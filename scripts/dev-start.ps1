# ============================================================================
# Local Development Startup Script (PowerShell)
#
# Starts the backend (FastAPI) and frontend (static server) together.
# Prerequisites: Python 3.12+
#
# Usage: .\scripts\dev-start.ps1
# ============================================================================

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Presenters Feedback - Local Development" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Found $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Install Python 3.12+ from https://www.python.org/downloads/"
    exit 1
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"

# Set environment variables
$env:LOCAL_DEV = "true"
$env:AWS_REGION = "us-east-1"
$env:S3_BUCKET = "presenters-feedback-audio-dev"
$env:DYNAMODB_TABLE = "presenters-feedback-dev"
$env:BEDROCK_MODEL_ID = "us.anthropic.claude-fable-5"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000"

# Create venv if needed
$venvDir = Join-Path $backendDir "venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "[1/4] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $venvDir
}

# Install dependencies
Write-Host "[2/4] Installing backend dependencies..." -ForegroundColor Yellow
& (Join-Path $venvDir "Scripts" "pip.exe") install -q -r (Join-Path $backendDir "requirements.txt")

# Start backend in background
Write-Host "[3/4] Starting backend on http://localhost:8000 ..." -ForegroundColor Yellow
$backendJob = Start-Process -FilePath (Join-Path $venvDir "Scripts" "uvicorn.exe") `
    -ArgumentList "app.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $backendDir `
    -PassThru

# Start frontend in background
Write-Host "[4/4] Starting frontend on http://localhost:3000 ..." -ForegroundColor Yellow
$frontendJob = Start-Process -FilePath "python" `
    -ArgumentList "-m", "http.server", "3000" `
    -WorkingDirectory $frontendDir `
    -PassThru

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " Both servers are running:" -ForegroundColor Green
Write-Host "   Backend:  http://localhost:8000/api/docs" -ForegroundColor Green
Write-Host "   Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host "" -ForegroundColor Green
Write-Host " Press Ctrl+C to stop both servers." -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Green

try {
    # Wait for Ctrl+C
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Write-Host "Stopping servers..." -ForegroundColor Yellow
    if ($backendJob -and !$backendJob.HasExited) { Stop-Process -Id $backendJob.Id -Force }
    if ($frontendJob -and !$frontendJob.HasExited) { Stop-Process -Id $frontendJob.Id -Force }
    Write-Host "Servers stopped." -ForegroundColor Green
}
