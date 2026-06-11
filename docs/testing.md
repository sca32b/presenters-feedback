# Testing Guide - Presenter Feedback App

## Overview

The test suite covers the full stack of the Presenter Feedback application:

| Layer | Framework | Location | Count |
|-------|-----------|----------|-------|
| Backend unit tests | pytest | `tests/unit/` | ~70 tests |
| Backend integration tests | pytest | `tests/integration/` | ~25 tests |
| Frontend tests | Jest | `tests/frontend/` | ~35 tests |
| Infrastructure tests | pytest + YAML | `tests/integration/test_infrastructure.py` | ~30 tests |

All AWS services are mocked -- no real AWS credentials needed to run the test suite locally.

## Prerequisites

- Python 3.12+
- Node.js 20+ (for frontend tests)
- pip, npm

## Setup

### Install Python test dependencies

```bash
pip install -r tests/requirements-test.txt
pip install -r backend/requirements.txt
```

### Install JavaScript test dependencies

```bash
cd tests/frontend
npm install
```

## Running Tests

### All tests (recommended)

```bash
python tests/run_tests.py
```

Or on Windows:

```bash
tests\run_tests.bat
```

### Backend tests only

```bash
python tests/run_tests.py --backend
```

Or directly with pytest:

```bash
cd tests
set PYTHONPATH=../backend
pytest -v
```

### Frontend tests only

```bash
python tests/run_tests.py --frontend
```

Or directly with Jest:

```bash
cd tests/frontend
npx jest --config jest.config.js
```

### With coverage reports

```bash
python tests/run_tests.py --coverage
```

Coverage reports are generated in `tests/coverage/`:
- `tests/coverage/backend/` - Python coverage (HTML)
- `tests/coverage/frontend/` - JavaScript coverage (HTML)

### CI mode

```bash
python tests/run_tests.py --ci
```

Enables strict mode, generates JUnit XML reports, and coverage output suitable for CI systems.

## Test Structure

```
tests/
  conftest.py                          # Shared fixtures (AWS mocks, sample data, TestClient)
  pytest.ini                           # pytest configuration
  run_tests.py                         # Cross-platform test runner script
  run_tests.bat                        # Windows batch shortcut
  requirements-test.txt                # Python test dependencies
  unit/
    test_api_endpoints.py              # FastAPI route tests (health, uploads, analyses)
    test_storage_service.py            # S3 presigned URL generation tests
    test_transcribe_service.py         # Amazon Transcribe integration tests
    test_bedrock_service.py            # Bedrock/Claude analysis tests
    test_analysis_pipeline.py          # Full pipeline orchestration tests
    test_database.py                   # DynamoDB table operations tests
    test_settings.py                   # Application settings / configuration tests
  integration/
    test_full_flow.py                  # End-to-end pipeline integration tests
    test_infrastructure.py             # SAM template validation (security, resources, IAM)
  frontend/
    jest.config.js                     # Jest configuration
    package.json                       # Node.js dependencies for tests
    api.test.js                        # API client tests (getUploadUrl, startAnalysis, etc.)
    results.test.js                    # Results display component tests
```

## Test Categories

### Backend Unit Tests

**API Endpoints** (`test_api_endpoints.py`):
- Health check returns 200
- Upload endpoint validates Pydantic schema (filename required, content_type defaults)
- Analysis creation validates object_key
- Analysis retrieval by ID
- Paginated analysis listing with validation (page >= 1, page_size 1-50)
- CORS headers on all responses
- OPTIONS preflight requests

**Storage Service** (`test_storage_service.py`):
- Presigned URL generation uses correct S3 bucket
- Object key format: `uploads/{user_id}/{uuid}.{ext}`
- Content type passthrough to S3 params
- File extension extraction and defaults
- UUID uniqueness in object keys

**Transcribe Service** (`test_transcribe_service.py`):
- StartTranscriptionJob with correct parameters (media URI, language, output key)
- GetTranscriptionJob status handling (COMPLETED, IN_PROGRESS, FAILED)
- Error propagation for AWS service failures

