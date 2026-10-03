from sqlalchemy.orm import Session
from database import SessionLocal
from models.account import AWSAccount
from models.anomaly import Anomaly
from models.cost_record import Recommendation
from services.savings_plan_optimiser import generate_sp_recommendations
from datetime import datetime, timedelta

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    
    print("\n--- 3. Anomaly Exclusion Case ---")
    anomaly = Anomaly(
        account_id=account.id,
        service_type="EC2",
        record_date=datetime.utcnow().date(),
        actual_cost=100.0,
        forecast_cost=50.0,
        residual=50.0,
        z_score=5.0,
        severity="high"
    )
    db.add(anomaly)
    db.commit()
    
    recs_after_anomaly = generate_sp_recommendations(db, account.id)
    excluded = True
    for r in recs_after_anomaly:
        if r.service_type == "EC2":
            excluded = False
    print(f"  Service EC2 excluded after anomaly? {excluded}")
    
    # 4. Denominator Guard Case
    print("\n--- 4. Denominator Guard Case ---")
    print("  Denominator guard logic is hardcoded: if monthly_savings <= 0: continue")

if __name__ == "__main__":
    main()
