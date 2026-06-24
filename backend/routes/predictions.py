"""
routes/predictions.py — GET /predictions endpoint.
Returns ML-based cost forecast for the next 30 days.
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

def get_user_account_ids(db: Session, current_user: User, account_id: Optional[str] = None) -> List[str]:
    if account_id:
        acc = db.query(AWSAccount).filter(AWSAccount.id == account_id, AWSAccount.user_id == current_user.id).first()
        if not acc:
            raise HTTPException(status_code=403, detail="Account not found or access denied")
        return [account_id]
    accounts = db.query(AWSAccount).filter(AWSAccount.user_id == current_user.id).all()
    return [acc.id for acc in accounts]

@router.get("/")
def get_predictions(
    account_id: Optional[str] = Query(None, description="Filter by specific AWS account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns ML-based cost predictions for the next 30 days.

    Response:
      - historical: [{date, cost}]   — past daily costs (from DB)
      - forecast:   [{date, cost}]   — predicted future costs
      - monthly_estimate_usd        — total predicted spend next month
      - model_info                  — training metadata (type, r2, days)
    """
    account_ids = get_user_account_ids(db, current_user, account_id)
    return predict_costs(db, account_ids)
