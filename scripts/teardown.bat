@echo off
REM ============================================================================
REM Tear Down AWS Infrastructure
REM
REM WARNING: This deletes ALL resources including S3 data and DynamoDB tables.
REM
REM Usage:
REM   scripts\teardown.bat              Tear down dev environment
REM   scripts\teardown.bat prod         Tear down prod environment
REM ============================================================================

set ENV=%1
if "%ENV%"=="" set ENV=dev

echo ============================================
echo  WARNING: Tearing down %ENV% environment
echo ============================================
echo.
echo This will DELETE all AWS resources for the %ENV% environment,
echo including S3 buckets, DynamoDB tables, Lambda functions, etc.
echo.
set /p CONFIRM=Are you sure? (yes/no):
if /i not "%CONFIRM%"=="yes" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Emptying S3 buckets...
for /f "tokens=*" %%a in ('aws cloudformation describe-stacks --stack-name presenters-feedback-%ENV% --query "Stacks[0].Outputs[?OutputKey=='AudioBucketName'].OutputValue" --output text 2^>nul') do (
    aws s3 rm "s3://%%a" --recursive 2>nul
)
for /f "tokens=*" %%a in ('aws cloudformation describe-stacks --stack-name presenters-feedback-%ENV% --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" --output text 2^>nul') do (
    aws s3 rm "s3://%%a" --recursive 2>nul
)

echo Deleting CloudFormation stack...
cd /d "%~dp0..\infra"
sam delete --stack-name presenters-feedback-%ENV% --no-prompts

echo.
echo ============================================
echo  Teardown complete.
echo ============================================
pause
