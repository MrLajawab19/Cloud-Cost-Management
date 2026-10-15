"""
measure_savings.py
──────────────────
Calculates total potential monthly and annualized savings across all unresolved
recommendations on the demo dataset, broken down by rule and service.
Imports actual functions from services.cleanup_advisor and services.savings_plan_optimiser.
"""

import sys
import os
from sqlalchemy import func

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True)

from config import get_settings
settings = get_settings()
settings.demo_mode = True

from database import SessionLocal
from models.account import CloudAccount
from models.cost_record import Recommendation
from services.cost_estimator import upsert_resources, seed_historical_data
from services.aws_collector import collect_demo_data
from services.azure_collector import collect_demo_data as collect_azure_demo_data
from services.cleanup_advisor import generate_recommendations
from services.savings_plan_optimiser import generate_sp_recommendations

def run_savings_audit():
    db = SessionLocal()
    try:
        account_id = "00000000-0000-0000-0000-demoaccount01"
        
        # 1. Ingest demo resources into DB
        resources = collect_demo_data() + collect_azure_demo_data()
        for r in resources:
            r["account_id"] = account_id
        upsert_resources(db, resources)
        seed_historical_data(db, account_id, days=45, min_days_threshold=100)

        # 2. Run actual cleanup advisor and savings plan optimizer
        generate_recommendations(db)
        generate_sp_recommendations(db, account_id)

        # 3. Query all unresolved recommendations for this demo dataset
        recs = (
            db.query(Recommendation)
            .filter(
                Recommendation.account_id == account_id,
                Recommendation.is_resolved == False,
            )
            .all()
        )

        total_monthly_savings = sum(r.potential_savings_usd or 0.0 for r in recs)
        total_upfront = sum(r.upfront_cost_usd or 0.0 for r in recs)

        # Breakdown by Rule (Issue)
        by_rule = {}
        for r in recs:
            by_rule.setdefault(r.issue, {"count": 0, "savings": 0.0, "service": r.service_type, "action": r.action})
            by_rule[r.issue]["count"] += 1
            by_rule[r.issue]["savings"] += (r.potential_savings_usd or 0.0)

        # Breakdown by Service
        by_service = {}
        for r in recs:
            by_service.setdefault(r.service_type, 0.0)
            by_service[r.service_type] += (r.potential_savings_usd or 0.0)

        print("=" * 80)
        print("RAW MEASURED OUTPUT: POTENTIAL SAVINGS AUDIT")
        print("DATA SOURCE: Synthetic Demo Dataset (11 AWS + 3 Azure demo resources)")
        print("=" * 80)
        print(f"Total Unresolved Recommendations : {len(recs)}")
        print(f"Total Potential Monthly Savings  : ${total_monthly_savings:,.2f} / month")
        print(f"Projected Annualized Savings     : ${total_monthly_savings * 12:,.2f} / year")
        if total_upfront > 0:
            print(f"Total Upfront Plan Commitments   : ${total_upfront:,.2f}")
        print("-" * 80)
        print("BREAKDOWN BY RECOMMENDATION RULE:")
        print(f"{'Rule (Issue)':<38} | {'Service':<8} | {'Count':<5} | {'Monthly Savings ($)':<20}")
        print("-" * 80)
        for issue, data in sorted(by_rule.items(), key=lambda x: -x[1]["savings"]):
            print(f"{issue:<38} | {data['service']:<8} | {data['count']:<5} | ${data['savings']:>18.2f}/mo")
        print("-" * 80)
        print("BREAKDOWN BY SERVICE TYPE:")
        print(f"{'Service':<15} | {'Monthly Savings ($)':<20} | {'Share (%)':<10}")
        print("-" * 80)
        for svc, amt in sorted(by_service.items(), key=lambda x: -x[1]):
            pct = (amt / total_monthly_savings * 100.0) if total_monthly_savings > 0 else 0.0
            print(f"{svc:<15} | ${amt:>18.2f}/mo | {pct:>8.1f}%")
        print("=" * 80)

    finally:
        db.close()

if __name__ == "__main__":
    run_savings_audit()
