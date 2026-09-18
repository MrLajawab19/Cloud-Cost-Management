"""
routes/predictions.py — GET /predictions and GET /predictions/per-service endpoints.

FR-2.1 / FR-2.5: /predictions/per-service returns per-service breakdown + attribution.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.ml_predictor import predict_costs
from services.security import get_current_user
from models.user import User
from models.account import AWSAccount

router = APIRouter(prefix="/predictions", tags=["Predictions"])


def get_user_account_ids(
    db: Session,
    current_user: User,
    account_id: Optional[str] = None,
) -> List[str]:
    if account_id:
        acc = db.query(AWSAccount).filter(
            AWSAccount.id == account_id,
            AWSAccount.user_id == current_user.id,
        ).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(AWSAccount).filter(AWSAccount.user_id == current_user.id).all()
    return [acc.id for acc in accounts]


@router.get("/")
def get_predictions(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full FR-2 cost forecast response.

    Returns:
      historical             — past daily actuals [{date, cost}]
      forecast               — winning model 30-day forecast [{date, cost}]
      forecast_poly          — polynomial regression forecast
      forecast_hw            — Holt-Winters forecast
      model_comparison       — MAPE/RMSE comparison (null if < 10 days of data)
      per_service_forecast   — per-service breakdown, normalized to headline total
      monthly_estimate_usd   — projected total for next 30 days
      model_info             — training metadata, winner, accuracy metrics
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    return predict_costs(db, account_ids)


@router.get("/per-service")
def get_per_service_forecast(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    FR-2.1 / FR-2.4 / FR-2.5: Per-service cost forecast with attribution.

    Returns only the per_service_forecast slice, convenient for dedicated
    frontend components that don't need the full prediction payload.

    Each service entry:
      service              — EC2 | S3 | RDS | Lambda
      forecast             — [{date, cost}] normalized to headline total
      attribution_pct      — % of total projected spend driven by this service
      monthly_estimate_usd — 30-day projected spend for this service
      is_normalized        — always true (sums exactly to headline)
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    result = predict_costs(db, account_ids)
    return {
        "per_service_forecast":  result["per_service_forecast"],
        "monthly_estimate_usd":  result["monthly_estimate_usd"],
        "model_comparison":      result["model_comparison"],
    }