**Bedrock Service** (`test_bedrock_service.py`):
- Invokes correct model ID from settings
- Sends transcript in the Anthropic messages API format
- Prompt includes expected analysis categories (voice_tone, vocabulary, pacing)
- Parses structured JSON response from Claude
- Handles throttling, malformed responses, service errors

**Analysis Pipeline** (`test_analysis_pipeline.py`):
- Creates initial DynamoDB record with 'processing' status
- Starts transcription job with correct job name format (pf-{analysis_id})
- Fetches transcript from S3 after transcription completes
- Stores final results in DynamoDB with 'completed' status
- Updates status to 'failed' on transcription failure

**Settings** (`test_settings.py`):
- Default values for all configuration fields
- Environment variable overrides
- Upload URL expiry, CORS origins, model ID

### Integration Tests

**Full Flow** (`test_full_flow.py`):
- Complete happy path: record -> upload -> transcribe -> analyze -> results
- Transcription failure propagation
- Presigned URL generation flow
- FastAPI endpoint validation integration
- CORS headers on live responses

**Infrastructure** (`test_infrastructure.py`):
- SAM template parses correctly
- All required resources exist (S3, DynamoDB, Lambda, API Gateway, Cognito, CloudFront)
- S3 buckets: encryption enabled, public access blocked, SSL enforced, lifecycle rules, CORS
- DynamoDB: PAY_PER_REQUEST billing, analysis_id hash key, user_id GSI, TTL enabled
- Lambda: Python 3.12 runtime, app.main.handler, reasonable timeout, environment variables
- IAM: S3 CRUD, DynamoDB CRUD, Transcribe, Bedrock (scoped to Claude models)
- Cognito: password policy (8+ chars, upper/lower/numbers), admin-only signup, no client secret
- API Gateway: CORS configured, Cognito JWT authorizer, health check no-auth
- CloudFront: HTTPS redirect, TLS 1.2 minimum, SPA error handling

### Frontend Tests

**API Client** (`api.test.js`):
- getUploadUrl sends POST /uploads with filename and content_type
- uploadAudio sends PUT to presigned URL with audio blob
- startAnalysis sends POST /analyses with object_key
- getAnalysis sends GET /analyses/{id}, handles completed/processing/404
- listAnalyses sends GET /analyses with pagination, defaults to page 1
- Error handling: extracts detail message, fallback for non-JSON, network errors

**Results Display** (`results.test.js`):
- Score card rendering for Voice & Tone, Vocabulary, Pacing
- Overall TedX score display
- Recommendations list rendering
- Polling behavior (3-second interval, stops on completed/failed)
- Loading and error state display

## Mocking Strategy

All AWS service calls are mocked at the boto3 client level:

- **S3**: `generate_presigned_url`, `put_object`, `get_object`, `delete_object`
- **Transcribe**: `start_transcription_job`, `get_transcription_job`
- **Bedrock Runtime**: `invoke_model` (returns structured JSON analysis)
- **DynamoDB**: `put_item`, `get_item`, `update_item`, `query`, `scan`

Fixtures are defined in `tests/conftest.py` and shared across all test files.

## CI/CD

The test suite runs automatically via GitHub Actions on push to main and on pull requests. See `.github/workflows/tests.yml`.

The CI pipeline runs three parallel jobs:
1. **Backend tests** - pytest with coverage
2. **Frontend tests** - Jest with coverage
3. **Infrastructure tests** - SAM template validation

## Adding New Tests

1. Create test functions/classes in the appropriate `test_*.py` file
2. Use fixtures from `conftest.py` (e.g., `client`, `mock_s3_client`, `sample_analysis_results`)
3. Follow the naming convention: `test_<description>` for functions, `Test<Area>` for classes
4. For async tests, use `@pytest.mark.asyncio` and `async def test_...`
5. Run tests locally before pushing: `python tests/run_tests.py`
