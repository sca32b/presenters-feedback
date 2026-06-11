# AWS Services for Presentation/Speech Analysis

## Overview

This document recommends the AWS services, Bedrock models, and supporting libraries
for the Presenters Feedback application. The goal is to analyze a speaker's presentation
across four dimensions: voice quality/tone, vocabulary, speed of delivery, and overall
quality benchmarked against TED-talk standards.

---

## Recommended Architecture (Pipeline)

```
Audio file (MP3/WAV/M4A)
        |
        v
  +-----+------+
  |             |
  v             v
AWS Transcribe  Lambda (librosa)
  (STT with     (pitch, energy,
   timestamps,   speaking rate,
   filler words) pause detection)
  |             |
  v             v
  +------+------+
         |
         v
   Amazon Bedrock
   (Claude model)
   Comprehensive scoring
   using transcript + audio features
         |
         v
   Structured JSON feedback
   (scores, suggestions, benchmarks)
```

**Why this pipeline?**
- Transcribe handles speech-to-text with word-level timestamps, which gives us
  words-per-minute, pause durations, and filler word detection.
- A lightweight Lambda with librosa extracts audio-level features (pitch/F0,
  energy/loudness, spectral features) that Transcribe does not provide.
- Bedrock Claude receives both the transcript and the extracted audio features
  and produces a single, comprehensive analysis with scores and actionable feedback.
- Amazon Comprehend is optional -- Claude can perform sentiment analysis itself,
  but Comprehend can be added for a second opinion at minimal cost.

---

## 1. AWS Transcribe

### What It Does
Converts speech to text. Returns a transcript with word-level timestamps,
confidence scores, speaker diarization, and automatic punctuation.

### Batch vs Real-Time

| Feature | Batch (StartTranscriptionJob) | Real-Time (StartStreamTranscription) |
|---------|-------------------------------|--------------------------------------|
| Latency | Minutes (async) | Sub-second |
| Max duration | 4 hours | 4 hours |
| Output | JSON in S3 | WebSocket stream |
| Cost | $0.024/min (standard) | $0.024/min |
| Word timestamps | Yes | Yes |
| Speaker diarization | Yes (up to 10 speakers) | Yes |
| Custom vocabulary | Yes | Yes |
| Automatic language detection | Yes | Yes |
| Toxicity detection | Yes | No |

**Recommendation**: Use **batch transcription** (`StartTranscriptionJob`). The user uploads
a recording, so real-time streaming is unnecessary. Batch is simpler to implement,
produces the same quality output, and the async model fits well with a Lambda/Step
Functions pipeline.

### Key Settings
- `ShowSpeakerLabels`: Enable if the presentation might have Q&A or multiple speakers.
- `ShowAlternatives`: Get alternative transcriptions for uncertain words.
- `LanguageCode`: `en-US` (or use `IdentifyLanguage` for auto-detection).
- `MediaFormat`: Supports mp3, mp4, wav, flac, ogg, amr, webm.

### Pricing (us-east-1)
- **Standard**: $0.024 per minute of audio (first 250,000 minutes/month)
- **Free tier**: 60 minutes/month for the first 12 months
- A 5-minute speech costs: **$0.12**

### Python Code Snippet

