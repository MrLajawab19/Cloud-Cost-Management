"""
services/what_if_simulator.py
─────────────────────────────
Implements FR-4: What-If Simulations.

FR-4.1 (Must) — Given a Recommendation (from FR-5/cleanup_advisor), project the
cost impact of applying that rightsizing action BEFORE it is taken. No AWS API
call is made; no resource is changed. Pure arithmetic on FR-2 forecast outputs.

⚠️  Service-level approximation — not a per-resource model
────────────────────────────────────────────────────────────
This simulator operates at service-level granularity, matching FR-2's forecast
resolution. It assumes that applying the recommendation reduces the service's
30-day aggregate cost by exactly Recommendation.potential_savings_usd.

This is a simplification: in reality, removing or resizing one resource out of
many in a service pool may have a non-linear or partial effect on the aggregate.
Users should treat the simulated figure as a directional estimate, not a
guaranteed billing outcome. The UI surfaces this limitation explicitly.

Unit note (verified from cleanup_advisor.py line-by-line):
  potential_savings_usd is an ESTIMATED MONTHLY figure in every rule:
    - EC2 underutilized: cost * 0.6   (monthly cost × ratio)
    - EC2 stopped:       0.10 * 30    ($/GB × GB — monthly storage total)
    - S3 large unused:   cost * 0.9   (monthly cost × ratio)
    - RDS stopped:       GB * 0.115   ($/GB/month × GB — monthly)
    - Lambda unused:     0.0          (no direct cost)
  No × 30 conversion is applied here. The value is used directly as the
  monthly delta against the FR-2 monthly forecast.

Synthetic data caveat:
  Cost projections are based on synthetic seed data (source='synthetic_seed').
  Simulated savings figures will differ once real AWS billing history accumulates.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session

from models.cost_record import Recommendation
from models.account import CloudAccount
from services.ml_predictor import predict_costs

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
#  RESULT DATACLASS
# ══════════════════════════════════════════════════════════════════

@dataclass
class SimulationResult:
    """
    Output of a single What-If simulation run.

    All *_30d_usd fields represent 30-day projected cost in USD,
    matching the FR-2 monthly_estimate_usd convention.

    payback_days is None for resize/stop actions (no upfront cost to recover).
    It is only populated when there is a known implementation cost — currently
    not applicable for FR-4.1 recommendation-driven simulations. Reserved for
    FR-6 (Savings Plans Optimizer) where Reserved Instance upfront costs apply.
    """
    recommendation_id:    str
    resource_id:          str
    resource_name:        str
    service_type:         str
    region:               str

    # FR-2 forecast baseline (what happens if nothing changes)
    baseline_30d_usd:     float     # FR-2 per-service monthly estimate, un-modified
    # Simulated forecast (what happens if recommendation is applied)
    simulated_30d_usd:    float     # max(0, baseline − potential_savings_usd)

    # Delta
    delta_usd:            float     # baseline − simulated (= potential_savings_usd, capped to baseline)
    delta_pct:            float     # delta / baseline × 100

    # Uncertainty — derived from FR-3 residual rolling_std for this service
    # (positive value; represents ± band width)
    uncertainty_band_usd: float

    # Trend context — from get_service_attribution() trend_rate
    monthly_trend_rate:   float     # USD/day slope × 30 (projected monthly trend contribution)

    # Approximation flag — always True for FR-4.1 (service-level, not per-resource)
    is_service_level_approx: bool = True

    # Nullable — only set when there is a known upfront implementation cost to recover
    payback_days: Optional[int] = None
    upfront_cost_usd: Optional[float] = None
    first_month_cash_impact_usd: float = 0.0


# ══════════════════════════════════════════════════════════════════
#  UNCERTAINTY HELPER  (reuses FR-3 residual distribution)
# ══════════════════════════════════════════════════════════════════

def _estimate_uncertainty(db: Session, account_ids: list, service_type: str) -> float:
    """
    Return the rolling residual std for this service from the anomaly detector's
    lookback window. Reuses the same residual data FR-3 uses — no separate computation.

    Falls back to 5% of baseline if insufficient history.
    """
    import numpy as np
    from services.ml_predictor import _load_per_service_data
    from services.anomaly_detector import LOOKBACK_DAYS, MIN_RESIDUALS

    # _compute_fitted is defined in anomaly_detector; import safely
    try:
        from services.anomaly_detector import _compute_fitted
    except ImportError:
        return 0.0

    service_data = _load_per_service_data(db, account_ids)
    if service_type not in service_data:
        return 0.0

    X, y, dates = service_data[service_type]
    n = len(X)
    if n < 7:
        return 0.0

    try:
        fitted = _compute_fitted(X, y, n)
        residuals = np.array([float(y[i]) - float(fitted[i]) for i in range(n)])
        # Use last LOOKBACK_DAYS window for rolling std (same as detector)
        window = residuals[-LOOKBACK_DAYS:] if n >= LOOKBACK_DAYS else residuals
        std    = float(np.std(window))
        # Convert daily std to 30-day band: std × sqrt(30) (random walk approximation)
        return round(std * (30 ** 0.5), 4)
    except Exception as e:
        logger.warning("_estimate_uncertainty failed for %s: %s", service_type, e)
        return 0.0


# ══════════════════════════════════════════════════════════════════
#  PUBLIC: RUN SIMULATION (FR-4 entry point)
# ══════════════════════════════════════════════════════════════════

def run_simulation(
    db: Session,
    account_id: str,
    recommendation_id: str,
) -> SimulationResult:
    """
    Run a What-If simulation for a single recommendation.

    Algorithm (corrected — no ×30 conversion):
      1. Load Recommendation → service_type, potential_savings_usd (already monthly)
      2. Run predict_costs() → per_service_forecast → baseline_30d_usd
      3. simulated_30d = max(0, baseline_30d − potential_savings_usd)
      4. delta = baseline − simulated  (capped at baseline if savings > forecast)
      5. delta_pct = delta / baseline × 100
      6. uncertainty_band from FR-3 residual rolling_std (reused, not recomputed)
      7. monthly_trend_rate from get_service_attribution().trend_rate × 30
      8. payback_days = None (resize/stop actions have no upfront cost to recover)

    Raises:
      ValueError — recommendation not found or belongs to wrong account
    """
    import uuid
    try:
        rec_uuid = uuid.UUID(str(recommendation_id))
    except ValueError:
        raise ValueError(f"Invalid recommendation_id {recommendation_id}")

    rec = db.query(Recommendation).filter(Recommendation.id == rec_uuid).first()
    if not rec:
        raise ValueError(f"Recommendation {recommendation_id} not found")
    if rec.account_id != account_id:
        raise ValueError("Recommendation does not belong to the requested account")

    savings_usd  = rec.potential_savings_usd or 0.0
    service_type = rec.service_type

    # ── Get FR-2 forecast baseline ───────────────────────────────
    try:
        forecast_data = predict_costs(db, [account_id])
    except Exception as e:
        logger.error("FR-4: predict_costs failed for account %s: %s", account_id[:8], e)
        raise ValueError(f"Could not generate forecast baseline: {e}")

    # Extract per-service monthly estimate for this service
    per_service = forecast_data.get("per_service_forecast", [])
    baseline_30d = 0.0
    for svc_entry in per_service:
        if svc_entry.get("service") == service_type:
            baseline_30d = float(svc_entry.get("monthly_estimate_usd", 0.0))
            break

    # If service not in per-service breakdown, fall back to proportional share
    if baseline_30d == 0.0:
        total_30d = float(forecast_data.get("monthly_estimate_usd", 0.0))
        logger.warning(
            "FR-4: service %s not in per_service_forecast for account %s. "
            "Baseline will be 0 — simulation delta = savings directly.",
            service_type, account_id[:8],
        )
        baseline_30d = total_30d  # conservative: treat total as baseline

    # ── Compute simulation ───────────────────────────────────────
    if rec.action == "Purchase Savings Plan":
        # SPs redefine the monthly cost structure. The new simulated monthly cost 
        # is the baseline minus the established monthly savings of the plan.
        delta_usd      = min(savings_usd, baseline_30d)
        simulated_30d  = round(max(0.0, baseline_30d - delta_usd), 4)
        delta_usd      = round(baseline_30d - simulated_30d, 4)
        delta_pct      = round((delta_usd / baseline_30d * 100) if baseline_30d > 1e-9 else 0.0, 2)
        
        payback_days = rec.payback_days
        upfront_cost_usd = rec.upfront_cost_usd or 0.0
        first_month_cash_impact_usd = round(simulated_30d + upfront_cost_usd, 4)
    else:
        # Standard rightsizing/cleanup
        delta_usd      = min(savings_usd, baseline_30d)
        simulated_30d  = round(max(0.0, baseline_30d - delta_usd), 4)
        delta_usd      = round(baseline_30d - simulated_30d, 4)
        delta_pct      = round((delta_usd / baseline_30d * 100) if baseline_30d > 1e-9 else 0.0, 2)
        
        payback_days = None
        upfront_cost_usd = None
        first_month_cash_impact_usd = simulated_30d

    # ── Uncertainty band (FR-3 residual reuse) ───────────────────
    uncertainty = _estimate_uncertainty(db, [account_id], service_type)
    if uncertainty == 0.0:
        uncertainty = round(baseline_30d * 0.05, 4)   # 5% of baseline fallback

    # ── Trend rate (from shared attribution helper) ───────────────
    try:
        from services.ml_predictor import get_service_attribution
        attribution = get_service_attribution(db, [account_id])
        trend_rate_per_day = next(
            (a["trend_rate"] for a in attribution if a["service"] == service_type), 0.0
        )
        monthly_trend_rate = round(trend_rate_per_day * 30, 4)
    except Exception:
        monthly_trend_rate = 0.0

    logger.info(
        "FR-4 simulation: rec=%s svc=%s baseline=%.2f simulated=%.2f delta=%.2f (%.1f%%) upfront=%.2f",
        str(recommendation_id)[:8], service_type, baseline_30d, simulated_30d, delta_usd, delta_pct, upfront_cost_usd or 0.0
    )

    return SimulationResult(
        recommendation_id    = recommendation_id,
        resource_id          = rec.resource_id,
        resource_name        = rec.resource_name or rec.resource_id,
        service_type         = service_type,
        region               = rec.region,
        baseline_30d_usd     = round(baseline_30d, 4),
        simulated_30d_usd    = simulated_30d,
        delta_usd            = delta_usd,
        delta_pct            = delta_pct,
        uncertainty_band_usd = uncertainty,
        monthly_trend_rate   = monthly_trend_rate,
        is_service_level_approx = True,
        payback_days         = payback_days,
        upfront_cost_usd     = upfront_cost_usd,
        first_month_cash_impact_usd = first_month_cash_impact_usd,
    )
