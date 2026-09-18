"""
services/ml_predictor.py
─────────────────────────
Implements FR-2 (Explainable Forecasting) in full:

  FR-2.1  Per-service 30-day forecast (normalized to total)
  FR-2.2  Two models: Polynomial Regression vs Holt's Double Exponential Smoothing
  FR-2.3  MAPE and RMSE on held-out window
          Rule: held_out = max(3, round(0.20 * n_days))
          Comparison skipped if n_days < MIN_COMPARISON_DAYS (10)
  FR-2.4  Service-contribution attribution (% of total)
  FR-2.5  Budget-planning: per-service breakdown with monthly estimates

Technology note:
  Model 2 uses Holt's additive double exponential smoothing implemented in
  pure NumPy (grid-searched alpha/beta). statsmodels ExponentialSmoothing was
  considered but its Fortran/LAPACK DLL extension is blocked by Windows
  Application Control on this machine. The pure-NumPy implementation is
  mathematically equivalent (level + trend) and dependency-free.
  Attribution uses service-contribution decomposition (per-service models
  normalised to headline) rather than SHAP, since the single time-index
  feature matrix would make SHAP trivially uninformative.
"""

import logging
import numpy as np
from datetime import date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.cost_record import CostRecord

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────
MIN_TRAINING_DAYS   = 7   # Minimum data points to train any model
MIN_COMPARISON_DAYS = 10  # = MIN_TRAINING_DAYS + min held-out (3)
PREDICT_DAYS        = 30  # Forward-forecast horizon


# ══════════════════════════════════════════════════════════════════
#  HELD-OUT WINDOW (single canonical rule — FR-2.3)
# ══════════════════════════════════════════════════════════════════

def _held_out_size(n_days: int) -> int:
    """
    Consistent held-out window: max(3, round(0.20 * n_days))

    n=10  → max(3, round(2.0)) = 3   → train on 7
    n=15  → max(3, round(3.0)) = 3   → train on 12
    n=30  → max(3, round(6.0)) = 6   → train on 24
    n=50  → max(3, round(10))  = 10  → train on 40
    """
    return max(3, round(0.20 * n_days))


# ══════════════════════════════════════════════════════════════════
#  DATA LOADING
# ══════════════════════════════════════════════════════════════════

def _load_total_data(db: Session, account_ids: List[str]) -> Tuple[np.ndarray, np.ndarray, List[date]]:
    """Aggregate daily cost across all services."""
    if not account_ids:
        return np.array([]), np.array([]), []

    rows = (
        db.query(
            CostRecord.record_date,
            func.sum(CostRecord.daily_cost_usd).label("total"),
        )
        .filter(CostRecord.account_id.in_(account_ids))
        .group_by(CostRecord.record_date)
        .order_by(CostRecord.record_date)
        .all()
    )
    if not rows:
        return np.array([]), np.array([]), []

    base  = rows[0].record_date
    X     = np.array([(r.record_date - base).days for r in rows], dtype=float)
    y     = np.array([float(r.total) for r in rows], dtype=float)
    dates = [r.record_date for r in rows]
    return X, y, dates


def _load_per_service_data(db: Session, account_ids: List[str]) -> Dict[str, Tuple[np.ndarray, np.ndarray, List[date]]]:
    """Aggregate daily cost grouped by service_type."""
    if not account_ids:
        return {}

    rows = (
        db.query(
            CostRecord.service_type,
            CostRecord.record_date,
            func.sum(CostRecord.daily_cost_usd).label("total"),
        )
        .filter(CostRecord.account_id.in_(account_ids))
        .group_by(CostRecord.service_type, CostRecord.record_date)
        .order_by(CostRecord.service_type, CostRecord.record_date)
        .all()
    )

    bucket: Dict[str, list] = {}
    for row in rows:
        bucket.setdefault(row.service_type, []).append((row.record_date, float(row.total)))

    result = {}
    for svc, entries in bucket.items():
        dates = [e[0] for e in entries]
        y     = np.array([e[1] for e in entries], dtype=float)
        base  = dates[0]
        X     = np.array([(d - base).days for d in dates], dtype=float)
        result[svc] = (X, y, dates)
    return result


# ══════════════════════════════════════════════════════════════════
#  MODEL 1 — Polynomial Regression (degree 2, scikit-learn)
# ══════════════════════════════════════════════════════════════════