```python
import boto3
import time
import json

transcribe = boto3.client("transcribe", region_name="us-east-1")

def start_transcription(job_name: str, s3_uri: str, language: str = "en-US") -> str:
    """Start a batch transcription job and return the job name."""
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        MediaFormat="mp3",  # adjust based on input
        LanguageCode=language,
        Settings={
            "ShowSpeakerLabels": True,
            "MaxSpeakerLabels": 5,
            "ShowAlternatives": False,
        },
        OutputBucketName="presenters-feedback-transcripts",
    )
    return job_name


def wait_for_transcription(job_name: str, poll_interval: int = 5) -> dict:
    """Poll until the transcription job completes and return the result."""
    while True:
        response = transcribe.get_transcription_job(
            TranscriptionJobName=job_name
        )
        status = response["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            # The transcript JSON is stored in S3; fetch it
            transcript_uri = response["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            import urllib.request
            with urllib.request.urlopen(transcript_uri) as resp:
                return json.loads(resp.read().decode())
        elif status == "FAILED":
            raise RuntimeError(
                f"Transcription failed: {response['TranscriptionJob']['FailureReason']}"
            )
        time.sleep(poll_interval)


def extract_transcript_features(transcript_json: dict) -> dict:
    """Extract useful features from the Transcribe output."""
    items = transcript_json["results"]["items"]

    words = []
    filler_words = {"um", "uh", "like", "you know", "so", "basically", "actually",
                    "literally", "right", "okay", "er", "ah", "hmm"}
    filler_count = 0
    total_words = 0
    word_timestamps = []

    for item in items:
        if item["type"] == "pronunciation":
            word = item["alternatives"][0]["content"].lower()
            confidence = float(item["alternatives"][0]["confidence"])
            start_time = float(item["start_time"])
            end_time = float(item["end_time"])

            words.append(word)
            word_timestamps.append({
                "word": word,
                "start": start_time,
                "end": end_time,
                "confidence": confidence,
            })
            total_words += 1

            if word in filler_words:
                filler_count += 1

    # Calculate speaking rate
    if word_timestamps:
        total_duration_sec = word_timestamps[-1]["end"] - word_timestamps[0]["start"]
        total_duration_min = total_duration_sec / 60.0
        wpm = total_words / total_duration_min if total_duration_min > 0 else 0
    else:
        wpm = 0
        total_duration_sec = 0

    # Detect pauses (gaps > 1.5 seconds between words)
    pauses = []
    for i in range(1, len(word_timestamps)):
        gap = word_timestamps[i]["start"] - word_timestamps[i - 1]["end"]
        if gap > 1.5:
            pauses.append({
                "after_word": word_timestamps[i - 1]["word"],
                "before_word": word_timestamps[i]["word"],
                "duration_sec": round(gap, 2),
                "at_time_sec": round(word_timestamps[i - 1]["end"], 2),
            })

    return {
        "transcript_text": " ".join(words),
        "total_words": total_words,
        "total_duration_sec": round(total_duration_sec, 2),
        "words_per_minute": round(wpm, 1),
        "filler_word_count": filler_count,
        "filler_word_ratio": round(filler_count / total_words, 4) if total_words > 0 else 0,
        "pauses_over_1_5_sec": pauses,
        "average_confidence": round(
            sum(w["confidence"] for w in word_timestamps) / len(word_timestamps), 4
        ) if word_timestamps else 0,
    }
```

---

## 2. Audio Feature Extraction with librosa (Lambda)

### Why This Is Needed
AWS Transcribe provides text and timestamps but does **not** provide acoustic features
like pitch (fundamental frequency), energy/loudness, or spectral characteristics.
These are essential for evaluating voice quality, confidence, and expressiveness.

### Recommended Approach
Run a Python Lambda function with `librosa` to extract audio features. Package
librosa and its dependencies (numpy, scipy, soundfile) as a Lambda layer or
container image.

**Important**: Lambda has a 250 MB unzipped deployment limit for layers. librosa +
numpy + scipy exceeds this, so use a **container image** Lambda (up to 10 GB).

### Features to Extract

| Feature | What It Measures | How to Extract |
|---------|-----------------|----------------|
| Pitch (F0) | Vocal tone, confidence, monotone detection | `librosa.pyin()` |
| Energy (RMS) | Loudness variation, emphasis | `librosa.feature.rms()` |
| Speaking rate variation | Pacing consistency | Word timestamps from Transcribe |
| Spectral centroid | Brightness/clarity of voice | `librosa.feature.spectral_centroid()` |
| Zero crossing rate | Voice quality/breathiness | `librosa.feature.zero_crossing_rate()` |
| Silence ratio | How much time is silence vs speech | Energy thresholding |

### Pricing
- Lambda: $0.0000166667 per GB-second. A 5-minute audio file processed in ~30
  seconds at 1 GB memory = **$0.0005**
- Essentially free for personal use.

### Python Code Snippet

