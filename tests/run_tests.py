#!/usr/bin/env python3
"""
Test runner script for the Presenter Feedback application.

Runs all tests (Python backend + JavaScript frontend) and generates
coverage reports. Works on Windows, macOS, and Linux.

Usage:
    python run_tests.py                  # Run all tests
    python run_tests.py --backend        # Run only backend (pytest) tests
    python run_tests.py --frontend       # Run only frontend (Jest) tests
    python run_tests.py --unit           # Run only unit tests
    python run_tests.py --integration    # Run only integration tests
    python run_tests.py --coverage       # Run with coverage report
    python run_tests.py --ci             # CI mode (strict, coverage, JUnit output)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent
COVERAGE_DIR = TESTS_DIR / "coverage"


def run_command(cmd, cwd=None, env=None):
    """Run a command and return the exit code."""
    print(f"\n{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")

    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, cwd=cwd or str(TESTS_DIR), env=merged_env)
    return result.returncode


def run_pytest(args):
    """Run Python backend tests with pytest."""
    cmd = [sys.executable, "-m", "pytest"]

    if args.unit and not args.integration:
        cmd.append("unit/")
    elif args.integration and not args.unit:
        cmd.append("integration/")

    if args.coverage or args.ci:
        cmd.extend([
            "--cov=app",
            "--cov-report=term-missing",
            f"--cov-report=html:{COVERAGE_DIR / 'backend'}",
        ])

    if args.ci:
        cmd.extend([
            f"--junitxml={COVERAGE_DIR / 'pytest-results.xml'}",
            "--strict-markers",
        ])

    if args.verbose:
        cmd.append("-vv")

    # Add markers filtering if specified
    if args.markers:
        cmd.extend(["-m", args.markers])

    return run_command(cmd, cwd=str(TESTS_DIR), env={
        "PYTHONPATH": str(PROJECT_ROOT / "backend"),
    })


def run_jest(args):
    """Run JavaScript frontend tests with Jest."""
    frontend_test_dir = TESTS_DIR / "frontend"

    # Check if node_modules exists (Jest is installed)
    node_modules = PROJECT_ROOT / "node_modules"
    if not node_modules.exists():
        # Try project-level or frontend-level
        for search_dir in [PROJECT_ROOT, PROJECT_ROOT / "frontend"]:
            pkg_json = search_dir / "package.json"
            if pkg_json.exists():
                print(f"Installing Node dependencies from {search_dir}...")
                result = run_command(["npm", "install"], cwd=str(search_dir))
                if result != 0:
                    print("Warning: npm install failed. Skipping frontend tests.")
                    return 1
                break
        else:
            print("Warning: No package.json found. Skipping frontend tests.")
            print("To run frontend tests, install Jest: npm install --save-dev jest")
            return 1

    cmd = ["npx", "jest", "--config", str(frontend_test_dir / "jest.config.js")]

    if args.coverage or args.ci:
        cmd.append("--coverage")

    if args.ci:
        cmd.extend(["--ci", "--reporters=default"])

    if args.verbose:
        cmd.append("--verbose")

    return run_command(cmd, cwd=str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Run Presenter Feedback tests")
    parser.add_argument("--backend", action="store_true", help="Run only backend tests")
    parser.add_argument("--frontend", action="store_true", help="Run only frontend tests")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage reports")
    parser.add_argument("--ci", action="store_true", help="CI mode (strict + coverage + JUnit)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--markers", "-m", type=str, help="pytest markers filter (e.g. 'not slow')")
    args = parser.parse_args()

    # Default: run everything
    run_all = not args.backend and not args.frontend

    # Ensure coverage directory exists
    COVERAGE_DIR.mkdir(parents=True, exist_ok=True)

    exit_codes = []

    # Run backend tests
    if run_all or args.backend:
        print("\n" + "#" * 60)
        print("# BACKEND TESTS (pytest)")
        print("#" * 60)
        exit_codes.append(("Backend (pytest)", run_pytest(args)))

    # Run frontend tests
    if run_all or args.frontend:
        print("\n" + "#" * 60)
        print("# FRONTEND TESTS (Jest)")
        print("#" * 60)
        exit_codes.append(("Frontend (Jest)", run_jest(args)))

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, code in exit_codes:
        status = "PASSED" if code == 0 else "FAILED"
        if code != 0:
            all_passed = False
        print(f"  {name}: {status} (exit code {code})")

    if args.coverage or args.ci:
        print(f"\nCoverage reports: {COVERAGE_DIR}")

    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
