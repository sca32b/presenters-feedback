# Presenter Feedback App - Technical Architecture

## 1. Overview

The Presenter Feedback App records a presenter's speech audio in the browser and provides AI-powered feedback on voice/tone, vocabulary, delivery speed, and overall TedX-level quality. The system is designed for economical AWS serverless deployment while supporting local development on Windows.

## 2. Tech Stack

### Frontend
- **Vanilla JavaScript (ES6+)** with minimal dependencies
- **Rationale**: No build step required, fast iteration, simple to serve from S3/CloudFront. The UI is a single-page recorder + results display -- a framework like React would be overengineered for this scope.
- **MediaRecorder API** for in-browser audio capture
- **CSS3** with responsive/mobile-first design

### Backend
- **Python 3.12 + FastAPI**
- **Rationale**: FastAPI provides async support, automatic OpenAPI docs, Pydantic validation, and runs well both locally (uvicorn) and on AWS Lambda (via Mangum adapter). Python has first-class AWS SDK support (boto3) for Bedrock, Transcribe, S3, and Cognito.
- **Mangum** adapter to wrap FastAPI as a Lambda handler
- **Pydantic v2** for request/response models

### Infrastructure
- **AWS SAM (Serverless Application Model)** for IaC
- **Rationale**: SAM is simpler than raw CloudFormation for Lambda-based apps, supports local testing via `sam local`, and integrates with CI/CD.

### AI/ML Services
- **Amazon Transcribe** for speech-to-text
- **Amazon Bedrock (Claude)** for analysis and feedback generation

### Auth
- **Amazon Cognito** user pools for authentication
- JWT tokens validated in FastAPI middleware

## 3. System Architecture

```
+------------------+       +-------------------+       +------------------+
|                  |       |                   |       |                  |
|   Browser        | ----> |   API Gateway     | ----> |   Lambda         |
|   (Recorder UI)  |       |   (REST)          |       |   (FastAPI +     |
|                  |       |                   |       |    Mangum)       |
+------------------+       +-------------------+       +------------------+
        |                                                     |
        |  presigned URL upload                               |
        v                                                     v
+------------------+                                 +------------------+
|                  |                                 |                  |
|   S3 Bucket      | <-----------------------------> |  AWS Services    |
|   (audio files)  |                                 |  - Transcribe    |
|                  |                                 |  - Bedrock       |
+------------------+                                 |  - DynamoDB      |
                                                     +------------------+
```

## 4. Data Flow

### Recording & Upload Flow
1. User authenticates via Cognito (hosted UI or custom login form)
2. User clicks "Record" -- browser uses `MediaRecorder` API to capture audio (WebM/Opus format)
3. User clicks "Stop" -- frontend requests a presigned S3 upload URL from the backend (`POST /api/uploads`)
4. Frontend uploads the audio blob directly to S3 via the presigned URL
5. Frontend calls `POST /api/analyses` with the S3 object key to initiate analysis

### Analysis Flow
1. Backend receives the analysis request, validates the JWT, creates a DynamoDB record with status `processing`
2. Backend starts an async pipeline:
   a. Calls **Amazon Transcribe** to convert audio to text (StartTranscriptionJob)
   b. Polls or uses a callback for transcription completion
   c. Sends the transcript + analysis prompt to **Amazon Bedrock (Claude)** requesting structured JSON feedback
   d. Parses the Bedrock response and stores results in DynamoDB
   e. Updates status to `completed`
3. Frontend polls `GET /api/analyses/{id}` until status is `completed`, then displays results

### Analysis Prompt Strategy
The Bedrock prompt requests a JSON response with these sections:
- **voice_tone**: Assessment of vocal qualities (confidence, warmth, authority, monotone detection)
- **vocabulary**: Richness score, filler word count, jargon assessment, readability level
- **pacing**: Words per minute, variation analysis, pause usage
- **overall_score**: 1-100 TedX-quality score with justification
- **recommendations**: Top 3 actionable improvements

## 5. API Design

Base path: `/api`

### Authentication
All endpoints require a valid JWT in the `Authorization: Bearer <token>` header, except `/api/health`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (no auth) |
| POST | `/api/uploads` | Get a presigned S3 upload URL |
| POST | `/api/analyses` | Start analysis for an uploaded audio file |
| GET | `/api/analyses/{id}` | Get analysis status and results |
| GET | `/api/analyses` | List user's past analyses (paginated) |

### Request/Response Schemas

#### POST /api/uploads
**Request:**
```json
{
  "filename": "recording-2026-02-08.webm",
  "content_type": "audio/webm"
}
```
**Response (200):**
```json
{
  "upload_url": "https://s3.amazonaws.com/...",
  "object_key": "uploads/{user_id}/{uuid}.webm"
}
```

#### POST /api/analyses
**Request:**
```json
{
  "object_key": "uploads/{user_id}/{uuid}.webm"
}
```
**Response (202):**
```json
{
  "analysis_id": "abc-123",
  "status": "processing"
}
```

#### GET /api/analyses/{id}
**Response (200):**
```json
{
  "analysis_id": "abc-123",
  "status": "completed",
  "created_at": "2026-02-08T12:00:00Z",
  "results": {
    "voice_tone": {
      "score": 72,
      "confidence_level": "moderate",
      "warmth": "high",
      "monotone_detected": false,
      "summary": "..."
    },
    "vocabulary": {
      "score": 65,
      "filler_word_count": 12,
      "unique_word_ratio": 0.74,
      "readability_level": "conversational",
      "summary": "..."
    },
    "pacing": {
      "score": 58,
      "words_per_minute": 162,
      "variation": "low",
      "pause_usage": "insufficient",
      "summary": "..."
    },
    "overall_score": 64,
    "overall_summary": "...",
    "recommendations": [
      "Slow down during key points and use 2-3 second pauses for emphasis",
      "Reduce filler words ('um', 'like') -- detected 12 instances",
      "Vary vocal pitch more to avoid monotone stretches"
    ]
  }
}
```