```python
import numpy as np
import librosa
import json


def extract_audio_features(audio_path: str) -> dict:
    """Extract acoustic features from an audio file using librosa."""
    # Load audio (librosa resamples to 22050 Hz by default)
    y, sr = librosa.load(audio_path, sr=22050)
    duration = librosa.get_duration(y=y, sr=sr)

    # --- Pitch (Fundamental Frequency) using PYIN ---
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7")
    )
    f0_valid = f0[~np.isnan(f0)]

    pitch_stats = {
        "mean_hz": round(float(np.mean(f0_valid)), 2) if len(f0_valid) > 0 else 0,
        "std_hz": round(float(np.std(f0_valid)), 2) if len(f0_valid) > 0 else 0,
        "min_hz": round(float(np.min(f0_valid)), 2) if len(f0_valid) > 0 else 0,
        "max_hz": round(float(np.max(f0_valid)), 2) if len(f0_valid) > 0 else 0,
        "range_hz": round(float(np.max(f0_valid) - np.min(f0_valid)), 2) if len(f0_valid) > 0 else 0,
        "voiced_ratio": round(float(np.mean(voiced_flag)), 4),
    }

    # Pitch variability over time (monotone detection)
    # Split into 10-second windows and compute pitch std per window
    window_samples = int(10 * sr / 512) * 512  # align to hop length
    pitch_variability_over_time = []
    hop_length = 512
    for i in range(0, len(f0) - 1, int(10 * sr / hop_length)):
        window = f0[i:i + int(10 * sr / hop_length)]
        window_valid = window[~np.isnan(window)]
        if len(window_valid) > 5:
            pitch_variability_over_time.append(round(float(np.std(window_valid)), 2))

    # --- Energy (RMS) ---
    rms = librosa.feature.rms(y=y)[0]
    energy_stats = {
        "mean": round(float(np.mean(rms)), 6),
        "std": round(float(np.std(rms)), 6),
        "max": round(float(np.max(rms)), 6),
        "dynamic_range_db": round(float(
            20 * np.log10(np.max(rms) / (np.min(rms[rms > 0]) + 1e-10))
        ), 2) if np.any(rms > 0) else 0,
    }

    # --- Spectral Centroid (voice clarity/brightness) ---
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    clarity_stats = {
        "spectral_centroid_mean_hz": round(float(np.mean(spectral_centroid)), 2),
        "spectral_centroid_std_hz": round(float(np.std(spectral_centroid)), 2),
    }

    # --- Silence Detection ---
    # Frames where RMS is below 2% of max
    silence_threshold = 0.02 * np.max(rms)
    silence_frames = np.sum(rms < silence_threshold)
    total_frames = len(rms)
    silence_ratio = silence_frames / total_frames if total_frames > 0 else 0

    # --- Speaking Rate Variation ---
    # We compute energy envelope to find speech segments
    # (detailed rate variation comes from Transcribe word timestamps)

    return {
        "duration_sec": round(duration, 2),
        "sample_rate": sr,
        "pitch": pitch_stats,
        "pitch_variability_per_10s_window": pitch_variability_over_time,
        "energy": energy_stats,
        "clarity": clarity_stats,
        "silence_ratio": round(float(silence_ratio), 4),
        "summary": {
            "is_monotone": pitch_stats["std_hz"] < 15,  # low pitch variation
            "has_good_energy_variation": energy_stats["std"] > 0.01,
            "silence_percentage": round(silence_ratio * 100, 1),
        },
    }


# Usage in Lambda handler
def lambda_handler(event, context):
    import boto3
    import tempfile
    import os

    s3 = boto3.client("s3")
    bucket = event["bucket"]
    key = event["key"]

    # Download audio to /tmp
    tmp_path = os.path.join(tempfile.gettempdir(), "audio_input")
    s3.download_file(bucket, key, tmp_path)

    features = extract_audio_features(tmp_path)

    # Store results in S3
    output_key = key.rsplit(".", 1)[0] + "_audio_features.json"
    s3.put_object(
        Bucket=bucket,
        Key=output_key,
        Body=json.dumps(features, indent=2),
        ContentType="application/json",
    )

    return {"status": "success", "features": features, "output_key": output_key}
```

---

## 3. AWS Bedrock -- Claude (Primary Analysis Engine)

