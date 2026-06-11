@echo off
setlocal
set PROJECT_ROOT=%~dp0..
set PYTHON=%PROJECT_ROOT%\backend\venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo Python virtual environment not found at %PYTHON%.
    echo Run scripts\dev-start.bat or create backend\venv first.
    exit /b 1
)

set PYTHONPATH=%PROJECT_ROOT%\backend
set LOCAL_DEV=true
set S3_BUCKET=test-bucket
set DYNAMODB_TABLE=test-table
set BEDROCK_MODEL_ID=us.anthropic.claude-fable-5
set COGNITO_USER_POOL_ID=us-east-1_test
set COGNITO_APP_CLIENT_ID=test-client
set CORS_ALLOWED_ORIGINS=http://localhost:3000

cd /d "%PROJECT_ROOT%"
"%PYTHON%" -m pytest tests -v
if errorlevel 1 exit /b %errorlevel%

cd /d "%PROJECT_ROOT%\tests\frontend"
npm.cmd test
exit /b %errorlevel%
