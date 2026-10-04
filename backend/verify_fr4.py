import sys
import os

from sqlalchemy.orm import Session
from database import SessionLocal
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation
from services.what_if_simulator import run_simulation
from services.ml_predictor import predict_costs
from services.cleanup_advisor import generate_recommendations

def main():
    db = SessionLocal()
    
    account = db.query(CloudAccount).first()
    user = db.query(User).filter(User.id == account.user_id).first()
    
    if not account:
        print("No accounts found.")
        sys.exit(1)
        
    rec = db.query(Recommendation).filter(Recommendation.account_id == account.id).first()
    if not rec:
        print("No recommendations found. Generating...")
        generate_recommendations(db)
        rec = db.query(Recommendation).filter(Recommendation.account_id == account.id).first()
        if not rec:
            print("Still no recommendations. Forcing dummy.")
            rec = Recommendation(
                account_id=account.id,
                resource_id="i-dummy",
                resource_name="Dummy Instance",
                service_type="EC2",
                region="us-east-1",
                issue="Underutilized",
                description="dummy description",
                action="dummy action",
                potential_savings_usd=15.0,
                severity="low"
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            
    print(f"--- 1. Testing run_simulation with real recommendation ({rec.id}) ---")
    res1 = run_simulation(db, account.id, rec.id)
    print(f"baseline_30d_usd: {res1.baseline_30d_usd}")
    print(f"simulated_30d_usd: {res1.simulated_30d_usd}")
    print(f"delta_usd: {res1.delta_usd}")
    print(f"delta_pct: {res1.delta_pct}")
    print(f"payback_days: {res1.payback_days}")
    
    print(f"\n--- 2. Testing max(0, ...) floor ---")
    orig_savings = rec.potential_savings_usd
    rec.potential_savings_usd = res1.baseline_30d_usd + 100.0
    db.commit()
    
    res2 = run_simulation(db, account.id, rec.id)
    print(f"Savings set to: {rec.potential_savings_usd} (baseline is {res1.baseline_30d_usd})")
    print(f"simulated_30d_usd: {res2.simulated_30d_usd}")
    print(f"delta_usd: {res2.delta_usd}")
    print(f"delta_pct: {res2.delta_pct}")
    
    rec.potential_savings_usd = orig_savings
    db.commit()
    
    print(f"\n--- 4. Confirming numbers are directionally sane ---")
    forecast_data = predict_costs(db, [account.id])
    per_service = forecast_data.get("per_service_forecast", [])
    
    pred_baseline = 0.0
    for svc in per_service:
        if svc["service"] == rec.service_type:
            pred_baseline = svc["monthly_estimate_usd"]
            break
            
    print(f"Service: {rec.service_type}")
    print(f"run_simulation baseline_30d_usd: {res1.baseline_30d_usd}")
    print(f"/predictions/per-service monthly_estimate_usd: {pred_baseline}")
    print(f"Difference: {abs(res1.baseline_30d_usd - pred_baseline):.4f}")

    user2 = db.query(User).filter(User.id != account.user_id).first()
    if not user2:
        user2 = User(email="test2@example.com", hashed_password="pw")
        db.add(user2)
        db.commit()
        db.refresh(user2)
        
    from services.security import create_access_token
    t1 = create_access_token({"sub": str(user.id)})
    t2 = create_access_token({"sub": str(user2.id)})
    
    print(f"\n--- Setup for API Testing ---")
    print(f"TOKEN1={t1}")
    print(f"TOKEN2={t2}")
    print(f"REC_ID={rec.id}")

if __name__ == '__main__':
    main()
