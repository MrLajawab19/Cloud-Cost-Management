"""Test environment bootstrap helper for backend/tests.
Ensures the backend directory is present in sys.path at index 0,
and exports canonical path references so moved test scripts can resolve
application modules, test assets, and the live database path.
"""
from pathlib import Path
import sys

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

