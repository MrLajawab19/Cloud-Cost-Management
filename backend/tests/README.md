# Backend Test Suites

Run all automated tests against isolated in-memory or temporary SQLite database copies:
- From repository root: `backend\venv\Scripts\python.exe backend\tests\run_all.py`
- From backend directory: `venv\Scripts\python.exe tests\run_all.py`

## Directory Structure
- `backend/tests/`: Automated functional verification suites (`verify_*.py`).
- `backend/tests/measurements/`: Performance, latency, and savings benchmark scripts (`measure_*.py`).

## Important Notes
1. `verify_real_azure.py` requires real Azure credentials and is never executed automatically.
2. Scripts in `measurements/` must only run against an isolated throwaway database to prevent pollution.

