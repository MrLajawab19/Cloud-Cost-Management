"""Automated regression runner for backend/tests.

Runs every backend/tests/verify_*.py (excluding verify_real_azure.py and measurements)
against a fresh SQLite backup-API copy of the live database in $env:TEMP.
Never writes to the live backend/cloud_cost.db.
Deletes each temporary copy immediately after the test completes.
"""

import os
import sys
import tempfile
import sqlite3
import subprocess
from pathlib import Path

# Bootstrap test environment
import _bootstrap
from _bootstrap import BACKEND_DIR, TESTS_DIR

LIVE_DB = BACKEND_DIR / "cloud_cost.db"
VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def run_all_tests() -> int:
    test_files = sorted([
        f for f in TESTS_DIR.glob("verify_*.py")
        if f.name != "verify_real_azure.py"
    ])

    print(f"Discovered {len(test_files)} verification test suites to execute:")
    results = {}
    failures = []

    for idx, test_path in enumerate(test_files, start=1):
        test_name = test_path.name
        temp_db_path = Path(tempfile.gettempdir()) / f"run_all_{test_name}.db"

        # Ensure no stale temp file exists
        if temp_db_path.exists():
            try:
                temp_db_path.unlink()
            except Exception:
                pass

        # Create fresh SQLite backup from live DB (read-only source)
        src_conn = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(str(temp_db_path))
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        engine_url = f"sqlite:///{temp_db_path}"
        print(f"[{idx:02d}/{len(test_files):02d}] Running {test_name}")
        print(f"       Engine Path: {engine_url}")

        env = os.environ.copy()
        env["DATABASE_URL"] = engine_url
        env["PYTHONPATH"] = str(BACKEND_DIR)

        proc = subprocess.run(
            [PYTHON_EXE, str(test_path)],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            results[test_name] = "PASS"
            print(f"       Result: PASS")
        else:
            results[test_name] = f"FAIL (exit {proc.returncode})"
            failures.append(test_name)
            print(f"       Result: FAIL (exit {proc.returncode})")
            if proc.stderr:
                print(f"       STDERR: {proc.stderr[-300:].strip()}")

        # Clean up temporary database copy
        if temp_db_path.exists():
            try:
                temp_db_path.unlink()
            except Exception:
                pass

    print("\n" + "=" * 50)
    print("           REGRESSION EXECUTION SUMMARY")
    print("=" * 50)
    for test_name, status in results.items():
        print(f"  {test_name:<36} : {status}")
    print("=" * 50)
    print(f"Total: {len(results)} | Passed: {len(results) - len(failures)} | Failed: {len(failures)}")
    print("=" * 50 + "\n")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

