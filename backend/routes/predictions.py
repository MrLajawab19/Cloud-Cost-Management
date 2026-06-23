"""
routes/predictions.py — GET /predictions endpoint.
Returns ML-based cost forecast for the next 30 days.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.ml_predictor import predict_costs

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.get("/")
def get_predictions(db: Session = Depends(get_db)):
    """
    Returns ML-based cost predictions for the next 30 days.

    Response:
      - historical: [{date, cost}]   — past daily costs (from DB)
      - forecast:   [{date, cost}]   — predicted future costs
      - monthly_estimate_usd        — total predicted spend next month
      - model_info                  — training metadata (type, r2, days)
    """
    return predict_costs(db)
