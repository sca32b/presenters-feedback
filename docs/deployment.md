# Deployment Guide

This document covers deploying and running the Presenters Feedback app both locally (on Windows) and on AWS.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Cost Estimates](#cost-estimates)
3. [Prerequisites](#prerequisites)
4. [Local Development Setup (Windows)](#local-development-setup-windows)
5. [AWS Deployment](#aws-deployment)
6. [Creating User Accounts](#creating-user-accounts)
7. [Teardown](#teardown)
8. [CI/CD with GitHub Actions](#cicd-with-github-actions)
9. [Security](#security)
10. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
                     HTTPS
  Browser  ──────────────────►  CloudFront  ──►  S3 (frontend)
    │                              │
    │  Authorization: Bearer JWT   │
    ▼                              ▼
  API Gateway (HTTP API)  ◄──  Cognito (JWT validation)
    │
    └──►  Lambda: presenters-feedback-api  (FastAPI + Mangum, 256MB, 60s)
            ├── GET  /api/health          (no auth)
            ├── POST /api/uploads         → S3 presigned URL
            ├── POST /api/analyses        → Transcribe + Bedrock pipeline
            ├── GET  /api/analyses/{id}   → DynamoDB lookup
            └── GET  /api/analyses        → DynamoDB query

  Storage:
    S3 (presenters-feedback-*)  ── audio uploads, lifecycle: auto-delete
    DynamoDB                    ── analysis results, on-demand billing, TTL

  AI Pipeline (inside Lambda):
    Amazon Transcribe (batch STT) → Bedrock Claude (analysis) → DynamoDB
```

All infrastructure is defined in `infra/template.yaml` (AWS SAM).

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| IaC tool | AWS SAM | Simpler than CDK for Lambda apps, built-in local testing |
| API type | HTTP API (v2) | $1/M requests vs $3.50/M for REST API |
| Backend | Single Lambda (FastAPI + Mangum) | Simple, all routes in one function |
| Database | DynamoDB on-demand | Zero idle cost, simple key-value access, TTL |
| Auth | Cognito (admin-create only) | Managed, free tier (50K MAUs), JWT-based |
| Frontend CDN | CloudFront PriceClass_100 | Cheapest: US/Canada/Europe edges only |
| Model | Claude Fable 5 | Configured through `BEDROCK_MODEL_ID` |

---

## Cost Estimates

### Per-Analysis Cost (5-minute recording)

| Service | Operation | Cost |
|---------|-----------|------|
| Amazon Transcribe | 5 min batch | $0.12 |
| Lambda (librosa) | ~30s at 1 GB | $0.0005 |
| Bedrock Claude Fable 5 | ~2K in + ~1.5K out tokens | Usage-based |
| S3 storage | ~10 MB audio + results | ~$0.0002 |
| API Gateway | 3-4 requests | ~$0.000004 |
| DynamoDB | ~5 read/write units | ~$0.000003 |
| **Total per analysis** | | **~$0.13** |

### Monthly Estimates

| Usage | Analyses/month | Monthly Cost |
|-------|---------------|--------------|
| Light (1/week) | 4 | ~$0.52 |
| Moderate (3/week) | 12 | ~$1.56 |
| Heavy (daily) | 30 | ~$3.90 |

### Always-On Costs (regardless of usage)

| Resource | Monthly Cost |
|----------|-------------|
| CloudFront distribution | $0 (no minimum) |
| S3 buckets (near-empty) | < $0.01 |
| DynamoDB (on-demand, no data) | $0 |
| Cognito (2 users) | $0 |
| **Total idle cost** | **< $0.01/month** |

### Free Tier Benefits (First 12 Months)

- Transcribe: 60 min/month free (covers ~12 five-minute recordings)
- Lambda: 1M requests + 400K GB-seconds free
- DynamoDB: 25 GB storage + 25 WCU/25 RCU
- S3: 5 GB standard storage
- CloudFront: 1 TB transfer

**With free tier, expect under $1/month for typical personal use.**

---

## Prerequisites

### For Local Development

- **Python 3.12+**: [python.org/downloads](https://www.python.org/downloads/)
- **Git**: [git-scm.com](https://git-scm.com/download/win)
- **AWS CLI v2** (optional, for using real AWS services locally):
  [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Docker Desktop** (optional, for LocalStack):
  [docker.com](https://www.docker.com/products/docker-desktop/)

### For AWS Deployment

All of the above, plus:

- **AWS SAM CLI**: [Install guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- **AWS account** with credentials configured (`aws configure`)
- **Docker** (required for `sam build --use-container` to build the container image Lambda)

### Install SAM CLI on Windows

```powershell
# Using MSI installer (recommended):
# Download from https://github.com/aws/aws-sam-cli/releases/latest

# Or via Chocolatey:
choco install aws-sam-cli

# Verify:
sam --version
```

---

## Local Development Setup (Windows)

### Quick Start

```powershell
# Clone the repo
git clone <repo-url>
cd presenters-feedback

# Option A: PowerShell script (recommended)
.\scripts\dev-start.ps1

# Option B: Batch file
.\scripts\dev-start.bat
```

This starts:
- **Backend** at http://localhost:8000 (FastAPI with hot-reload)
- **Frontend** at http://localhost:3000 (static file server)
- **API docs** at http://localhost:8000/api/docs (Swagger UI)

### Manual Setup

```powershell
# 1. Create and activate virtual environment
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Set environment variables
$env:LOCAL_DEV = "true"
$env:AWS_REGION = "us-east-1"
$env:S3_BUCKET = "presenters-feedback-audio-dev"
$env:DYNAMODB_TABLE = "presenters-feedback-dev"

# 4. Start the backend
uvicorn app.main:app --reload --port 8000

# 5. In another terminal, start the frontend
cd frontend\public
python -m http.server 3000
```

### Using LocalStack (Optional)

LocalStack emulates S3 and DynamoDB locally so you don't need real AWS credentials for basic testing.

```powershell
# Start LocalStack
docker-compose -f infra\docker-compose.localstack.yml up -d

# Set endpoint override
$env:AWS_ENDPOINT_URL = "http://localhost:4566"

# Verify resources were created
aws --endpoint-url=http://localhost:4566 s3 ls
aws --endpoint-url=http://localhost:4566 dynamodb list-tables
```

**Note**: LocalStack Community does NOT emulate Amazon Transcribe or Bedrock. In `LOCAL_DEV=true` mode, the backend uses mock implementations for those services.

### Testing with SAM CLI (Optional)

SAM CLI can invoke Lambda functions locally:

```powershell
cd infra

# Build the SAM application
sam build

# Invoke a single function with a test event
sam local invoke ApiFunction --event events/test-health.json

# Start a local API Gateway
sam local start-api --port 3001

# Then test:
curl http://localhost:3001/api/health
```

Create test events in `infra/events/`:

```json
// events/test-health.json
{
  "httpMethod": "GET",
  "path": "/api/health",
  "headers": {},
  "queryStringParameters": null,
  "body": null
}
```

---

## AWS Deployment

### First-Time Setup

1. **Configure AWS CLI credentials:**

```powershell
aws configure
# Enter your AWS Access Key ID, Secret Access Key, region (us-east-1)
```

2. **Enable Bedrock model access** (one-time, manual step):
   - Go to [Amazon Bedrock Console](https://console.aws.amazon.com/bedrock/)
   - Navigate to "Model access" in the left sidebar
   - Request access to `Anthropic > Claude Fable 5`
   - Wait for approval

3. **Build and deploy:**

```powershell
# Option A: Use the deploy script
.\scripts\deploy.bat         # deploys dev
.\scripts\deploy.bat prod    # deploys prod

# Option B: Manual SAM commands
cd infra
sam build --use-container
sam deploy                   # deploys dev (uses samconfig.toml defaults)
sam deploy --config-env prod # deploys prod
```

4. **Note the outputs** (API URL, CloudFront URL, User Pool ID, etc.):

```powershell
aws cloudformation describe-stacks `
  --stack-name presenters-feedback-dev `
  --query "Stacks[0].Outputs" `
  --output table
```

5. **Deploy the frontend** to S3:

```powershell
# Get the frontend bucket name from outputs
$BUCKET = aws cloudformation describe-stacks `
  --stack-name presenters-feedback-dev `
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" `
  --output text

# Sync frontend files
aws s3 sync frontend\public\ "s3://$BUCKET/" --delete

# Invalidate CloudFront cache
$DIST_ID = aws cloudformation describe-stacks `
  --stack-name presenters-feedback-dev `
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" `
  --output text

aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

### Updating the Frontend Configuration

After deployment, update the frontend to point to the real API and Cognito:

Edit `frontend/public/src/api.js` (or equivalent config) with values from the stack outputs:

```javascript
const CONFIG = {
  API_URL: "https://xxxxx.execute-api.us-east-1.amazonaws.com/dev",
  COGNITO_USER_POOL_ID: "us-east-1_xxxxxxxxx",
  COGNITO_CLIENT_ID: "xxxxxxxxxxxxxxxxxxxxxxxxxx",
  COGNITO_REGION: "us-east-1",
};
```

Then re-deploy the frontend:

```powershell
aws s3 sync frontend\public\ "s3://$BUCKET/" --delete
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

---

## Creating User Accounts

Cognito is configured with `AllowAdminCreateUserOnly: true`, so users must be created by an admin (you).

### Using the Script

```powershell
.\scripts\create-users.bat       # interactive, prompts for email + password
```

### Manual CLI

```powershell
# Get User Pool ID
$POOL_ID = aws cloudformation describe-stacks `
  --stack-name presenters-feedback-dev `
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" `
  --output text

# Create a user
aws cognito-idp admin-create-user `
  --user-pool-id $POOL_ID `
  --username "user@example.com" `
  --user-attributes Name=email,Value=user@example.com Name=email_verified,Value=true `
  --temporary-password "TempPass123" `
  --message-action SUPPRESS

# The user will be prompted to set a permanent password on first login.
```

### Setting a Permanent Password (skip the force-change flow)

```powershell
aws cognito-idp admin-set-user-password `
  --user-pool-id $POOL_ID `
  --username "user@example.com" `
  --password "PermanentPass123" `
  --permanent
```

---

## Teardown

To completely remove all AWS resources:

```powershell
# Option A: Use the script (includes confirmation prompt)
.\scripts\teardown.bat       # dev
.\scripts\teardown.bat prod  # prod

# Option B: Manual
cd infra
sam delete --stack-name presenters-feedback-dev --no-prompts
```

This deletes all CloudFormation resources: Lambda functions, API Gateway, S3 buckets, DynamoDB table, Cognito user pool, CloudFront distribution, and all IAM roles.

S3 buckets must be empty before stack deletion. The teardown script handles this automatically.

---

## CI/CD with GitHub Actions

The `.github/workflows/deploy.yml` workflow provides automated testing and deployment:

| Trigger | Action |
|---------|--------|
| PR to `main` | Run tests only |
| Push to `develop` | Run tests, deploy to dev |
| Push to `main` | Run tests, deploy to prod |

### Setup

1. **Create an OIDC IAM role** for GitHub Actions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_ORG>/<REPO_NAME>:*"
        }
      }
    }
  ]
}
```

2. **Add the role ARN** as a GitHub repository secret named `AWS_DEPLOY_ROLE_ARN`.

3. **Create GitHub environments** named `dev` and `prod` (optional, for approval gates on prod).

---

## Security

### Authentication Flow

1. User opens the app (served by CloudFront over HTTPS)
2. User logs in with email/password via the Cognito-powered login form
3. Cognito returns JWT tokens (id_token, access_token, refresh_token)
4. Frontend includes `Authorization: Bearer <access_token>` on all API requests
5. API Gateway validates the JWT against the Cognito User Pool before forwarding to Lambda
6. Lambda extracts user identity from the validated JWT claims

### Security Measures

| Measure | Implementation |
|---------|---------------|
| HTTPS everywhere | CloudFront redirects HTTP to HTTPS; API Gateway is HTTPS-only |
| Authentication | Cognito User Pool with JWT tokens; no self-signup |
| Authorization | User ID extracted from JWT; users can only access own analyses |
| S3 access | No direct public access; presigned URLs (5 min expiry) for uploads |
| S3 encryption | Server-side encryption (SSE-S3) on all buckets |
| SSL enforcement | S3 bucket policy denies non-SSL requests |
| Frontend isolation | CloudFront OAI; S3 bucket blocks all public access |
| CORS | API Gateway configured with specific frontend origin |
| Input validation | Pydantic models validate all request payloads |
| File size limit | Presigned URL policy enforces 50MB max upload |
| IAM least privilege | Each Lambda gets only the permissions it needs |
| Data lifecycle | Audio auto-deleted after 30 days (configurable) |
| No secrets in code | All config via environment variables / IAM roles |

---

## Troubleshooting

### Common Issues

**"sam build" fails on Windows:**
- Ensure Docker Desktop is running (required for `--use-container`)
- Try `sam build` without `--use-container` if you have Python 3.12 installed

**Lambda timeout on analysis:**
- The analyze Lambda has a 300s (5 min) timeout
- Transcribe can take 30-90 seconds for a 5-minute recording
- If consistently timing out, check CloudWatch Logs for the specific step that's slow

**Cognito "User does not exist" error:**
- Ensure the user was created with the correct email
- Check if the User Pool ID and Client ID in the frontend config match the deployed stack

**CORS errors in browser:**
- Verify the `FrontendOrigin` parameter matches your CloudFront URL
- For local development, ensure `CORS_ALLOWED_ORIGINS=http://localhost:3000`

**Bedrock "Access denied":**
- Go to the Bedrock console and verify model access is granted for Claude Fable 5
- Model access requests are per-region; ensure you requested in us-east-1

**S3 presigned URL upload fails:**
- Check that the audio bucket CORS configuration allows PUT from the frontend origin
- Verify the presigned URL hasn't expired (5 min default)

### Viewing Logs

```powershell
# View Lambda logs
sam logs --stack-name presenters-feedback-dev --name ApiFunction --tail

# Or via CloudWatch
aws logs tail /aws/lambda/pf-api-dev --follow
aws logs tail /aws/lambda/pf-analyze-dev --follow
```

### Useful AWS CLI Commands

```powershell
# List all stack resources
aws cloudformation list-stack-resources --stack-name presenters-feedback-dev

# Check Lambda function configuration
aws lambda get-function-configuration --function-name pf-api-dev

# List Cognito users
aws cognito-idp list-users --user-pool-id $POOL_ID

# Check DynamoDB table
aws dynamodb scan --table-name presenters-feedback-dev --max-items 5
```
