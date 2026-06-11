@echo off
REM ============================================================================
REM Local Development Startup Script (Windows)
REM
REM Starts the backend (FastAPI) and frontend (static server) together.
REM Prerequisites: Python 3.12+, pip
REM ============================================================================

echo ============================================
echo  Presenters Feedback - Local Development
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Set local dev environment
set LOCAL_DEV=true
set AWS_REGION=us-east-1
set S3_BUCKET=presenters-feedback-audio-dev
set DYNAMODB_TABLE=presenters-feedback-dev
set BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5-20250929-v1:0
set CORS_ALLOWED_ORIGINS=http://localhost:3000

REM Install backend dependencies if needed
echo [1/3] Checking backend dependencies...
if not exist "%~dp0..\backend\venv" (
    echo Creating virtual environment...
    python -m venv "%~dp0..\backend\venv"
)
call "%~dp0..\backend\venv\Scripts\activate.bat"
pip install -q -r "%~dp0..\backend\requirements.txt" 2>nul

REM Start backend
echo [2/3] Starting backend on http://localhost:8000 ...
start "PF-Backend" cmd /c "cd /d %~dp0..\backend && call venv\Scripts\activate.bat && set "LOCAL_DEV=true" && uvicorn app.main:app --reload --port 8000"

REM Start frontend
echo [3/3] Starting frontend on http://localhost:3000 ...
start "PF-Frontend" cmd /c "cd /d %~dp0..\frontend && python -m http.server 3000"

echo.
echo ============================================
echo  Both servers are running:
echo    Backend:  http://localhost:8000/api/docs
echo    Frontend: http://localhost:3000
echo.
echo  Close the terminal windows to stop.
echo ============================================
pause
