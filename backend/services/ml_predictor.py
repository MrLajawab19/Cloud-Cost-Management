"""
services/ml_predictor.py
─────────────────────────
Trains a Linear Regression model on historical daily cost data
and predicts costs for the next 30 days.

Model is retrained on every prediction call if enough data exists (≥14 days).
Uses only scikit-learn + numpy — no heavy dependencies.
"""

import logging
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.cost_record import CostRecord

logger = logging.getLogger(__name__)

MIN_TRAINING_DAYS = 7    # Minimum days of data needed to train
PREDICT_DAYS      = 30   # How many days ahead to predict


def _load_training_data(db: Session) -> tuple:
    """
    Load aggregated daily cost totals from CostRecord table.
    Returns (X: day indices, y: total cost per day, dates).
    """
    rows = (
        db.query(
            CostRecord.record_date,
            func.sum(CostRecord.daily_cost_usd).label("total"),
        )
        .group_by(CostRecord.record_date)
        .order_by(CostRecord.record_date)
        .all()
    )

    if not rows:
        return np.array([]), np.array([]), []

    base_date = rows[0].record_date
    X = np.array([(r.record_date - base_date).days for r in rows], dtype=float)
    y = np.array([float(r.total) for r in rows], dtype=float)
    dates = [r.record_date for r in rows]

    return X, y, dates


def predict_costs(db: Session) -> Dict[str, Any]:
    """
    Train a polynomial regression model on historical data and predict
    the next 30 days of daily costs.

    Returns a dict with:
      - historical: [{date, cost}] — actual past data
      - forecast:   [{date, cost}] — predicted future data
      - model_info: training metadata
    """
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.pipeline import make_pipeline

    X, y, dates = _load_training_data(db)

    # ── Historical data (always returned) ────────────────────────
    historical = [
        {"date": str(d), "cost": round(float(c), 4)}
        for d, c in zip(dates, y)
    ]

    # ── Not enough data: return trend line based on current costs ─
    if len(X) < MIN_TRAINING_DAYS:
        logger.info(
            f"Not enough historical data ({len(X)} days). "
            f"Need {MIN_TRAINING_DAYS}. Using flat estimate."
        )
        avg_daily = float(np.mean(y)) if len(y) > 0 else 1.0
        today = date.today()
        forecast = [
            {
                "date": str(today + timedelta(days=i + 1)),
                "cost": round(avg_daily, 4),
                "is_estimate": True,
            }
            for i in range(PREDICT_DAYS)
        ]
        return {
            "historical": historical,
            "forecast": forecast,
            "model_info": {
                "type": "flat_average",
                "training_days": len(X),
                "note": f"Need at least {MIN_TRAINING_DAYS} days of data for ML prediction.",
            },
        }

    # ── Train polynomial regression (degree 2) ───────────────────
    degree = 2
    model = make_pipeline(
        PolynomialFeatures(degree=degree, include_bias=False),
        LinearRegression(),
    )
    X_reshaped = X.reshape(-1, 1)
    model.fit(X_reshaped, y)

    # In-sample score
    r2 = model.score(X_reshaped, y)
    logger.info(f"ML model trained. R²={r2:.4f}, training_days={len(X)}")

    # ── Predict next 30 days ──────────────────────────────────────
    last_day_idx = int(X[-1])
    last_date    = dates[-1]

    future_X     = np.arange(last_day_idx + 1, last_day_idx + 1 + PREDICT_DAYS, dtype=float)
    future_preds = model.predict(future_X.reshape(-1, 1))

    forecast = []
    for i, pred in enumerate(future_preds):
        forecast.append({
            "date": str(last_date + timedelta(days=i + 1)),
            "cost": round(max(0.0, float(pred)), 4),  # Clamp negatives to 0
        })

    # ── 30-day total estimate ─────────────────────────────────────
    monthly_estimate = round(sum(f["cost"] for f in forecast), 2)

    return {
        "historical": historical,
        "forecast": forecast,
        "monthly_estimate_usd": monthly_estimate,
        "model_info": {
            "type": f"polynomial_regression_deg{degree}",
            "training_days": len(X),
            "r2_score": round(r2, 4),
        },
    }
