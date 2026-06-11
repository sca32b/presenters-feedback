@echo off
REM ============================================================================
REM Create Cognito Users
REM
REM Creates user accounts in the Cognito User Pool.
REM Run this after deploying to set up access for you and your wife.
REM
REM Usage: scripts\create-users.bat
REM ============================================================================

set ENV=%1
if "%ENV%"=="" set ENV=dev

echo ============================================
echo  Create Cognito Users (%ENV%)
echo ============================================
echo.

REM Get User Pool ID from stack outputs
for /f "tokens=*" %%a in ('aws cloudformation describe-stacks --stack-name presenters-feedback-%ENV% --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text 2^>nul') do set POOL_ID=%%a

if "%POOL_ID%"=="" (
    echo ERROR: Could not find User Pool ID. Is the stack deployed?
    pause
    exit /b 1
)

echo User Pool ID: %POOL_ID%
echo.

REM Create first user
set /p EMAIL1=Enter email for user 1:
set /p PASS1=Enter temporary password for user 1:
aws cognito-idp admin-create-user ^
    --user-pool-id %POOL_ID% ^
    --username %EMAIL1% ^
    --user-attributes Name=email,Value=%EMAIL1% Name=email_verified,Value=true ^
    --temporary-password %PASS1% ^
    --message-action SUPPRESS

if errorlevel 1 (
    echo Failed to create user 1.
) else (
    echo User 1 created: %EMAIL1%
    echo They will need to set a new password on first login.
)

echo.

REM Create second user
set /p MORE=Create another user? (y/n):
if /i "%MORE%"=="y" (
    set /p EMAIL2=Enter email for user 2:
    set /p PASS2=Enter temporary password for user 2:
    aws cognito-idp admin-create-user ^
        --user-pool-id %POOL_ID% ^
        --username %EMAIL2% ^
        --user-attributes Name=email,Value=%EMAIL2% Name=email_verified,Value=true ^
        --temporary-password %PASS2% ^
        --message-action SUPPRESS

    if errorlevel 1 (
        echo Failed to create user 2.
    ) else (
        echo User 2 created: %EMAIL2%
    )
)

echo.
echo ============================================
echo  Users created. They will be prompted to
echo  set a new password on first login.
echo ============================================
pause