#### GET /api/analyses
**Query params:** `?page=1&page_size=10`
**Response (200):**
```json
{
  "items": [ ... ],
  "total": 25,
  "page": 1,
  "page_size": 10
}
```

## 6. Project Structure

```
presenters-feedback/
├── frontend/
│   ├── public/
│   │   └── index.html          # Main HTML page
│   ├── src/
│   │   ├── components/
│   │   │   ├── recorder.js     # Audio recording logic
│   │   │   ├── results.js      # Results display component
│   │   │   ├── history.js      # Past analyses list
│   │   │   └── auth.js         # Login/signup UI logic
│   │   ├── styles/
│   │   │   └── main.css        # All styles (mobile-first)
│   │   ├── api.js              # API client (fetch wrapper)
│   │   └── app.js              # Main application entry point
│   └── package.json            # For dev server only (optional)
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app creation + Mangum handler
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── health.py       # Health check endpoint
│   │   │   ├── uploads.py      # Presigned URL generation
│   │   │   └── analyses.py     # Analysis CRUD endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── transcribe.py   # Amazon Transcribe integration
│   │   │   ├── bedrock.py      # Amazon Bedrock/Claude integration
│   │   │   ├── storage.py      # S3 operations
│   │   │   └── analysis.py     # Orchestrates the analysis pipeline
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── schemas.py      # Pydantic request/response models
│   │   │   └── database.py     # DynamoDB table operations
│   │   └── config/
│   │       ├── __init__.py
│   │       └── settings.py     # Environment-based configuration
│   ├── requirements.txt
│   └── requirements-dev.txt
├── infra/
│   ├── template.yaml           # SAM template (Lambda, API GW, S3, DynamoDB, Cognito)
│   └── samconfig.toml          # SAM deployment config
├── tests/
│   ├── unit/
│   │   ├── test_analyses.py
│   │   ├── test_transcribe.py
│   │   └── test_bedrock.py
│   └── integration/
│       └── test_api.py
├── docs/
│   └── architecture.md         # This file
└── README.md
```

## 7. Local Development

### Prerequisites
- Python 3.12+
- AWS CLI configured with credentials (for Transcribe/Bedrock/S3 access)
- SAM CLI (optional, for Lambda simulation)

### Running Locally

**Backend:**
```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
python -m http.server 3000 --directory public
```
Or use any static file server. The frontend `api.js` will point to `http://localhost:8000/api` in local mode.

**Local auth bypass:**
In local development, the auth middleware reads a `LOCAL_DEV=true` environment variable and skips JWT validation, injecting a test user identity instead.

### Environment Variables
| Variable | Local Default | Description |
|----------|---------------|-------------|
| `LOCAL_DEV` | `true` | Bypass auth for local testing |
| `AWS_REGION` | `us-east-1` | AWS region |
| `S3_BUCKET` | `presenters-feedback-dev` | Audio upload bucket |
| `DYNAMODB_TABLE` | `presenters-feedback-dev` | Analysis results table |
| `COGNITO_USER_POOL_ID` | - | Cognito pool (prod only) |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-fable-5` | Bedrock model |

## 8. AWS Deployment Architecture

### Services Used
| Service | Purpose | Cost Optimization |
|---------|---------|-------------------|
| **S3** | Audio file storage + frontend hosting | Lifecycle policy to delete old audio after 30 days |
| **CloudFront** | CDN for frontend | Caching reduces origin requests |
| **API Gateway (HTTP)** | REST API | HTTP API type (cheaper than REST API type) |
| **Lambda** | Backend compute | 256MB memory, 60s timeout, pay-per-request |
| **DynamoDB** | Analysis results storage | On-demand billing (pay-per-request) |
| **Cognito** | User authentication | Free tier covers 50K MAUs |
| **Transcribe** | Speech-to-text | Pay per second of audio |
| **Bedrock** | AI analysis (Claude) | Pay per token |

### Estimated Monthly Cost (Low Usage: ~100 analyses/month)
- Lambda + API Gateway: ~$0 (free tier)
- S3: ~$0.05
- DynamoDB: ~$0 (free tier)
- Transcribe: ~$1-2 (assuming avg 5 min recordings)
- Bedrock: ~$2-5 (depending on transcript lengths)
- Cognito: $0 (free tier)
- **Total: ~$3-8/month**

## 9. Security Considerations

1. **Authentication**: All API endpoints (except health) require valid Cognito JWT
2. **Authorization**: Users can only access their own analyses (user_id from JWT compared to resource owner)
3. **S3 presigned URLs**: Short-lived (5 min expiry), scoped to user's prefix
4. **CORS**: API Gateway configured for specific frontend origin only
5. **Input validation**: Pydantic models validate all request payloads; file size limit enforced via presigned URL policy (max 50MB)
6. **No secrets in code**: All credentials via environment variables / IAM roles

## 10. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Frontend framework | Vanilla JS | Simple UI, no build step, fast to develop and deploy |
| Backend framework | FastAPI | Async, auto-docs, Lambda-compatible via Mangum, great Python ecosystem |
| IaC tool | SAM | Simpler than CDK for pure serverless, built-in local testing |
| Database | DynamoDB | Serverless, pay-per-request, simple key-value access pattern |
| Audio upload | Presigned S3 URLs | Avoids Lambda payload limits, direct client-to-S3 upload |
| Analysis approach | Synchronous pipeline | Simpler than Step Functions for MVP; can migrate later if needed |
| Auth | Cognito | Managed service, free tier, JWT-based, integrates with API Gateway |
