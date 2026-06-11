@echo off
REM ============================================================================
REM Deploy to AWS
REM
REM Usage:
REM   scripts\deploy.bat              Deploy dev environment
REM   scripts\deploy.bat prod         Deploy prod environment
REM ============================================================================

set ENV=%1
if "%ENV%"=="" set ENV=dev

echo ============================================
echo  Deploying to AWS (%ENV%)
echo ============================================

REM Check prerequisites
sam --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: SAM CLI is not installed.
    echo Install from https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
    pause
    exit /b 1
)

aws sts get-caller-identity >nul 2>&1
if errorlevel 1 (
    echo ERROR: AWS credentials not configured.
    echo Run: aws configure
    pause
    exit /b 1
)

REM Build
echo.
echo [1/3] Building SAM application...
cd /d "%~dp0..\infra"
sam build --use-container

REM Deploy
echo.
echo [2/3] Deploying to AWS...
if "%ENV%"=="prod" (
    sam deploy --config-env prod
) else (
    sam deploy
)

REM Deploy frontend to S3
echo.
echo [3/3] Deploying frontend to S3...
for /f "tokens=2" %%a in ('aws cloudformation describe-stacks --stack-name presenters-feedback-%ENV% --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text 2^>nul') do set BUCKET=%%a
if not "%BUCKET%"=="" (
    aws s3 sync "%~dp0..\frontend" "s3://%BUCKET%/" --delete --exclude "serve.py" --exclude "__pycache__/*" --exclude "src/*" --exclude "public/*"
    echo Frontend deployed to S3.
) else (
    echo WARNING: Could not find frontend bucket. Deploy frontend manually.
)

echo.
echo ============================================
echo  Deployment complete!
echo ============================================
echo.
echo Run the following to see your endpoints:
echo   aws cloudformation describe-stacks --stack-name presenters-feedback-%ENV% --query "Stacks[0].Outputs"
echo.
pause
