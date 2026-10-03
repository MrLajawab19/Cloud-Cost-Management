"""
routes/simulations.py — FR-4 What-If Simulation API endpoints.

Endpoints:
  GET  /simulations/{recommendation_id}   — single simulation (on-demand, no DB write)
  POST /simulations/batch                 — list of recommendation IDs

Results are ephemeral: computed on request, not persisted.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.security import get_current_user
from services.what_if_simulator import run_simulation, SimulationResult
from models.user import User
from models.account import AWSAccount
from models.cost_record import Recommendation

router = APIRouter(prefix="/simulations", tags=["Simulations"])


# ── Request schema ────────────────────────────────────────────────

class BatchRequest(BaseModel):
    ids: List[str]   # list of recommendation_ids
    account_id: Optional[str] = None


# ── Shared helpers ────────────────────────────────────────────────

def _resolve_account_id(
    db: Session,
    current_user: User,
    recommendation_id: str,
) -> str:
    """
    Resolve account_id from the recommendation itself, verify ownership.
    Raises 404/403 as appropriate.
    """
    import uuid
    try:
        rec_uuid = uuid.UUID(str(recommendation_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recommendation_id format")

    rec = db.query(Recommendation).filter(Recommendation.id == rec_uuid).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    user_account_ids = [
        a.id for a in db.query(AWSAccount)
        .filter(AWSAccount.user_id == current_user.id).all()
    ]
    if rec.account_id not in user_account_ids:
        raise HTTPException(status_code=403, detail="Access denied")

    return rec.account_id


def _result_to_dict(r: SimulationResult) -> dict:
    return {
        "recommendation_id":     r.recommendation_id,
        "resource_id":           r.resource_id,
        "resource_name":         r.resource_name,
        "service_type":          r.service_type,
        "region":                r.region,
        "baseline_30d_usd":      r.baseline_30d_usd,
        "simulated_30d_usd":     r.simulated_30d_usd,
        "delta_usd":             r.delta_usd,
        "delta_pct":             r.delta_pct,
        "uncertainty_band_usd":  r.uncertainty_band_usd,
        "monthly_trend_rate":    r.monthly_trend_rate,
        "is_service_level_approx": r.is_service_level_approx,
        "payback_days":          r.payback_days,
        "upfront_cost_usd":      r.upfront_cost_usd,
        "first_month_cash_impact_usd": r.first_month_cash_impact_usd,
        # Explanation text — consumed directly by the frontend
        "approx_note": (
            "Service-level approximation: assumes this action reduces the "
            f"{r.service_type} aggregate cost by ${r.delta_usd:.2f}/month. "
            "Actual savings may vary depending on other resources in the same service pool."
        ),
        "synthetic_data_note": (
            "Projection is based on synthetic seed data, not live AWS billing. "
            "Figures will become more accurate once real billing history is collected."
        ),
    }


# ── Routes ────────────────────────────────────────────────────────

@router.get("/{recommendation_id}")
def simulate_one(
    recommendation_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    FR-4.1: Run a What-If simulation for a single recommendation.

    Returns projected 30-day cost baseline vs. simulated (post-action) figures,
    delta, uncertainty band, and trend context.

    Computation is on-demand; result is NOT persisted to DB.
    """
    account_id = _resolve_account_id(db, current_user, recommendation_id)
    try:
        result = run_simulation(db, account_id, recommendation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return _result_to_dict(result)


@router.post("/batch")
def simulate_batch(
    body:         BatchRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    FR-4.1: Run simulations for multiple recommendation IDs.

    Returns a list of results (one per ID). Failed simulations are included
    with an 'error' key so the client can display partial results gracefully.
    """
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids list must not be empty")
    if len(body.ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 IDs per batch")

    results = []
    for rec_id in body.ids:
        try:
            account_id = _resolve_account_id(db, current_user, rec_id)
            result     = run_simulation(db, account_id, rec_id)
            results.append(_result_to_dict(result))
        except HTTPException as e:
            results.append({"recommendation_id": rec_id, "error": e.detail})
        except Exception as e:
            results.append({"recommendation_id": rec_id, "error": str(e)})

    return {
        "simulations": results,
        "total":       len(results),
        "success":     sum(1 for r in results if "error" not in r),
    }
