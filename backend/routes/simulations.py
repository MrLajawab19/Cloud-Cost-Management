"""
routes/simulations.py — FR-4 What-If Simulation API endpoints.

Endpoints:
  GET  /simulations/{recommendation_id}   — single simulation (on-demand, no DB write)
  POST /simulations/batch                 — list of recommendation IDs

Results are ephemeral: computed on request, not persisted.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from database import get_db
from services.security import get_current_user
from services.what_if_simulator import run_simulation, SimulationResult
from services.aws_collector import EC2_HOURLY_PRICE
from services.ml_predictor import predict_costs
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation
from models.resource import Resource
from models.anomaly import Anomaly

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations"])


# ── Request schema ────────────────────────────────────────────────

class BatchRequest(BaseModel):
    ids: List[str]   # list of recommendation_ids
    account_id: Optional[str] = None


class ResourceSimulateRequest(BaseModel):
    resource_id: str
    action: str      # stop | terminate | resize | delete | deallocate
    target_type: Optional[str] = None
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
        a.id for a in db.query(CloudAccount)
        .filter(CloudAccount.user_id == current_user.id).all()
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


# ── Per-Resource What-If Endpoints ─────────────────────────────────

@router.get("/resource-options")
def get_resource_options(
    account_id: str,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Returns every resource for the specified account with allowed What-If actions.
    Ephemeral read-only query.
    """
    account = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    resources = db.query(Resource).filter(Resource.account_id == account_id).all()
    results = []
    for r in resources:
        svc = r.service_type
        if svc == "EC2":
            allowed_actions = ["stop", "terminate", "resize"]
            target_types = list(EC2_HOURLY_PRICE.keys())
        elif svc == "RDS":
            allowed_actions = ["stop", "delete"]
            target_types = []
        elif svc == "AzureVM":
            # Per specification: resize is only offered if an Azure price table exists
            allowed_actions = ["stop", "delete"]
            target_types = []
        elif svc in ["S3", "Lambda"]:
            allowed_actions = ["delete"]
            target_types = []
        else:
            allowed_actions = ["terminate"]
            target_types = []

        results.append({
            "resource_id": r.resource_id,
            "name": r.resource_name or r.resource_id,
            "service_type": r.service_type,
            "status": r.status or "unknown",
            "monthly_cost": r.estimated_monthly_cost,
            "allowed_actions": allowed_actions,
            "target_types": target_types,
            "cpu_utilization_avg": r.cpu_utilization_avg,
        })
    return results