### Why Claude?
Claude excels at structured analysis of text, understanding context, and generating
actionable feedback. It can evaluate vocabulary sophistication, argument structure,
persuasiveness, and clarity -- tasks that rule-based systems handle poorly.

### Available Claude Models on Bedrock

| Model | Model ID on Bedrock | Context Window | Input Price (per 1K tokens) | Output Price (per 1K tokens) | Recommendation |
|-------|---------------------|----------------|----------------------------|-----------------------------|----|
| Claude 3.5 Haiku | `anthropic.claude-3-5-haiku-20241022-v1:0` | 200K | $0.001 | $0.005 | **Best for cost-sensitive personal use** |
| Claude 3.5 Sonnet v2 | `anthropic.claude-3-5-sonnet-20241022-v2:0` | 200K | $0.003 | $0.015 | Good balance of quality/cost |
| Claude Sonnet 4 | `anthropic.claude-sonnet-4-20250514-v1:0` | 200K | $0.003 | $0.015 | Latest Sonnet, excellent reasoning |
| Claude Opus 4 | `anthropic.claude-opus-4-20250514-v1:0` | 200K | $0.015 | $0.075 | Best quality, higher cost |

**Recommendation**: Use **Claude 3.5 Haiku** for personal use. A 5-minute presentation
transcript is roughly 700-900 words (~1,000 tokens input). With the prompt and audio
features included, expect ~2,000 tokens input and ~1,500 tokens output.

**Cost per analysis with Haiku**: ~$0.002 input + ~$0.0075 output = **~$0.01**

If higher quality is needed, Claude Sonnet 4 costs ~$0.03 per analysis.

### Region Availability
Bedrock Claude models are available in: `us-east-1`, `us-west-2`, `eu-west-1`,
`ap-northeast-1`, and others. Use `us-east-1` for best availability and lowest latency
in North America.

### Python Code Snippet

