# Presenter Feedback App - UX Design Document

## Overview

A web application that allows presenters to record or upload their speech audio and receive detailed AI-powered feedback on their presentation skills. The target user is preparing for a TED/TEDx-style talk and wants to improve voice quality, vocabulary, pacing, and overall delivery.

## Design Principles

1. **Simplicity first** - Minimal UI with clear actions. The user should know what to do within seconds of loading the page.
2. **Mobile-friendly** - Fully responsive. The primary user's wife will access from a mobile device.
3. **Professional appearance** - Clean typography, muted color palette, subtle animations. Conveys credibility.
4. **Progressive disclosure** - Show recording controls first, reveal feedback only after analysis completes.
5. **Encouraging tone** - Feedback should feel constructive, not judgmental. Visual scores use warm colors.

## Color Palette

| Role        | Color      | Usage                              |
|-------------|------------|------------------------------------|
| Primary     | #2563EB    | Buttons, active states, links      |
| Secondary   | #7C3AED    | Accent elements, highlights        |
| Success     | #059669    | Good scores, completion states     |
| Warning     | #D97706    | Medium scores, caution states      |
| Danger      | #DC2626    | Low scores, errors, stop button    |
| Background  | #F8FAFC    | Page background                    |
| Surface     | #FFFFFF    | Cards, panels                      |
| Text        | #1E293B    | Primary text                       |
| Text Muted  | #64748B    | Secondary text, labels             |

## Typography

- **Font family**: Inter (Google Fonts) with system font fallback
- **Headings**: 600 weight, sizes 1.5rem - 2.5rem
- **Body**: 400 weight, 1rem (16px base)
- **Small/labels**: 0.875rem

## Page Layout

### Single-Page Application with Three Sections

```
+-----------------------------------------------+
|  [Logo/Title]              [History Button]    |
+-----------------------------------------------+
|                                                |
|  +-------------------------------------------+|
|  |          RECORDING SECTION                 ||
|  |                                            ||
|  |  [Audio Level Visualizer]                  ||
|  |                                            ||
|  |  00:00 / Timer                             ||
|  |                                            ||
|  |  [Record]  [Pause]  [Stop]                 ||
|  |                                            ||
|  |  --- or ---                                ||
|  |                                            ||
|  |  [Upload Audio File]                       ||
|  +-------------------------------------------+|
|                                                |
|  +-------------------------------------------+|
|  |          FEEDBACK SECTION                  ||
|  |  (appears after analysis)                  ||
|  |                                            ||
|  |  Overall Score: [===========] 8.2/10       ||
|  |                                            ||
|  |  +----------+  +----------+                ||
|  |  |Voice/Tone|  |Vocabulary|                ||
|  |  |  7.5/10  |  |  8.0/10  |                ||
|  |  +----------+  +----------+                ||
|  |  +----------+  +----------+                ||
|  |  |  Speed   |  | Clarity  |                ||
|  |  |  9.0/10  |  |  7.8/10  |                ||
|  |  +----------+  +----------+                ||
|  |                                            ||
|  |  Detailed Feedback:                        ||
|  |  - Voice: "Your tone is confident..."      ||
|  |  - Vocab: "Good range, consider..."        ||
|  |  - Speed: "Well paced at 142 WPM..."       ||
|  +-------------------------------------------+|
|                                                |
+-----------------------------------------------+
```

### History Panel (Slide-in from right on mobile, sidebar on desktop)

```
+---------------------------+
| Analysis History          |
+---------------------------+
| [Dec 15] Score: 8.2  [>] |
| [Dec 14] Score: 7.5  [>] |
| [Dec 12] Score: 6.8  [>] |
+---------------------------+
```

## Component Details

### 1. Recording Controls

- **Record button**: Large, circular, red. Pulses when recording.
- **Pause button**: Standard pause icon. Only visible during recording.
- **Stop button**: Square icon. Only visible during recording or paused state.
- **Timer**: MM:SS format, updates every second during recording.
- **States**: idle -> recording -> paused -> stopped

### 2. Audio Level Visualizer

- Horizontal bar-style level meter (not waveform for simplicity).
- Shows 20 bars that respond to microphone input volume in real-time.
- Uses green/yellow/red gradient to indicate levels.
- Provides visual confirmation that the microphone is working.

### 3. Upload Alternative

- Drag-and-drop zone below recording controls.
- Accepts .wav, .mp3, .m4a, .webm formats.
- Shows file name and duration after selection.
- "or" divider between record and upload sections.

### 4. Loading/Analysis State

- Replaces feedback section while analysis is in progress.
- Animated spinner with status messages:
  - "Uploading audio..."
  - "Transcribing speech..."
  - "Analyzing presentation..."
  - "Generating feedback..."
- Progress bar (indeterminate if no progress info from API, determinate if available).

### 5. Feedback Display

- **Overall Score**: Large circular gauge, color-coded (green > 70, yellow > 40, red <= 40). Scores use a 0-100 scale.
- **Category Cards**: 2x2 grid on desktop, stacked on mobile. Each card shows:
  - Category icon
  - Score as circular progress indicator
  - One-line summary
  - Expandable detailed feedback
- **Categories**:
  - Voice & Tone (microphone icon)
  - Vocabulary (book icon)
  - Delivery Speed (speedometer icon)
  - Overall Readiness (star icon)
- **Detailed Analysis**: Collapsible section below cards with full text feedback.
- **Suggestions**: Bulleted list of actionable improvements.

### 6. Error States

- Toast notifications for transient errors (network issues, etc.).
- Inline error messages for form validation.
- Microphone permission denied: Full-page prompt with instructions.
- API errors: Friendly message with retry button.

## Responsive Breakpoints

| Breakpoint | Width    | Layout Changes                    |
|------------|----------|-----------------------------------|
| Mobile     | < 640px  | Single column, stacked cards      |
| Tablet     | 640-1024 | 2-column card grid                |
| Desktop    | > 1024px | Centered content, max-width 800px |

## Interactions & Animations

- Button hover: Subtle scale (1.02) and shadow increase.
- Recording pulse: Red glow animation on record button.
- Score reveal: Counter animation from 0 to final score.
- Card expand: Smooth height transition for detailed feedback.
- Page transitions: Fade-in for new content sections.
- Level meter: 60fps updates using requestAnimationFrame.

## Accessibility

- All interactive elements are keyboard-navigable.
- ARIA labels on icon-only buttons.
- Color is not the sole indicator of state (icons + text supplement colors).
- Focus indicators on all interactive elements.
- Screen reader announcements for recording state changes.

## API Integration Points

Endpoints (aligned with architecture document):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (no auth) |
| POST | `/api/uploads` | Get a presigned S3 upload URL |
| POST | `/api/analyses` | Start analysis for an uploaded audio file |
| GET | `/api/analyses/{id}` | Get analysis status and results (poll until `status: completed`) |
| GET | `/api/analyses` | List user's past analyses (paginated) |

### Upload Flow
1. `POST /api/uploads` with `{ filename, content_type }` to get a presigned S3 URL
2. `PUT` the audio blob directly to the presigned S3 URL
3. `POST /api/analyses` with `{ object_key }` to start analysis
4. Poll `GET /api/analyses/{id}` until `status` is `completed`

### Authentication
All endpoints (except `/api/health`) require `Authorization: Bearer <JWT>` header.
Local development bypasses auth via `LOCAL_DEV=true` environment variable.

### Score Scale
All scores use a 0-100 integer scale. Categories: `voice_tone`, `vocabulary`, `pacing`, `overall_score`.
