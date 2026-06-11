# Runs the full local test suite using the project-managed Python venv.
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $projectRoot "backend\venv\Scripts\python.exe"
$npm = "npm.cmd"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "Python virtual environment not found at $python. Run scripts\dev-start.ps1 or create backend\venv first."
}

$env:PYTHONPATH = Join-Path $projectRoot "backend"
$env:LOCAL_DEV = "true"
$env:S3_BUCKET = "test-bucket"
$env:DYNAMODB_TABLE = "test-table"
$env:BEDROCK_MODEL_ID = "us.anthropic.claude-fable-5"
$env:COGNITO_USER_POOL_ID = "us-east-1_test"
$env:COGNITO_APP_CLIENT_ID = "test-client"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000"

Push-Location $projectRoot
try {
    & $python -m pytest tests -v
    Push-Location (Join-Path $projectRoot "tests\frontend")
    try {
        & $npm test
    } finally {
        Pop-Location
    }
} finally {
    Pop-Location
}