```python
import boto3
import json

bedrock_runtime = boto3.client("bedrock-runtime", region_name="us-east-1")

# Use the Converse API (recommended, works uniformly across models)
def analyze_presentation(
    transcript_features: dict,
    audio_features: dict,
    model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0",
) -> dict:
    """Send transcript and audio features to Claude for comprehensive analysis."""

    prompt = build_analysis_prompt(transcript_features, audio_features)

    response = bedrock_runtime.converse(
        modelId=model_id,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        system=[
            {
                "text": (
                    "You are an expert presentation coach who has trained hundreds of "
                    "TED speakers. You analyze presentations with precision and provide "
                    "actionable, specific feedback. You always respond in valid JSON format."
                )
            }
        ],
        inferenceConfig={
            "maxTokens": 2048,
            "temperature": 0.3,  # low temperature for consistent scoring
        },
    )

    result_text = response["output"]["message"]["content"][0]["text"]

    # Parse JSON from response
    try:
        return json.loads(result_text)
    except json.JSONDecodeError:
        # Claude sometimes wraps JSON in markdown code blocks
        import re
        json_match = re.search(r"```json?\s*(.*?)\s*```", result_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return {"raw_response": result_text}


def build_analysis_prompt(transcript_features: dict, audio_features: dict) -> str:
    """Build the comprehensive analysis prompt for Claude."""
    return f"""Analyze this presentation and provide detailed scoring and feedback.

## Transcript Data
- **Full transcript**: {transcript_features['transcript_text']}
- **Total words**: {transcript_features['total_words']}
- **Duration**: {transcript_features['total_duration_sec']} seconds
- **Words per minute**: {transcript_features['words_per_minute']}
- **Filler word count**: {transcript_features['filler_word_count']} (ratio: {transcript_features['filler_word_ratio']})
- **Pauses over 1.5s**: {json.dumps(transcript_features['pauses_over_1_5_sec'])}
- **Transcription confidence**: {transcript_features['average_confidence']}

## Audio Features (extracted from audio signal)
- **Pitch**: mean={audio_features['pitch']['mean_hz']}Hz, std={audio_features['pitch']['std_hz']}Hz, range={audio_features['pitch']['range_hz']}Hz
- **Is monotone**: {audio_features['summary']['is_monotone']}
- **Energy**: mean={audio_features['energy']['mean']}, std={audio_features['energy']['std']}, dynamic_range={audio_features['energy']['dynamic_range_db']}dB
- **Has good energy variation**: {audio_features['summary']['has_good_energy_variation']}
- **Voice clarity (spectral centroid)**: mean={audio_features['clarity']['spectral_centroid_mean_hz']}Hz
- **Silence ratio**: {audio_features['silence_ratio']} ({audio_features['summary']['silence_percentage']}%)
- **Pitch variability per 10s window**: {audio_features['pitch_variability_per_10s_window']}

## TED Talk Benchmarks for Reference
- Ideal speaking rate: 130-170 WPM (TED average is ~150 WPM)
- Filler word ratio: <2% is excellent, 2-5% is acceptable, >5% needs work
- Pitch variation (std): >25Hz indicates good expressiveness
- Pause usage: Strategic pauses of 1-3 seconds are effective; >5 seconds is too long
- Dynamic range: >20dB indicates good vocal emphasis variation

## Instructions
Score each dimension from 1-10 and provide specific, actionable feedback.
Respond in this exact JSON format:

{{
  "overall_score": <1-10>,
  "dimensions": {{
    "voice_quality": {{
      "score": <1-10>,
      "sub_scores": {{
        "pitch_variation": <1-10>,
        "energy_and_emphasis": <1-10>,
        "clarity": <1-10>,
        "confidence": <1-10>
      }},
      "feedback": "<2-3 sentences of specific feedback>",
      "improvement_tips": ["<tip 1>", "<tip 2>"]
    }},
    "vocabulary": {{
      "score": <1-10>,
      "sub_scores": {{
        "word_choice": <1-10>,
        "filler_words": <1-10>,
        "complexity_appropriateness": <1-10>,
        "persuasive_language": <1-10>
      }},
      "feedback": "<2-3 sentences>",
      "improvement_tips": ["<tip 1>", "<tip 2>"],
      "notable_phrases": ["<good phrase>", "<phrase to improve>"],
      "filler_word_details": "<specific filler word feedback>"
    }},
    "delivery_speed": {{
      "score": <1-10>,
      "sub_scores": {{
        "overall_pace": <1-10>,
        "pace_variation": <1-10>,
        "strategic_pauses": <1-10>,
        "rush_detection": <1-10>
      }},
      "feedback": "<2-3 sentences>",
      "improvement_tips": ["<tip 1>", "<tip 2>"],
      "wpm_assessment": "<how their WPM compares to ideal>"
    }},
    "overall_quality": {{
      "score": <1-10>,
      "sub_scores": {{
        "structure": <1-10>,
        "engagement": <1-10>,
        "persuasiveness": <1-10>,
        "ted_benchmark": <1-10>
      }},
      "feedback": "<2-3 sentences>",
      "improvement_tips": ["<tip 1>", "<tip 2>"],
      "ted_comparison": "<how this compares to a typical TED talk>"
    }}
  }},
  "top_3_strengths": ["<strength>", "<strength>", "<strength>"],
  "top_3_improvements": ["<improvement>", "<improvement>", "<improvement>"],
  "one_line_summary": "<one sentence overall assessment>"
}}"""
```

### Alternative: Using the InvokeModel API (lower-level)

```python
def analyze_with_invoke_model(prompt: str) -> str:
    """Alternative using InvokeModel API directly (Claude-specific payload)."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "temperature": 0.3,
        "system": "You are an expert presentation coach. Respond in valid JSON.",
        "messages": [
            {"role": "user", "content": prompt}
        ],
    })

    response = bedrock_runtime.invoke_model(
        modelId="anthropic.claude-3-5-haiku-20241022-v1:0",
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]
```

---

## 4. Amazon Comprehend (Optional -- Sentiment Analysis)

### What It Does
Amazon Comprehend provides NLP features including sentiment analysis, entity
detection, key phrase extraction, and language detection. It can add a
supplementary sentiment score to the analysis.

### Why It Is Optional
Claude can perform sentiment analysis as part of its comprehensive analysis.
Comprehend is useful if you want a second, independent sentiment signal or
want to skip Claude for a quick preliminary check.

