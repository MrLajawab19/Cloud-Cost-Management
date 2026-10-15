"""
measure_refresh_time.py
───────────────────────
Measures execution time in seconds for each individual stage of the data collection,
cost estimation, recommendation, and ML detection pipeline, plus total refresh duration.
Imports actual functions from scheduler.py and services.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from config import get_settings
settings = get_settings()
settings.demo_mode = True

from database import SessionLocal
from models.user import User
from models.account import CloudAccount
from services import aws_collector, azure_collector
from services.cost_estimator import upsert_resources, record_daily_costs, seed_historical_data
from services.cleanup_advisor import generate_recommendations
from services.anomaly_detector import detect_anomalies
from services.savings_plan_optimiser import generate_sp_recommendations
from services.escalation_manager import process_auto_resizes, process_escalations

def run_refresh_benchmark():
    db = SessionLocal()
    try:
        # Ensure demo account exists
        user = db.query(User).first()
        if not user:
            user = User(email="benchmark@example.com", password_hash="dummy")
            db.add(user)
            db.commit()
            db.refresh(user)

        account_id = "00000000-0000-0000-0000-demoaccount01"
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
        if not acc:
            acc = CloudAccount(
                id=account_id,
                user_id=user.id,
                name="Demo_AWS_Account",
                provider="aws",
                region="us-east-1",
                access_key_id="DEMO_KEY",
                encrypted_secret_key="",
            )
            db.add(acc)
            db.commit()

        # ── Stage 1: AWS Data Collection (Demo) ─────────────────────
        t0 = time.perf_counter()
        aws_resources = aws_collector.collect_demo_data()
        t_aws = time.perf_counter() - t0

        # ── Stage 2: Azure Data Collection (Demo) ───────────────────
        t0 = time.perf_counter()
        azure_resources = azure_collector.collect_demo_data()
        t_az = time.perf_counter() - t0

        all_resources = aws_resources + azure_resources
        for r in all_resources:
            r["account_id"] = account_id

        # ── Stage 3: Database Upsert & Stale Resource Pruning ────────
        t0 = time.perf_counter()
        upsert_resources(db, all_resources, [account_id])
        t_upsert = time.perf_counter() - t0

        # ── Stage 4: Historical Data Backfill Seeding ───────────────
        t0 = time.perf_counter()
        seed_historical_data(db, account_id, days=45, min_days_threshold=100)
        t_seed = time.perf_counter() - t0

        # ── Stage 5: Daily Cost Snapshot Recording ───────────────────
        t0 = time.perf_counter()
        record_daily_costs(db, all_resources)
        t_record = time.perf_counter() - t0

        # ── Stage 6: Cleanup Advisor Recommendations (10 rules) ──────
        t0 = time.perf_counter()
        generate_recommendations(db)
        t_cleanup = time.perf_counter() - t0

        # ── Stage 7: Anomaly Detection (Z-Score + IQR) ───────────────
        t0 = time.perf_counter()
        detect_anomalies(db, [account_id])
        t_anom = time.perf_counter() - t0

        # ── Stage 8: Savings Plan Optimization ───────────────────────
        t0 = time.perf_counter()
        generate_sp_recommendations(db, account_id)
        t_sp = time.perf_counter() - t0

        # ── Stage 9: Automated Remediation & Escalations ─────────────
        t0 = time.perf_counter()
        process_auto_resizes(db)
        process_escalations(db)
        t_remed = time.perf_counter() - t0

        total_time = t_aws + t_az + t_upsert + t_seed + t_record + t_cleanup + t_anom + t_sp + t_remed

        print("=" * 75)
        print("RAW MEASURED OUTPUT: PIPELINE REFRESH TIME BENCHMARK")
        print("DATA SOURCE: Synthetic Demo Data Pipeline in SQLite")
        print("=" * 75)
        print(f"{'Pipeline Stage':<50} | {'Duration (s)':<12} | {'Share (%)':<8}")
        print("-" * 75)
        print(f"{'1. AWS Resource Collection (boto3 demo)':<50} | {t_aws:<12.5f} | {(t_aws/total_time)*100:>6.1f}%")
        print(f"{'2. Azure Resource Collection (SDK demo)':<50} | {t_az:<12.5f} | {(t_az/total_time)*100:>6.1f}%")
        print(f"{'3. Resource Table Upsert & Stale Pruning':<50} | {t_upsert:<12.5f} | {(t_upsert/total_time)*100:>6.1f}%")
        print(f"{'4. Historical Cost Data Seeding':<50} | {t_seed:<12.5f} | {(t_seed/total_time)*100:>6.1f}%")
        print(f"{'5. Daily Cost Snapshot Recording':<50} | {t_record:<12.5f} | {(t_record/total_time)*100:>6.1f}%")
        print(f"{'6. Cleanup Advisor Rule Evaluation':<50} | {t_cleanup:<12.5f} | {(t_cleanup/total_time)*100:>6.1f}%")
        print(f"{'7. Residual Anomaly Detection (FR-3)':<50} | {t_anom:<12.5f} | {(t_anom/total_time)*100:>6.1f}%")
        print(f"{'8. Savings Plan & RI Optimizer (FR-6)':<50} | {t_sp:<12.5f} | {(t_sp/total_time)*100:>6.1f}%")
        print(f"{'9. Auto-Remediation & Escalation Manager':<50} | {t_remed:<12.5f} | {(t_remed/total_time)*100:>6.1f}%")
        print("-" * 75)
        print(f"{'TOTAL END-TO-END PIPELINE REFRESH TIME':<50} | {total_time:<12.5f} | 100.0%")
        print("=" * 75)

    finally:
        db.close()

if __name__ == "__main__":
    run_refresh_benchmark()
