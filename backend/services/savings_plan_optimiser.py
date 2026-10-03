import logging
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from models.cost_record import Recommendation
from models.anomaly import Anomaly
from services.ml_predictor import predict_costs

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 14

_MOCK_PRICING = {
    "discount_pct": 0.30,  # 30% discount
    "upfront_pct": 0.50,   # 50% paid upfront
}

def generate_sp_recommendations(db: Session, account_id: str) -> List[Recommendation]:
    """
    Generate Savings Plan recommendations for stable services (FR-6).
    """
    recs = []
    
    # 1. Get 30-day baseline forecasts per service
    forecast_data = predict_costs(db, [account_id])
    per_service_forecast = forecast_data.get("per_service_forecast", [])
    forecast = {svc["service"]: float(svc["monthly_estimate_usd"]) for svc in per_service_forecast}
    
    # 2. Identify services with recent unresolved anomalies (FR-6.4)
    cutoff = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    recent_anomalies = db.query(Anomaly).filter(
        Anomaly.account_id == account_id,
        Anomaly.record_date >= cutoff.date(),
        Anomaly.is_resolved == False
    ).all()
    anomalous_services = {a.service_type for a in recent_anomalies}
    
    for srv, baseline_30d in forecast.items():
        if srv in anomalous_services:
            logger.info(f"Skipping SP for {srv} - anomalous within last {LOOKBACK_DAYS} days.")
            continue
            
        # Only evaluate if baseline is meaningful
        if baseline_30d < 50:
            continue
            
        # Synthetic pricing logic (Partial Upfront, 1-Year mock)
        discount_factor = 1.0 - _MOCK_PRICING.get("discount_pct", 0.30)
        upfront_pct = _MOCK_PRICING.get("upfront_pct", 0.50)
        monthly_pct = 1.0 - upfront_pct
        
        discounted_30d = baseline_30d * discount_factor
        monthly_sp_fee = discounted_30d * monthly_pct
        upfront_cost = discounted_30d * 12 * upfront_pct
        
        # Denominator guard
        monthly_savings = baseline_30d - monthly_sp_fee
        if monthly_savings <= 0:
            continue
            
        break_even_months = upfront_cost / monthly_savings
        
        # Only recommend if break-even is <= 8 months
        if break_even_months <= 8.0:
            payback_days = int(round(break_even_months * 30))
            
            # Delete existing SP recommendation for this service
            db.query(Recommendation).filter(
                Recommendation.account_id == account_id,
                Recommendation.service_type == srv,
                Recommendation.action == "Purchase Savings Plan"
            ).delete(synchronize_session=False)
            
            rec = Recommendation(
                account_id=account_id,
                resource_id=f"{srv}-SP-1YR",
                resource_name=f"{srv} 1-Year Savings Plan",
                service_type=srv,
                region="global",
                issue="No Commitment",
                description=f"Consistent {srv} usage detected. Purchasing a 1-Year Savings Plan can reduce effective costs by 30%.",
                action="Purchase Savings Plan",
                severity="medium",
                potential_savings_usd=monthly_savings,
                upfront_cost_usd=upfront_cost,
                payback_days=payback_days
            )
            db.add(rec)
            recs.append(rec)
            
    db.commit()
    logger.info(f"Generated {len(recs)} Savings Plan recommendations.")
    return recs