### Pricing
- **Sentiment analysis**: $0.0001 per unit (1 unit = 100 characters, minimum 3 units)
- A 5-minute transcript (~4,000 characters) = 40 units = **$0.004**
- **Free tier**: 50,000 units/month for the first 12 months

### Python Code Snippet

```python
import boto3

comprehend = boto3.client("comprehend", region_name="us-east-1")


def analyze_sentiment(text: str) -> dict:
    """Analyze sentiment of the transcript text."""
    # Comprehend has a 5,000 byte limit per call for real-time
    # For longer texts, split into chunks
    response = comprehend.detect_sentiment(
        Text=text[:5000],
        LanguageCode="en",
    )
    return {
        "sentiment": response["Sentiment"],  # POSITIVE, NEGATIVE, NEUTRAL, MIXED
        "scores": {
            "positive": round(response["SentimentScore"]["Positive"], 4),
            "negative": round(response["SentimentScore"]["Negative"], 4),
            "neutral": round(response["SentimentScore"]["Neutral"], 4),
            "mixed": round(response["SentimentScore"]["Mixed"], 4),
        },
    }


def extract_key_phrases(text: str) -> list:
    """Extract key phrases from the transcript."""
    response = comprehend.detect_key_phrases(
        Text=text[:5000],
        LanguageCode="en",
    )
    return [
        {"text": phrase["Text"], "confidence": round(phrase["Score"], 4)}
        for phrase in response["KeyPhrases"]
        if phrase["Score"] > 0.9
    ]


def detect_entities(text: str) -> list:
    """Detect named entities (useful for topic analysis)."""
    response = comprehend.detect_entities(
        Text=text[:5000],
        LanguageCode="en",
    )
    return [
        {
            "text": entity["Text"],
            "type": entity["Type"],
            "confidence": round(entity["Score"], 4),
        }
        for entity in response["Entities"]
        if entity["Score"] > 0.9
    ]
```

---

## 5. Cost Analysis

### Per-Analysis Cost (5-minute speech)

| Service | Operation | Estimated Cost |
|---------|-----------|---------------|
| AWS Transcribe | 5 min batch transcription | $0.12 |
| Lambda (librosa) | ~30s at 1 GB memory | $0.0005 |
| Bedrock Claude 3.5 Haiku | ~2K input + ~1.5K output tokens | $0.01 |
| Amazon Comprehend (optional) | Sentiment on ~4K chars | $0.004 |
| S3 storage | Audio + results (~10 MB) | ~$0.0002 |
| **Total (without Comprehend)** | | **~$0.13** |
| **Total (with Comprehend)** | | **~$0.14** |

### Monthly Cost Estimates (Personal Use)

| Usage Level | Analyses/month | Monthly Cost |
|-------------|---------------|--------------|
| Light (1/week) | 4 | ~$0.52 |
| Moderate (3/week) | 12 | ~$1.56 |
| Heavy (daily) | 30 | ~$3.90 |

### Free Tier Benefits (First 12 Months)
- **Transcribe**: 60 minutes/month free (covers 12 five-minute analyses)
- **Lambda**: 1M free requests + 400,000 GB-seconds
- **Comprehend**: 50,000 units/month free
- **S3**: 5 GB free
- Bedrock has **no free tier**, but Haiku costs are negligible

**With free tier, cost drops to ~$0.01 per analysis** (just the Bedrock call).

---

## 6. Recommended Pipeline Implementation

### Step Functions Workflow

Use AWS Step Functions to orchestrate the pipeline:

```
StartExecution
    |
    v
[Upload audio to S3]
    |
    +---> [Start Transcribe Job] (async)
    +---> [Invoke librosa Lambda] (async)
    |          |
    v          v
[Wait for Transcribe]  [Audio features ready]
    |          |
    v          v
[Both complete - merge results]
    |
    v
[Invoke Bedrock Claude analysis]
    |
    v
[Store results in S3 / DynamoDB]
    |
    v
[Return results to user]
```

### Simplified Implementation (Single Lambda)

For personal use, a single Lambda can orchestrate everything sequentially.
This avoids the complexity of Step Functions.

