from sqlalchemy.orm import Session
from database import SessionLocal
from models.account import AWSAccount
import services.savings_plan_optimiser

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    
    print("\n--- 4. Denominator Guard Case ---")
    # Temporarily inject a synthetic CommitmentPricing entry where the monthly SP fee exceeds the on-demand forecast
    # We do this by making the discount negative (a price hike) and the upfront 0% (so the monthly fee takes the full brunt)
    services.savings_plan_optimiser._MOCK_PRICING["discount_pct"] = -0.50 # 50% premium
    services.savings_plan_optimiser._MOCK_PRICING["upfront_pct"] = 0.0 # 0% upfront, all monthly
    
    recs = services.savings_plan_optimiser.generate_sp_recommendations(db, account.id)
    print(f"  Generated SP recommendations with premium pricing: {len(recs)}")
    if len(recs) == 0:
        print("  SUCCESS: Denominator guard fired correctly, no recommendations generated.")
    else:
        print("  FAILURE: Recommendations generated despite monthly_savings <= 0.")
        
    # Revert mock
    services.savings_plan_optimiser._MOCK_PRICING["discount_pct"] = 0.30
    services.savings_plan_optimiser._MOCK_PRICING["upfront_pct"] = 0.50

if __name__ == "__main__":
    main()
