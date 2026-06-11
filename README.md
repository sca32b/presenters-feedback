# Presenter Feedback

AI-powered presentation coach. Record your speech in the browser, get detailed feedback on voice/tone, vocabulary, pacing, and overall TedX-level delivery quality.

## How It Works

```
Record audio in browser
        |
        v
Upload to S3 (presigned URL)
        |
        v
Amazon Transcribe (speech-to-text)
        |
        v
Amazon Bedrock / Claude (analysis)
        |
        v
Structured feedback with scores and recommendations
```

1. Open the app in your browser and click **Record**
2. Deliver your presentation
3. Click **Stop**, then **Analyze**
4. Wait for results (typically under 2 minutes)
5. Review scores across four categories: voice/tone, vocabulary, pacing, and overall quality
6. Read actionable recommendations for improvement

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Vanilla JS, HTML, CSS | Audio recording UI, results display |
| Backend | Python 3.12, FastAPI | REST API, orchestration |
| AI | Amazon Bedrock (Claude) | Presentation analysis |
| Speech-to-Text | Amazon Transcribe | Audio transcription |
| Auth | Amazon Cognito | User authentication (JWT) |
| Storage | S3, DynamoDB | Audio files, analysis results |
| Infrastructure | AWS SAM | Serverless deployment |

## Quick Start (Local Development on Windows)

### Prerequisites

- **Python 3.12+** -- [download](https://www.python.org/downloads/)
- **AWS CLI** configured with credentials that have access to Transcribe, Bedrock, S3, and DynamoDB -- [install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- A microphone (for recording in the browser)

### Option A: Use the startup script

```cmd
scripts\dev-start.bat
```

This creates a virtual environment, installs dependencies, and starts both servers:
- Backend: http://localhost:8000 (API docs at http://localhost:8000/api/docs)
- Frontend: http://localhost:3000

### Option B: Start manually

**1. Set up the backend:**

```cmd
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**2. Create a `.env` file** (copy from the example):

```cmd
copy ..\infra\env.example .env
```

The default `.env` sets `LOCAL_DEV=true`, which bypasses Cognito authentication and injects a test user. You still need valid AWS credentials for Transcribe, Bedrock, and S3.

**3. Start the backend:**

```cmd
set LOCAL_DEV=true
uvicorn app.main:app --reload --port 8000
```

**4. Start the frontend** (in a separate terminal):

```cmd
cd frontend\public
python -m http.server 3000
```

**5. Open** http://localhost:3000 in your browser.

### Verify it works

- Backend health check: http://localhost:8000/api/health should return `{"status": "ok"}`
- API docs (auto-generated): http://localhost:8000/api/docs

## Deploy to AWS

### Prerequisites

- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- AWS CLI configured with credentials

### Deploy

```cmd
scripts\deploy.bat
```

Or for production:

```cmd
scripts\deploy.bat prod
```

This builds the Lambda package, deploys all AWS resources (Lambda, API Gateway, S3, DynamoDB, Cognito), and syncs the frontend to S3.

### Create User Accounts

After deploying, create Cognito user accounts:

```cmd
scripts\create-users.bat
```

The script prompts for email addresses and temporary passwords. Users set a permanent password on first login.

### View Deployment Outputs

```cmd
aws cloudformation describe-stacks --stack-name presenters-feedback-dev --query "Stacks[0].Outputs"
```

This shows the API URL, S3 bucket name, Cognito User Pool ID, and Client ID.

## Project Structure

```
presenters-feedback/
├── frontend/                  # Browser UI
│   ├── public/
│   │   └── index.html         # Main page
│   └── src/
│       ├── components/
│       │   ├── recorder.js    # Audio recording (MediaRecorder API)
│       │   ├── results.js     # Score display and recommendations
│       │   ├── history.js     # Past analyses list
│       │   └── auth.js        # Cognito authentication
│       ├── styles/
│       │   └── main.css       # Mobile-first responsive styles
│       ├── api.js             # Backend API client
│       └── app.js             # Application entry point
├── backend/                   # FastAPI server
│   ├── app/
│   │   ├── main.py            # App setup + Lambda handler (Mangum)
│   │   ├── api/
│   │   │   ├── health.py      # GET /api/health
│   │   │   ├── uploads.py     # POST /api/uploads (presigned URLs)
│   │   │   └── analyses.py    # POST/GET /api/analyses
│   │   ├── services/
│   │   │   ├── analysis.py    # Pipeline orchestrator
│   │   │   ├── transcribe.py  # Amazon Transcribe integration
│   │   │   ├── bedrock.py     # Amazon Bedrock/Claude integration
│   │   │   └── storage.py     # S3 operations
│   │   ├── models/
│   │   │   ├── schemas.py     # Pydantic request/response models
│   │   │   └── database.py    # DynamoDB operations
│   │   └── config/
│   │       └── settings.py    # Environment-based configuration
│   ├── requirements.txt       # Production dependencies
│   └── requirements-dev.txt   # Test dependencies
├── infra/                     # Infrastructure as Code
│   ├── template.yaml          # SAM template (all AWS resources)
│   ├── samconfig.toml         # SAM deployment config
│   └── env.example            # Example .env for local dev
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── scripts/
│   ├── dev-start.bat          # Start local dev servers
│   ├── deploy.bat             # Deploy to AWS
│   └── create-users.bat       # Create Cognito users
└── docs/
    ├── architecture.md        # Full technical architecture
    ├── aws-services.md        # AWS service details and code snippets
    └── ux-design.md           # UI/UX design specification
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health` | No | Health check |
| POST | `/api/uploads` | Yes | Get a presigned S3 upload URL |
| POST | `/api/analyses` | Yes | Start analysis for uploaded audio |
| GET | `/api/analyses/{id}` | Yes | Get analysis status and results |
| GET | `/api/analyses` | Yes | List past analyses (paginated) |

Interactive API docs are available at `/api/docs` when running locally.

## Feedback Categories

Each analysis returns scores (0-100) and feedback in four categories:

- **Voice & Tone** -- Confidence, warmth, monotone detection, vocal variety
- **Vocabulary** -- Word choice, filler word count, readability level, unique word ratio
- **Pacing** -- Words per minute, variation, strategic pause usage
- **Overall Score** -- TedX-level delivery assessment with top 3 recommendations

## Configuration

Key environment variables (see `infra/env.example` for full list):

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_DEV` | `false` | Set to `true` to bypass auth for local testing |
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `S3_BUCKET` | `presenters-feedback-audio-dev` | S3 bucket for audio uploads |
| `DYNAMODB_TABLE` | `presenters-feedback-dev` | DynamoDB table name |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-haiku-20241022-v1:0` | Bedrock model for analysis |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Allowed CORS origins |

## Cost Estimate (AWS)

At ~100 analyses per month (moderate personal use):

| Service | Estimated Cost |
|---------|---------------|
| Transcribe | $1-2 |
| Bedrock (Claude Haiku) | $1-2 |
| Lambda + API Gateway | ~$0 (free tier) |
| S3 + DynamoDB | ~$0 (free tier) |
| Cognito | $0 (free tier) |
| **Total** | **$2-4/month** |

## Running Tests

```cmd
cd backend
pip install -r requirements-dev.txt
pytest ..\tests
```

## Documentation

- [Architecture](docs/architecture.md) -- System design, data flow, API schemas, design decisions
- [AWS Services](docs/aws-services.md) -- Service details, code snippets, pricing, IAM permissions
- [UX Design](docs/ux-design.md) -- UI layout, components, color palette, responsive design