@router.post("/resource")
def simulate_resource(
    body:         ResourceSimulateRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Ephemeral What-If simulation for a specific resource change.
    No database mutations, no cloud SDK calls.
    """
    import uuid as _uuid
    res = db.query(Resource).filter(Resource.resource_id == body.resource_id).first()
    if not res:
        try:
            res_uuid = _uuid.UUID(str(body.resource_id))
            res = db.query(Resource).filter(Resource.id == res_uuid).first()
        except (ValueError, TypeError):
            res = None
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")

    account = db.query(CloudAccount).filter(CloudAccount.id == res.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    if account.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if body.account_id and body.account_id != res.account_id:
        raise HTTPException(status_code=403, detail="Resource does not belong to specified account")

    act_raw = (body.action or "").strip().lower()
    if act_raw in ["stop", "deallocate"]:
        action = "stop"
    elif act_raw in ["terminate", "delete"]:
        action = "terminate"
    elif act_raw in ["resize", "downsize"]:
        action = "resize"
    else:
        action = act_raw

    svc = res.service_type

    # Action validations
    if svc == "AzureVM" and action == "resize":
        raise HTTPException(status_code=400, detail="Resize is not offered for AzureVM: no price table available.")
    if svc in ["S3", "Lambda"] and action in ["stop", "resize"]:
        raise HTTPException(status_code=400, detail=f"Action '{act_raw}' is not supported for {svc}. Only deletion is available.")
    if svc == "RDS" and action == "resize":
        raise HTTPException(status_code=400, detail="Resize is not supported for RDS. Allowed actions: stop, delete.")
    if action not in ["stop", "terminate", "resize"]:
        raise HTTPException(status_code=400, detail=f"Unknown action '{act_raw}'. Must be stop, terminate, or resize.")
    if action == "resize" and svc == "EC2":
        if not body.target_type:
            raise HTTPException(status_code=400, detail="target_type is required for resize action")
        if body.target_type not in EC2_HOURLY_PRICE:
            raise HTTPException(status_code=400, detail=f"Invalid target_type '{body.target_type}'. Valid types: {list(EC2_HOURLY_PRICE.keys())}")

    # Check FR-7 safety rule: active unresolved anomaly on this service within 14 days
    cutoff = datetime.utcnow() - timedelta(days=14)
    active_anomaly = db.query(Anomaly).filter(
        Anomaly.account_id == res.account_id,
        Anomaly.record_date >= cutoff.date(),
        Anomaly.is_resolved == False,
        Anomaly.service_type == res.service_type,
    ).first()
    has_anomaly_hold = (active_anomaly is not None)

    # Normalized service forecast baseline
    try:
        forecast_data = predict_costs(db, [res.account_id])
        per_service = forecast_data.get("per_service_forecast", [])
        svc_baseline = 0.0
        for s in per_service:
            if s.get("service") == res.service_type:
                svc_baseline = float(s.get("monthly_estimate_usd", 0.0))
                break
        if svc_baseline == 0.0:
            svc_baseline = float(forecast_data.get("monthly_estimate_usd", 0.0))
    except Exception as e:
        logger.warning("Predict costs failed in resource simulation: %s", e)
        svc_baseline = 0.0

    # Unknown cost -> "Cost unavailable", no numbers
    if res.estimated_monthly_cost is None:
        return {
            "resource_name": res.resource_name or res.resource_id,
            "service_type": res.service_type,
            "action": body.action,
            "current_monthly_cost": "Cost unavailable",
            "new_monthly_cost": "Cost unavailable",
            "monthly_saving": "Cost unavailable",
            "annual_saving": "Cost unavailable",
            "remaining_cost_after_action": "Cost unavailable",
            "remaining_cost_reason": "Cost unavailable",
            "reversible": action in ["stop", "resize"],
            "side_effects": ["Resource lifecycle state modified; service metrics unavailable."],
            "risk_notes": ["Cost unavailable: baseline metrics have not been recorded yet."],
            "service_forecast_before": "Cost unavailable",
            "service_forecast_after": "Cost unavailable",
            "formula_note": "Cost unavailable",
        }

    cost = round(float(res.estimated_monthly_cost), 2)
    current_monthly_cost = cost
    side_effects = []
    risk_notes = []

    if action == "stop":
        reversible = True
        if svc == "EC2":
            ebs_cost = 3.00  # Stopped-EC2 EBS constant from cleanup_advisor
            new_monthly_cost = round(min(cost, ebs_cost), 2)
            monthly_saving = round(max(0.0, cost - new_monthly_cost), 2)
            remaining_cost_after_action = new_monthly_cost
            remaining_cost_reason = "EBS storage charges (~$3.00/month) continue to accrue while instance is stopped"
            formula_note = "Compute cost eliminated; baseline EBS volume cost ($3.00/month) retained."
            side_effects.append("Instance compute halts. Applications and web services hosted on this instance will be temporarily unavailable.")
            if has_anomaly_hold:
                risk_notes.append(f"FR-7 Safety Rule: Automatic stop would be held due to an active unresolved anomaly on {res.service_type} within the last 14 days.")
        elif svc == "RDS":
            storage_gb = res.storage_size_gb or 20.0
            rds_storage_cost = round(storage_gb * 0.115, 2)
            new_monthly_cost = round(min(cost, rds_storage_cost), 2)
            monthly_saving = round(max(0.0, cost - new_monthly_cost), 2)
            remaining_cost_after_action = new_monthly_cost
            remaining_cost_reason = f"Allocated storage charges ({storage_gb:.0f} GB @ $0.115/GB-month) continue to accrue while instance is stopped"
            formula_note = f"Compute cost eliminated; allocated storage ({storage_gb:.0f} GB @ $0.115/GB-month) retained."
            side_effects.append("Database instance stops; incoming client connections and transactions will fail until restarted.")
            risk_notes.append("AWS automatically restarts stopped RDS instances after 7 consecutive days for maintenance.")
            if has_anomaly_hold:
                risk_notes.append(f"FR-7 Safety Rule: Automatic stop would be held due to an active unresolved anomaly on {res.service_type} within the last 14 days.")
        elif svc == "AzureVM":
            disk_cost = 1.50
            new_monthly_cost = round(min(cost, disk_cost), 2)
            monthly_saving = round(max(0.0, cost - new_monthly_cost), 2)
            remaining_cost_after_action = new_monthly_cost
            remaining_cost_reason = "OS disk storage charges (~$1.50/month) continue to accrue while VM is deallocated"
            formula_note = "Compute cost eliminated; OS disk baseline ($1.50/month) retained."
            side_effects.append("VM is deallocated and compute stops. Dynamic public IP address is released unless static.")
            if has_anomaly_hold:
                risk_notes.append(f"FR-7 Safety Rule: Automatic stop would be held due to an active unresolved anomaly on {res.service_type} within the last 14 days.")
        else:
            new_monthly_cost = 0.0
            monthly_saving = cost
            remaining_cost_after_action = 0.0
            remaining_cost_reason = "None"
            formula_note = "Resource stopped."

    elif action == "terminate":
        reversible = False
        new_monthly_cost = 0.0
        monthly_saving = cost
        remaining_cost_after_action = 0.0
        remaining_cost_reason = "None (resource completely deleted)"
        formula_note = "Full 100% monthly cost eliminated."

        if svc == "EC2":
            side_effects.append("Instance, ephemeral storage, and root EBS volumes permanently terminated.")
            risk_notes.append("Irreversible action: Data loss warning. Create an AMI/EBS snapshot prior to termination.")
        elif svc == "RDS":
            side_effects.append("Database cluster/instance destroyed permanently.")
            risk_notes.append("Irreversible action: Data loss warning. Take a final DB snapshot before deletion.")
        elif svc == "S3":
            side_effects.append("All objects, prefixes, and versions within bucket deleted permanently.")
            risk_notes.append("Irreversible action: Data loss warning. Consider lifecycle transition to Glacier instead of outright deletion if archives may be needed.")
        elif svc == "Lambda":
            side_effects.append("Function code and configuration removed; API endpoints and event triggers will return errors.")
            risk_notes.append("Verify upstream event sources and dependencies are disconnected before deleting.")
        elif svc == "AzureVM":
            side_effects.append("Virtual Machine and attached OS disks deleted permanently.")
            risk_notes.append("Irreversible action: Data loss warning. Create a managed disk snapshot before deletion.")
        else:
            side_effects.append("Resource deleted permanently.")
            risk_notes.append("Irreversible action: Data loss warning.")

    elif action == "resize":
        reversible = True
        hourly_price = EC2_HOURLY_PRICE[body.target_type]
        new_monthly_cost = round(hourly_price * 730, 2)
        monthly_saving = round(cost - new_monthly_cost, 2)
        remaining_cost_after_action = new_monthly_cost
        remaining_cost_reason = f"New instance type {body.target_type} hourly rate (${hourly_price:.4f}/hr × 730h)"
        formula_note = f"Difference between current cost (${cost:.2f}) and {body.target_type} monthly cost (${new_monthly_cost:.2f})."
        side_effects.append("Requires instance reboot/restart to apply instance type change (brief downtime).")
        
        # CPU-fit note
        if res.cpu_utilization_avg is not None:
            risk_notes.append(f"Average CPU is {res.cpu_utilization_avg:.1f}%; a smaller type is likely safe.")
        else:
            risk_notes.append("CPU utilization metrics unavailable; monitor performance closely after resizing.")
        
        if has_anomaly_hold:
            risk_notes.append(f"FR-7 Safety Rule: Automatic remediation would be held due to an active unresolved anomaly on {res.service_type} within the last 14 days.")

    annual_saving = round(monthly_saving * 12, 2)
    service_forecast_before = round(svc_baseline, 2)
    service_forecast_after = round(max(0.0, svc_baseline - monthly_saving), 2)

    return {
        "resource_name": res.resource_name or res.resource_id,
        "service_type": res.service_type,
        "action": body.action,
        "current_monthly_cost": current_monthly_cost,
        "new_monthly_cost": new_monthly_cost,
        "monthly_saving": monthly_saving,
        "annual_saving": annual_saving,
        "remaining_cost_after_action": remaining_cost_after_action,
        "remaining_cost_reason": remaining_cost_reason,
        "reversible": reversible,
        "side_effects": side_effects,
        "risk_notes": risk_notes,
        "service_forecast_before": service_forecast_before,
        "service_forecast_after": service_forecast_after,
        "formula_note": formula_note,
    }


# ── Recommendation Simulation Routes ───────────────────────────────

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
