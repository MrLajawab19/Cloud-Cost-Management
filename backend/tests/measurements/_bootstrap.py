"""Test environment bootstrap helper for backend/tests/measurements.
Ensures the backend directory is present in sys.path at index 0.
"""
from pathlib import Path
import sys

MEAS_DIR = Path(__file__).resolve().parent
TESTS_DIR = MEAS_DIR.parent
BACKEND_DIR = TESTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