```python
import boto3
import json
import os
import tempfile
import time

s3 = boto3.client("s3")
transcribe = boto3.client("transcribe")
bedrock_runtime = boto3.client("bedrock-runtime")

BUCKET = os.environ["BUCKET_NAME"]


def handler(event, context):
    """Main orchestrator Lambda. Triggered by S3 upload."""
    audio_key = event["Records"][0]["s3"]["object"]["key"]
    job_name = f"presentation-{int(time.time())}"

    # Step 1: Start transcription (async)
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": f"s3://{BUCKET}/{audio_key}"},
        MediaFormat=audio_key.rsplit(".", 1)[-1],
        LanguageCode="en-US",
        Settings={"ShowSpeakerLabels": True, "MaxSpeakerLabels": 5},
        OutputBucketName=BUCKET,
        OutputKey=f"transcripts/{job_name}.json",
    )

    # Step 2: Extract audio features while waiting
    tmp_audio = os.path.join(tempfile.gettempdir(), "audio_input")
    s3.download_file(BUCKET, audio_key, tmp_audio)

    # Import here to avoid cold start penalty if audio extraction is in a layer
    from audio_features import extract_audio_features
    audio_features = extract_audio_features(tmp_audio)

    # Step 3: Wait for transcription
    while True:
        resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            break
        elif status == "FAILED":
            raise RuntimeError("Transcription failed")
        time.sleep(3)

    # Step 4: Parse transcript
    transcript_obj = s3.get_object(Bucket=BUCKET, Key=f"transcripts/{job_name}.json")
    transcript_json = json.loads(transcript_obj["Body"].read())

    from transcript_features import extract_transcript_features
    transcript_features = extract_transcript_features(transcript_json)

    # Step 5: Analyze with Claude
    from bedrock_analysis import analyze_presentation
    analysis = analyze_presentation(transcript_features, audio_features)

    # Step 6: Store results
    result_key = f"results/{job_name}_analysis.json"
    s3.put_object(
        Bucket=BUCKET,
        Key=result_key,
        Body=json.dumps({
            "analysis": analysis,
            "transcript_features": transcript_features,
            "audio_features": audio_features,
        }, indent=2),
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Analysis complete",
            "result_key": result_key,
        }),
    }
```

### Lambda Timeout Note
The orchestrator Lambda must have a timeout of at least **5 minutes** (300 seconds)
to accommodate Transcribe processing time. For 5-minute audio, Transcribe typically
completes in 30-90 seconds. Set the Lambda timeout to 300 seconds to be safe.

Alternatively, use an S3 event notification on the Transcribe output to trigger
the analysis Lambda only after transcription completes. This avoids polling and
reduces Lambda execution time.

---

## 7. IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:Converse"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "comprehend:DetectSentiment",
        "comprehend:DetectKeyPhrases",
        "comprehend:DetectEntities"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::presenters-feedback-*/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:*:function:presenters-feedback-*"
    }
  ]
}
```

---

## 8. Summary of Recommendations

| Component | Recommended Service | Model/Config | Est. Cost per Run |
|-----------|-------------------|--------------|-------------------|
| Speech-to-text | AWS Transcribe (batch) | Standard, en-US | $0.12 |
| Audio features | Lambda + librosa | Container image, 1GB RAM | $0.0005 |
| Comprehensive analysis | Bedrock Claude | `anthropic.claude-3-5-haiku-20241022-v1:0` | $0.01 |
| Sentiment (optional) | Amazon Comprehend | DetectSentiment | $0.004 |
| Orchestration | Single Lambda or Step Functions | 300s timeout | (included in Lambda cost) |
| Storage | S3 | Standard | ~$0.0002 |
| **Total** | | | **~$0.13** |

### Key Decisions
1. **Use Haiku for cost efficiency** -- upgrade to Sonnet if analysis quality is insufficient.
2. **Batch Transcribe over real-time** -- simpler, same cost, sufficient for uploaded recordings.
3. **librosa in Lambda container** -- only practical way to get pitch/energy features in AWS.
4. **Comprehend is optional** -- Claude handles sentiment well; add Comprehend only if you
   want an independent NLP signal.
5. **Single Lambda orchestrator** for simplicity. Move to Step Functions only if you need
   parallel processing or retries at scale.
6. **Region**: `us-east-1` for best service availability and model access.