def _train_poly(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.pipeline import make_pipeline
    m = make_pipeline(PolynomialFeatures(degree=2, include_bias=False), LinearRegression())
    m.fit(X.reshape(-1, 1), y)
    return m


def _predict_poly(model, X_future: np.ndarray) -> np.ndarray:
    return np.maximum(model.predict(X_future.reshape(-1, 1)), 0.0)


# ══════════════════════════════════════════════════════════════════
#  MODEL 2 — Double Exponential Smoothing (Holt's method, pure NumPy)
#
#  Uses Holt's additive trend (Holt-Winters without seasonality).
#  Pure NumPy — avoids statsmodels Fortran/LAPACK DLL issues on Windows.
#  Optimal alpha/beta found via grid search minimizing MSE on training data.
# ══════════════════════════════════════════════════════════════════

class _HoltModel:
    """Fitted Holt double exponential smoothing model (additive trend)."""
    def __init__(self, alpha: float, beta: float, level: float, trend: float):
        self.alpha = alpha
        self.beta  = beta
        self.level = level
        self.trend = trend

    def forecast(self, steps: int) -> np.ndarray:
        preds = np.empty(steps)
        for h in range(1, steps + 1):
            preds[h - 1] = self.level + h * self.trend
        return np.maximum(preds, 0.0)


def _train_hw(y: np.ndarray) -> _HoltModel:
    """
    Fit Holt double exponential smoothing via grid search.
    alpha controls level smoothing; beta controls trend smoothing.
    Returns the fitted model with the lowest training MSE.
    """
    best_mse   = float("inf")
    best_model = None

    alphas = np.arange(0.1, 1.0, 0.1)
    betas  = np.arange(0.0, 0.5, 0.1)

    for alpha in alphas:
        for beta in betas:
            # Initialise
            lvl   = float(y[0])
            trend = float(y[1] - y[0]) if len(y) > 1 else 0.0
            errors = []

            for t in range(1, len(y)):
                prev_lvl   = lvl
                prev_trend = trend
                lvl        = alpha * float(y[t]) + (1 - alpha) * (prev_lvl + prev_trend)
                trend      = beta  * (lvl - prev_lvl) + (1 - beta) * prev_trend
                pred       = prev_lvl + prev_trend
                errors.append((float(y[t]) - pred) ** 2)

            mse = float(np.mean(errors)) if errors else float("inf")
            if mse < best_mse:
                best_mse   = mse
                best_model = _HoltModel(alpha, beta, lvl, trend)

    if best_model is None:
        # Trivial fallback
        best_model = _HoltModel(0.3, 0.1, float(y[-1]), 0.0)

    return best_model


def _predict_hw(model: _HoltModel, steps: int) -> np.ndarray:
    return model.forecast(steps)


# ══════════════════════════════════════════════════════════════════
#  EVALUATION (FR-2.3)
# ══════════════════════════════════════════════════════════════════

def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """MAPE — ignores points where actual < 1e-6 to avoid /0."""
    mask = actual > 1e-6
    if mask.sum() == 0:
        return 999.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def _evaluate_models(X: np.ndarray, y: np.ndarray) -> Optional[Dict[str, Any]]:
    """
    Evaluate both models on a held-out window.

    Canonical rule: held_out = max(3, round(0.20 * n_days))
    Skip entirely if n_days < MIN_COMPARISON_DAYS (10), because
    training window would be below MIN_TRAINING_DAYS (7).

    Returns None when skipped; otherwise comparison dict.
    """
    n = len(X)
    if n < MIN_COMPARISON_DAYS:
        return None

    held_out  = _held_out_size(n)
    train_end = n - held_out

    X_tr, y_tr = X[:train_end], y[:train_end]
    X_ho, y_ho = X[train_end:], y[train_end:]

    def eval_poly():
        try:
            m = _train_poly(X_tr, y_tr)
            p = _predict_poly(m, X_ho)
            return {"mape": round(_mape(y_ho, p), 2), "rmse": round(_rmse(y_ho, p), 4)}
        except Exception as e:
            logger.warning(f"Poly evaluation failed: {e}")
            return {"mape": 999.0, "rmse": 999.0}

    def eval_hw():
        try:
            m = _train_hw(y_tr)
            p = _predict_hw(m, held_out)
            return {"mape": round(_mape(y_ho, p), 2), "rmse": round(_rmse(y_ho, p), 4)}
        except Exception as e:
            logger.warning(f"HW evaluation failed: {e}")
            return {"mape": 999.0, "rmse": 999.0}

    poly_r = eval_poly()
    hw_r   = eval_hw()

    winner_key = "poly" if poly_r["mape"] <= hw_r["mape"] else "hw"
    return {
        "winner":        "Polynomial Regression" if winner_key == "poly" else "Holt-Winters",
        "winner_key":    winner_key,
        "held_out_days": held_out,
        "poly_mape":     poly_r["mape"],
        "poly_rmse":     poly_r["rmse"],
        "hw_mape":       hw_r["mape"],
        "hw_rmse":       hw_r["rmse"],
    }


# ══════════════════════════════════════════════════════════════════
#  TOTAL FORECAST
# ══════════════════════════════════════════════════════════════════

def _forecast_total(
    X: np.ndarray,
    y: np.ndarray,
    dates: List[date],
    comparison: Optional[Dict],
) -> Tuple[List[Dict], List[Dict], Dict]:
    """Train both models on all data and produce 30-day forecasts."""
    last_idx  = int(X[-1])
    last_date = dates[-1]
    future_X  = np.arange(last_idx + 1, last_idx + 1 + PREDICT_DAYS, dtype=float)
    fut_dates = [last_date + timedelta(days=i + 1) for i in range(PREDICT_DAYS)]

    # Polynomial
    r2_poly = 0.0
    try:
        m_poly  = _train_poly(X, y)
        r2_poly = float(m_poly.score(X.reshape(-1, 1), y))
        preds_p = _predict_poly(m_poly, future_X)
    except Exception as e:
        logger.error(f"Poly total forecast failed: {e}")
        preds_p = np.full(PREDICT_DAYS, float(np.mean(y)))

    forecast_poly = [
        {"date": str(d), "cost": round(float(c), 4)}
        for d, c in zip(fut_dates, preds_p)
    ]

    # Holt-Winters
    try:
        m_hw    = _train_hw(y)
        preds_h = _predict_hw(m_hw, PREDICT_DAYS)
    except Exception as e:
        logger.error(f"HW total forecast failed: {e}")
        preds_h = np.full(PREDICT_DAYS, float(np.mean(y)))

    forecast_hw = [
        {"date": str(d), "cost": round(float(c), 4)}
        for d, c in zip(fut_dates, preds_h)
    ]

    model_info: Dict[str, Any] = {
        "training_days":  len(X),
        "r2_score_poly":  round(r2_poly, 4),
    }
    if comparison:
        model_info.update({
            "winner":        comparison["winner"],
            "winner_key":    comparison["winner_key"],
            "held_out_days": comparison["held_out_days"],
            "poly_mape":     comparison["poly_mape"],
            "poly_rmse":     comparison["poly_rmse"],
            "hw_mape":       comparison["hw_mape"],
            "hw_rmse":       comparison["hw_rmse"],
        })

    return forecast_poly, forecast_hw, model_info


# ══════════════════════════════════════════════════════════════════
#  PER-SERVICE FORECAST (FR-2.1, FR-2.4, FR-2.5)
# ══════════════════════════════════════════════════════════════════

def _forecast_per_service(
    db: Session,
    account_ids: List[str],
    headline_forecast: List[Dict],
) -> List[Dict]:
    """
    Forecast each service independently, then normalize so per-service
    values sum EXACTLY to the headline forecast on every day.

    is_normalized=True is always set in the response so the UI and
    any consumers can assert consistency without a separate flag check.
    """
    service_data = _load_per_service_data(db, account_ids)
    if not service_data:
        return []

    fut_dates        = [f["date"] for f in headline_forecast]
    headline_totals  = np.array([f["cost"] for f in headline_forecast], dtype=float)

    raw: Dict[str, np.ndarray] = {}

    for svc, (X, y, dates) in service_data.items():
        n         = len(X)
        last_idx  = int(X[-1])
        future_X  = np.arange(last_idx + 1, last_idx + 1 + PREDICT_DAYS, dtype=float)
        preds: Optional[np.ndarray] = None

        if n >= MIN_TRAINING_DAYS:
            try:
                m     = _train_hw(y) if n >= 14 else _train_poly(X, y)
                preds = _predict_hw(m, PREDICT_DAYS) if n >= 14 else _predict_poly(m, future_X)
            except Exception as e:
                logger.warning(f"Per-service model ({svc}) failed: {e}")

        if preds is None:
            avg   = float(np.mean(y)) if n > 0 else 0.0
            preds = np.full(PREDICT_DAYS, avg)

        raw[svc] = np.maximum(preds, 0.0)

    services      = list(raw.keys())
    matrix        = np.array([raw[s] for s in services])           # (n_svc, PREDICT_DAYS)
    raw_day_sums  = matrix.sum(axis=0)                              # (PREDICT_DAYS,)

    # Scale factors: match each day to the headline total
    scale_factors = np.where(raw_day_sums > 1e-9, headline_totals / raw_day_sums, 1.0)
    norm_matrix   = matrix * scale_factors                          # (n_svc, PREDICT_DAYS)

    total_30d = float(headline_totals.sum())

    result = []
    for i, svc in enumerate(services):
        svc_30d     = float(norm_matrix[i].sum())
        attribution = round((svc_30d / total_30d * 100) if total_30d > 1e-9 else 0.0, 1)
        result.append({
            "service":              svc,
            "forecast":             [
                {"date": d, "cost": round(float(norm_matrix[i][j]), 4)}
                for j, d in enumerate(fut_dates)
            ],
            "attribution_pct":      attribution,
            "monthly_estimate_usd": round(svc_30d, 2),
            "is_normalized":        True,
        })

    result.sort(key=lambda x: x["attribution_pct"], reverse=True)
    return result


# ══════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def predict_costs(db: Session, account_ids: List[str]) -> Dict[str, Any]:
    """
    Full FR-2 prediction response.

    Backward-compatible fields (shape unchanged):
        historical, forecast, monthly_estimate_usd, model_info

    New FR-2 fields:
        forecast_poly       — polynomial model 30-day series
        forecast_hw         — Holt-Winters 30-day series
        model_comparison    — MAPE/RMSE dict (null if < 10 days of data)
        per_service_forecast — normalized per-service breakdown
    """
    X, y, dates = _load_total_data(db, account_ids)

    # Historical (always returned)
    historical = [
        {"date": str(d), "cost": round(float(c), 4)}
        for d, c in zip(dates, y)
    ]

    # Not enough data → flat-average fallback
    if len(X) < MIN_TRAINING_DAYS:
        avg        = float(np.mean(y)) if len(y) > 0 else 0.0
        today      = date.today()
        flat_fcst  = [
            {"date": str(today + timedelta(days=i + 1)), "cost": round(avg, 4), "is_estimate": True}
            for i in range(PREDICT_DAYS)
        ]
        return {
            "historical":           historical,
            "forecast":             flat_fcst,
            "forecast_poly":        flat_fcst,
            "forecast_hw":          flat_fcst,
            "per_service_forecast": [],
            "model_comparison":     None,
            "monthly_estimate_usd": round(avg * PREDICT_DAYS, 2),
            "model_info": {
                "type":          "flat_average",
                "training_days": len(X),
                "note": (
                    f"Need >= {MIN_TRAINING_DAYS} days for ML prediction; "
                    f">= {MIN_COMPARISON_DAYS} days for model comparison."
                ),
            },
        }

    # Model comparison on held-out window (FR-2.3)
    comparison = _evaluate_models(X, y)

    # Train both on full data
    forecast_poly, forecast_hw, model_info = _forecast_total(X, y, dates, comparison)

    # Headline = winning model
    if comparison and comparison["winner_key"] == "hw":
        headline_forecast = forecast_hw
        model_info["type"] = "holt_winters"
    else:
        headline_forecast = forecast_poly
        model_info["type"] = "polynomial_regression_deg2"

    monthly_estimate = round(sum(f["cost"] for f in headline_forecast), 2)

    # Per-service, normalized (FR-2.1, FR-2.4, FR-2.5)
    per_service = _forecast_per_service(db, account_ids, headline_forecast)

    logger.info(
        "FR-2 predict_costs: %d training days | comparison=%s | winner=%s | services=%s",
        len(X),
        "yes" if comparison else f"skipped (<{MIN_COMPARISON_DAYS} days)",
        model_info.get("winner", "N/A"),
        [p["service"] for p in per_service],
    )

    return {
        "historical":           historical,
        "forecast":             headline_forecast,
        "forecast_poly":        forecast_poly,
        "forecast_hw":          forecast_hw,
        "per_service_forecast": per_service,
        "model_comparison":     comparison,
        "monthly_estimate_usd": monthly_estimate,
        "model_info":           model_info,
    }
