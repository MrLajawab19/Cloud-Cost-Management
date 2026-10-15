"""
measure_api_latency.py
──────────────────────
Benchmarks API response latency (avg, p50, p95, min, max) across key dashboard endpoints
executing 30 real HTTP requests per endpoint against the FastAPI application loaded with demo data.
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from config import get_settings
settings = get_settings()
settings.demo_mode = True

from fastapi.testclient import TestClient
from main import app
from database import SessionLocal
from models.user import User
from models.account import CloudAccount
from services.security import create_access_token
from services.cost_estimator import seed_historical_data, upsert_resources
from services.aws_collector import collect_demo_data
from services.azure_collector import collect_demo_data as collect_azure_demo_data
from services.cleanup_advisor import generate_recommendations
from services.anomaly_detector import detect_anomalies

DASHBOARD_ENDPOINTS = [
    "/health",
    "/resources/summary",
    "/resources/?limit=50",
    "/costs/summary",
    "/costs/trend?days=30",
    "/costs/by-service",
    "/costs/top-resources?limit=10",
    "/recommendations/",
    "/recommendations/summary",
    "/predictions/",
    "/anomalies/",
    "/anomalies/summary",
]

def setup_demo_environment():
    """Ensure user, demo account, resources, cost records, and recommendations exist."""
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            user = User(email="test@example.com", password_hash="dummy")
            db.add(user)
            db.commit()
            db.refresh(user)

        account_id = "00000000-0000-0000-0000-demoaccount01"
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
        if not acc:
            acc = CloudAccount(
                id=account_id,
                user_id=user.id,
                name="Demo_Account",
                provider="aws",
                region="us-east-1",
                access_key_id="DEMO_KEY",
                encrypted_secret_key="",
            )
            db.add(acc)
            db.commit()

        # Ingest demo resources
        res = collect_demo_data() + collect_azure_demo_data()
        for r in res:
            r["account_id"] = account_id
        upsert_resources(db, res)
        seed_historical_data(db, account_id, days=45, min_days_threshold=100)
        generate_recommendations(db)
        detect_anomalies(db, [account_id])

        # Generate JWT Bearer token
        token = create_access_token({"sub": str(user.id)})
        return token
    finally:
        db.close()

def run_latency_benchmark(num_requests=30):
    token = setup_demo_environment()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    print("=" * 80)
    print("RAW MEASURED OUTPUT: DASHBOARD API LATENCY BENCHMARK")
    print("DATA SOURCE: Synthetic Demo Data in SQLite/FastAPI TestClient")
    print(f"BENCHMARK SPEC: {num_requests} requests per endpoint | Authenticated with JWT")
    print("=" * 80)
    print(f"{'Endpoint':<32} | {'Avg (ms)':<9} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'Min (ms)':<8} | {'Max (ms)':<8}")
    print("-" * 80)

    all_latencies = []

    for ep in DASHBOARD_ENDPOINTS:
        latencies = []
        for _ in range(num_requests):
            t0 = time.perf_counter()
            response = client.get(ep, headers=headers)
            t1 = time.perf_counter()
            if response.status_code == 200:
                elapsed_ms = (t1 - t0) * 1000.0
                latencies.append(elapsed_ms)
                all_latencies.append(elapsed_ms)
            else:
                print(f"ERROR: {ep} returned HTTP {response.status_code}")
                break

        if latencies:
            avg_l = float(np.mean(latencies))
            p50_l = float(np.percentile(latencies, 50))
            p95_l = float(np.percentile(latencies, 95))
            min_l = float(np.min(latencies))
            max_l = float(np.max(latencies))
            print(f"{ep:<32} | {avg_l:<9.2f} | {p50_l:<9.2f} | {p95_l:<9.2f} | {min_l:<8.2f} | {max_l:<8.2f}")

    print("-" * 80)
    overall_avg = float(np.mean(all_latencies))
    overall_p50 = float(np.percentile(all_latencies, 50))
    overall_p95 = float(np.percentile(all_latencies, 95))
    print(f"{'OVERALL ACROSS ALL ENDPOINTS':<32} | {overall_avg:<9.2f} | {overall_p50:<9.2f} | {overall_p95:<9.2f} | {float(np.min(all_latencies)):<8.2f} | {float(np.max(all_latencies)):<8.2f}")
    print("=" * 80)

if __name__ == "__main__":
    run_latency_benchmark(num_requests=30)
