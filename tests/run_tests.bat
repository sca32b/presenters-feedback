@echo off
REM ============================================================================
REM Test Runner for Windows
REM
REM Sets up the Python virtual environment, installs dependencies, and runs
REM the full test suite with pytest.
REM
REM Usage:
REM   tests\run_tests.bat                Run all tests
REM   tests\run_tests.bat --backend      Run only Python backend tests
REM   tests\run_tests.bat --frontend     Run only JavaScript frontend tests
REM   tests\run_tests.bat --coverage     Run with coverage reports
REM   tests\run_tests.bat --unit         Run only unit tests
REM   tests\run_tests.bat --integration  Run only integration tests
REM   tests\run_tests.bat --ci           CI mode (strict + coverage + JUnit)
REM   tests\run_tests.bat --skip-setup   Skip venv creation and pip install
REM ============================================================================

setlocal

set PROJECT_ROOT=%~dp0..
set BACKEND_DIR=%PROJECT_ROOT%\backend
set TESTS_DIR=%~dp0
set VENV_DIR=%BACKEND_DIR%\venv

REM Check for --skip-setup flag
set SKIP_SETUP=0
for %%a in (%*) do (
    if "%%a"=="--skip-setup" set SKIP_SETUP=1
)

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python 3.12+ from https://www.python.org/downloads/
    exit /b 1
)

if %SKIP_SETUP%==0 (
    echo ============================================
    echo  Setting up test environment...
    echo ============================================

    REM Create venv if it doesn't exist
    if not exist "%VENV_DIR%\Scripts\activate.bat" (
        echo Creating virtual environment...
        python -m venv "%VENV_DIR%"
    )

    REM Activate venv
    call "%VENV_DIR%\Scripts\activate.bat"

    REM Install backend dependencies
    echo Installing backend dependencies...
    pip install -q -r "%BACKEND_DIR%\requirements.txt" 2>nul

    REM Install test dependencies
    echo Installing test dependencies...
    pip install -q -r "%BACKEND_DIR%\requirements-dev.txt" 2>nul
    pip install -q -r "%TESTS_DIR%\requirements-test.txt" 2>nul
) else (
    REM Still activate venv if it exists
    if exist "%VENV_DIR%\Scripts\activate.bat" (
        call "%VENV_DIR%\Scripts\activate.bat"
    )
)

echo.
echo ============================================
echo  Running tests...
echo ============================================
echo.

REM Set environment for tests
set LOCAL_DEV=true
set PYTHONPATH=%BACKEND_DIR%

REM Delegate to run_tests.py
cd /d "%TESTS_DIR%"
python run_tests.py %*

set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE%==0 (
    echo All tests passed.
) else (
    echo Some tests failed. Exit code: %EXIT_CODE%
)

exit /b %EXIT_CODE%
