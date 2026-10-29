"""
routes/demo.py — Live Data Lab API for Demo Accounts.

Endpoints:
  POST /demo/inject?account_id= — Inject synthetic test scenarios and evaluate live pipeline.
  POST /demo/reset?account_id=  — Reset demo account to clean initial deterministic state.

Security & Safety:
  - Allowed ONLY for UUID5 demo accounts owned by the current user.
  - Real accounts (with credentials), legacy demo accounts, or other users' accounts return 403/404.
  - Simulated actions never call cloud SDKs.
  - Note: A backend restart also resets demo accounts relative to today.
"""

import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation, format_recommendation_id_fk
from models.anomaly import Anomaly
from models.remediation import EscalationState
from services.security import get_current_user
from services.cost_estimator import is_aws_real, is_azure_real
from services.demo_data import reset_demo_account
from services.ml_predictor import predict_costs
from services.anomaly_detector import detect_anomalies
from services.cleanup_advisor import generate_recommendations
from services.savings_plan_optimiser import generate_sp_recommendations
from services.escalation_manager import process_auto_resizes
from routes.savings_optimiser import compute_savings_plans

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["Live Data Lab"])


class InjectRequest(BaseModel):
    scenario: str = Field(..., description="normal_day | cost_spike | sustained_drift | cost_drop | new_idle_resource | new_oversized_resource | new_service")
    service: Optional[str] = None
    magnitude: Optional[float] = None
    days: Optional[int] = None
    monthly_cost: Optional[float] = None


def _validate_uuid5_demo_account(db: Session, current_user: User, account_id: str) -> CloudAccount:
    acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")

    if str(acc.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    if is_aws_real(acc) or is_azure_real(acc):
        raise HTTPException(status_code=403, detail="Live Data Lab allowed only for demo accounts without credentials")

    if acc.id == "00000000-0000-0000-0000-demoaccount01":
        raise HTTPException(status_code=403, detail="Live Data Lab not allowed on legacy demo account")

    try:
        u_uuid = uuid.UUID(str(current_user.id))
        valid_demo_ids = {
            str(uuid.uuid5(u_uuid, "demo-aws")),
            str(uuid.uuid5(u_uuid, "demo-azure")),
        }
    except Exception:
        valid_demo_ids = set()

    if acc.id not in valid_demo_ids:
        raise HTTPException(status_code=403, detail="Live Data Lab allowed only for UUID5 demo accounts")

    return acc


def _capture_state(db: Session, account: CloudAccount) -> Dict[str, Any]:
    acc_id = str(account.id)

    # 1. Anomalies
    anomalies = (
        db.query(Anomaly)
        .filter(Anomaly.account_id == acc_id)
        .order_by(Anomaly.record_date.desc(), Anomaly.service_type)
        .all()
    )
    anomaly_list = [
        {
            "id": a.id,
            "service": a.service_type,
            "date": str(a.record_date),
            "z": round(float(a.z_score), 2),
            "severity": a.severity,
            "direction": a.direction,
            "driver": a.driver_service,
            "is_resolved": bool(a.is_resolved)
        }
        for a in anomalies
    ]

    # 2. Forecast
    try:
        forecast_data = predict_costs(db, [acc_id])
        comp = forecast_data.get("model_comparison") or {}
        model_info = forecast_data.get("model_info") or {}
        forecast_summary = {
            "total_30d": float(forecast_data.get("monthly_estimate_usd", 0.0)),
            "winner": comp.get("winner") or model_info.get("winner", "N/A"),
            "winner_key": comp.get("winner_key") or model_info.get("type", "N/A"),
            "poly_mape": comp.get("poly_mape"),
            "hw_mape": comp.get("hw_mape"),
        }
    except Exception as e:
        logger.warning(f"Failed to capture forecast for demo state: {e}")
        forecast_summary = {
            "total_30d": 0.0,
            "winner": "N/A",
            "winner_key": "N/A",
            "poly_mape": None,
            "hw_mape": None,
        }

    # 3. Recommendations
    recs = (
        db.query(Recommendation)
        .filter(Recommendation.account_id == acc_id, Recommendation.is_resolved == False)
        .order_by(Recommendation.potential_savings_usd.desc())
        .all()
    )
    rec_list = [
        {
            "id": str(r.id),
            "issue": r.issue,
            "resource": r.resource_name or r.resource_id,
            "resource_id": r.resource_id,
            "savings": float(r.potential_savings_usd or 0.0),
            "severity": r.severity
        }
        for r in recs
    ]

    # 4. Savings Optimiser Plans
    try:
        plans = compute_savings_plans(db, account)
        opt_summary = [
            {
                "service": s["service"],
                "recommended": s["recommended"],
                "reason": s["reason"],
                "is_new": s.get("is_new", False)
            }
            for s in plans.get("services", [])
        ]
    except Exception as e:
        logger.warning(f"Failed to compute savings plans for demo state: {e}")
        opt_summary = []

    # 5. Escalations
    rec_ids = [r.id for r in recs]
    rec_fks = [format_recommendation_id_fk(rid, db) for rid in rec_ids] + [str(rid) for rid in rec_ids]
    escs = (
        db.query(EscalationState)
        .filter(EscalationState.recommendation_id.in_(rec_fks))
        .all()
    )
    esc_list = [
        {
            "id": e.id,
            "recommendation_id": e.recommendation_id,
            "status": e.status,
            "due_at": e.due_at.isoformat() if e.due_at else None
        }
        for e in escs
    ]

    return {
        "anomaly_count": len(anomaly_list),
        "anomalies": anomaly_list,
        "forecast": forecast_summary,
        "recommendation_count": len(rec_list),
        "recommendations": rec_list,
        "savings_optimiser": opt_summary,
        "escalation_count": len(esc_list),
        "escalations": esc_list
    }


@router.post("/inject")
def inject_demo_scenario(
    payload: InjectRequest,
    account_id: str = Query(..., description="Demo Account ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Inject synthetic scenarios into a UUID5 demo account, run the real pipeline,
    and return {before, after, delta}.
    """
    acc = _validate_uuid5_demo_account(db, current_user, account_id)
    provider = acc.provider.lower()

    # Provider separation enforcement
    if provider == "aws":
        valid_services = ["EC2", "RDS", "S3", "Lambda"]
        if payload.service and payload.service not in valid_services:
            raise HTTPException(status_code=400, detail=f"Service {payload.service} not allowed on AWS demo account")
        target_service = payload.service or "EC2"
    elif provider == "azure":
        valid_services = ["AzureVM"]
        if payload.service and payload.service != "AzureVM":
            raise HTTPException(status_code=400, detail=f"Only AzureVM is supported on Azure demo account")
        target_service = "AzureVM"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider {provider}")

    # Step 1: Capture BEFORE state
    before = _capture_state(db, acc)

    today = date.today()
    scenario = payload.scenario.strip().lower()

    # Step 2: Inject scenario data
    if scenario == "normal_day":
        # Add small seeded noise (<1%) to today's cost records — must NOT create an anomaly
        for svc in valid_services:
            rec = (
                db.query(CostRecord)
                .filter(CostRecord.account_id == acc.id, CostRecord.service_type == svc, CostRecord.record_date == today)
                .first()
            )
            if rec:
                rec.daily_cost_usd = round(rec.daily_cost_usd * 1.004, 4)
                rec.monthly_estimate = round(rec.daily_cost_usd * 30.0, 4)
                rec.source = "demo_injected"
            else:
                # Use yesterday's cost
                yest = (
                    db.query(CostRecord)
                    .filter(CostRecord.account_id == acc.id, CostRecord.service_type == svc)
                    .order_by(CostRecord.record_date.desc())
                    .first()
                )
                base = yest.daily_cost_usd if yest else 5.0
                cr = CostRecord(
                    account_id=acc.id,
                    service_type=svc,
                    region=acc.region or ("us-east-1" if provider == "aws" else "eastus"),
                    record_date=today,
                    daily_cost_usd=round(base * 1.002, 4),
                    monthly_estimate=round(base * 1.002 * 30.0, 4),
                    source="demo_injected"
                )
                db.add(cr)

    elif scenario == "cost_spike":
        # Magnitude = % above that day's baseline, default +80%
        mag = payload.magnitude if payload.magnitude is not None else 80.0
        rec = (
            db.query(CostRecord)
            .filter(CostRecord.account_id == acc.id, CostRecord.service_type == target_service, CostRecord.record_date == today)
            .first()
        )
        if rec:
            base_cost = rec.daily_cost_usd
            spike_cost = round(base_cost * (1.0 + mag / 100.0), 4)
            rec.daily_cost_usd = spike_cost
            rec.monthly_estimate = round(spike_cost * 30.0, 4)
            rec.source = "demo_injected"
        else:
            yest = (
                db.query(CostRecord)
                .filter(CostRecord.account_id == acc.id, CostRecord.service_type == target_service)
                .order_by(CostRecord.record_date.desc())
                .first()
            )
            base_cost = yest.daily_cost_usd if yest else 6.0
            spike_cost = round(base_cost * (1.0 + mag / 100.0), 4)
            cr = CostRecord(
                account_id=acc.id,
                service_type=target_service,
                region=acc.region or ("us-east-1" if provider == "aws" else "eastus"),
                record_date=today,
                daily_cost_usd=spike_cost,
                monthly_estimate=round(spike_cost * 30.0, 4),
                source="demo_injected"
            )
            db.add(cr)

    elif scenario == "sustained_drift":
        # service, days, +%/day
        mag = payload.magnitude if payload.magnitude is not None else 5.0
        n_days = max(2, min(payload.days if payload.days is not None else 5, 14))
        for d in range(n_days, -1, -1):
            r_date = today - timedelta(days=d)
            step_pct = (mag / 100.0) * (n_days - d + 1)
            rec = (
                db.query(CostRecord)
                .filter(CostRecord.account_id == acc.id, CostRecord.service_type == target_service, CostRecord.record_date == r_date)
                .first()
            )
            if rec:
                rec.daily_cost_usd = round(rec.daily_cost_usd * (1.0 + step_pct), 4)
                rec.monthly_estimate = round(rec.daily_cost_usd * 30.0, 4)
                rec.source = "demo_injected"

    elif scenario == "cost_drop":
        mag = payload.magnitude if payload.magnitude is not None else 80.0
        rec = (
            db.query(CostRecord)
            .filter(CostRecord.account_id == acc.id, CostRecord.service_type == target_service, CostRecord.record_date == today)
            .first()
        )
        drop_factor = max(0.05, 1.0 - (mag / 100.0))
        if rec:
            drop_cost = round(max(0.01, rec.daily_cost_usd * drop_factor), 4)
            rec.daily_cost_usd = drop_cost
            rec.monthly_estimate = round(drop_cost * 30.0, 4)
            rec.source = "demo_injected"
        else:
            yest = (
                db.query(CostRecord)
                .filter(CostRecord.account_id == acc.id, CostRecord.service_type == target_service)
                .order_by(CostRecord.record_date.desc())
                .first()
            )
            base = yest.daily_cost_usd if yest else 5.0
            drop_cost = round(max(0.01, base * drop_factor), 4)
            cr = CostRecord(
                account_id=acc.id,
                service_type=target_service,
                region=acc.region or ("us-east-1" if provider == "aws" else "eastus"),
                record_date=today,
                daily_cost_usd=drop_cost,
                monthly_estimate=round(drop_cost * 30.0, 4),
                source="demo_injected"
            )
            db.add(cr)

    elif scenario == "new_idle_resource":
        # AWS: EC2 t3.medium cpu 0.3 runtime 300h; Azure: VM Standard_B2s cpu 0.4 runtime 250h
        now_dt = datetime.now(timezone.utc)
        if provider == "aws":
            res_id = f"i-demo-injected-idle-{uuid.uuid4().hex[:8]}"
            r = Resource(
                id=uuid.uuid4(),
                account_id=acc.id,
                resource_id=res_id,
                resource_name="injected-idle-worker",
                service_type="EC2",
                region=acc.region or "us-east-1",
                status="running",
                resource_type="t3.medium",
                cpu_utilization_avg=0.3,
                runtime_hours=300.0,
                estimated_monthly_cost=40.0,
                is_idle=True,
                last_seen=now_dt,
                launch_time=now_dt - timedelta(days=20)
            )
            db.add(r)
        else:
            res_id = f"/subscriptions/demo/resourceGroups/injected/providers/Microsoft.Compute/virtualMachines/injected-idle-vm-{uuid.uuid4().hex[:8]}"
            r = Resource(
                id=uuid.uuid4(),
                account_id=acc.id,
                resource_id=res_id,
                resource_name="injected-idle-vm",
                service_type="AzureVM",
                region=acc.region or "eastus",
                status="running",
                resource_type="Standard_B2s",
                cpu_utilization_avg=0.4,
                runtime_hours=250.0,
                estimated_monthly_cost=30.37,
                is_idle=True,
                last_seen=now_dt,
                launch_time=now_dt - timedelta(days=15)
            )
            db.add(r)

    elif scenario == "new_oversized_resource":
        # cpu ~3%
        now_dt = datetime.now(timezone.utc)
        if provider == "aws":
            res_id = f"i-demo-injected-oversized-{uuid.uuid4().hex[:8]}"
            r = Resource(
                id=uuid.uuid4(),
                account_id=acc.id,
                resource_id=res_id,
                resource_name="injected-oversized-api",
                service_type="EC2",
                region=acc.region or "us-east-1",
                status="running",
                resource_type="t3.medium",
                cpu_utilization_avg=3.0,
                runtime_hours=300.0,
                estimated_monthly_cost=40.0,
                is_idle=False,
                last_seen=now_dt,
                launch_time=now_dt - timedelta(days=20)
            )
            db.add(r)
        else:
            res_id = f"/subscriptions/demo/resourceGroups/injected/providers/Microsoft.Compute/virtualMachines/injected-oversized-vm-{uuid.uuid4().hex[:8]}"
            r = Resource(
                id=uuid.uuid4(),
                account_id=acc.id,
                resource_id=res_id,
                resource_name="injected-oversized-vm",
                service_type="AzureVM",
                region=acc.region or "eastus",
                status="running",
                resource_type="Standard_B2s",
                cpu_utilization_avg=3.0,
                runtime_hours=250.0,
                estimated_monthly_cost=30.37,
                is_idle=False,
                last_seen=now_dt,
                launch_time=now_dt - timedelta(days=15)
            )
            db.add(r)

    elif scenario == "new_service":
        target_service = payload.service or ("EC2" if provider == "aws" else "AzureVM")
        if provider == "aws":
            valid_services = {"EC2", "RDS", "Lambda", "S3"}
            if target_service not in valid_services:
                raise HTTPException(status_code=400, detail=f"Service '{target_service}' is not valid for AWS demo account")
        else:
            valid_services = {"AzureVM"}
            if target_service not in valid_services:
                raise HTTPException(status_code=400, detail=f"Service '{target_service}' is not valid for Azure demo account")

        m_cost = float(payload.monthly_cost if payload.monthly_cost is not None else 120.0)
        daily_c = round(m_cost / 30.0, 4)
        now_dt = datetime.now(timezone.utc)
        res_uid = uuid.uuid4()

        if target_service == "EC2":
            res_id = f"i-demo-injected-svc-{res_uid.hex[:8]}"
            r_name = "injected-ec2-service"
            r_type = "t3.medium"
            r_status = "running"
            cpu_avg = 15.0
            rt_hours = 360.0
        elif target_service == "RDS":
            res_id = f"rds-demo-injected-svc-{res_uid.hex[:8]}"
            r_name = "injected-rds-service"
            r_type = "db.t3.medium"
            r_status = "available"
            cpu_avg = 12.0
            rt_hours = 360.0
        elif target_service == "Lambda":
            res_id = f"lambda-demo-injected-svc-{res_uid.hex[:8]}"
            r_name = "injected-lambda-service"
            r_type = "Serverless Function"
            r_status = "active"
            cpu_avg = None
            rt_hours = 0.0
        elif target_service == "S3":
            res_id = f"s3-demo-injected-svc-{res_uid.hex[:8]}"
            r_name = "injected-s3-service"
            r_type = "S3 Bucket"
            r_status = "available"
            cpu_avg = None
            rt_hours = 0.0
        elif target_service == "AzureVM":
            res_id = f"/subscriptions/demo/resourceGroups/injected/providers/Microsoft.Compute/virtualMachines/injected-vm-{res_uid.hex[:8]}"
            r_name = "injected-azurevm-service"
            r_type = "Standard_B2s"
            r_status = "running"
            cpu_avg = 15.0
            rt_hours = 360.0
        else:
            res_id = f"demo-injected-{target_service.lower()}-{res_uid.hex[:8]}"
            r_name = f"injected-{target_service.lower()}-service"
            r_type = "Standard"
            r_status = "running"
            cpu_avg = None
            rt_hours = 360.0

        r = Resource(
            id=res_uid,
            account_id=acc.id,
            resource_id=res_id,
            resource_name=r_name,
            service_type=target_service,
            region=acc.region or ("us-east-1" if provider == "aws" else "eastus"),
            status=r_status,
            resource_type=r_type,
            cpu_utilization_avg=cpu_avg,
            runtime_hours=rt_hours,
            estimated_monthly_cost=m_cost,
            is_idle=False,
            last_seen=now_dt,
            launch_time=now_dt - timedelta(days=20)
        )
        db.add(r)

        # Backfill 15 days (>= 14 days) seeded cost history tagged source='demo_injected'
        today = date.today()
        for offset in range(14, -1, -1):
            d = today - timedelta(days=offset)
            v_factor = 1.0 + 0.01 * ((offset % 5) - 2)
            c_usd = round(daily_c * v_factor, 4)
            cr = CostRecord(
                account_id=acc.id,
                resource_id=res_id,
                service_type=target_service,
                region=acc.region or ("us-east-1" if provider == "aws" else "eastus"),
                record_date=d,
                daily_cost_usd=c_usd,
                monthly_estimate=round(c_usd * 30.0, 4),
                source="demo_injected"
            )
            db.add(cr)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{payload.scenario}'")

    db.commit()

    # Step 3: Run the real pipeline pieces
    detect_anomalies(db, [acc.id])
    generate_recommendations(db)
    generate_sp_recommendations(db, acc.id)
    process_auto_resizes(db)
    db.commit()

    # Step 4: Capture AFTER state
    after = _capture_state(db, acc)

    # Step 5: Compute DELTA
    before_anom_keys = {(a["service"], a["date"]) for a in before["anomalies"]}
    new_anomalies = [a for a in after["anomalies"] if (a["service"], a["date"]) not in before_anom_keys]

    before_rec_keys = {(r["issue"], r["resource_id"]) for r in before["recommendations"]}
    after_rec_keys = {(r["issue"], r["resource_id"]) for r in after["recommendations"]}

    recs_added = [r for r in after["recommendations"] if (r["issue"], r["resource_id"]) not in before_rec_keys]
    recs_removed = [r for r in before["recommendations"] if (r["issue"], r["resource_id"]) not in after_rec_keys]

    before_opt_map = {o["service"]: o for o in before["savings_optimiser"]}
    after_opt_map = {o["service"]: o for o in after["savings_optimiser"]}
    opt_changes = []
    for svc, a_opt in after_opt_map.items():
        b_opt = before_opt_map.get(svc)
        if not b_opt or b_opt["recommended"] != a_opt["recommended"] or b_opt["reason"] != a_opt["reason"]:
            opt_changes.append({
                "service": svc,
                "before": b_opt["recommended"] if b_opt else None,
                "after": a_opt["recommended"],
                "reason": a_opt["reason"]
            })

    before_esc_ids = {e["id"] for e in before["escalations"]}
    escs_created = [e for e in after["escalations"] if e["id"] not in before_esc_ids]

    new_plans_available = [
        {
            "service": s["service"],
            "recommended": s["recommended"],
            "reason": s["reason"]
        }
        for s in after["savings_optimiser"]
        if s["service"] not in before_opt_map
    ]

    delta = {
        "anomaly_count": after["anomaly_count"] - before["anomaly_count"],
        "new_anomalies": new_anomalies,
        "forecast_30d_delta": round(after["forecast"]["total_30d"] - before["forecast"]["total_30d"], 2),
        "winner_changed": after["forecast"]["winner"] != before["forecast"]["winner"],
        "recommendations_added": recs_added,
        "recommendations_removed": recs_removed,
        "savings_optimiser_changes": opt_changes,
        "new_plans_available": new_plans_available,
        "escalations_created": escs_created,
    }

    return {
        "scenario": scenario,
        "account_id": acc.id,
        "provider": provider,
        "before": before,
        "after": after,
        "delta": delta,
    }


@router.post("/reset")
def reset_demo(
    account_id: str = Query(..., description="Demo Account ID to reset"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Reset a UUID5 demo account to its initial deterministic seeded state.
    Note: A backend restart also resets demo accounts relative to today.
    """
    acc = _validate_uuid5_demo_account(db, current_user, account_id)
    reset_demo_account(db, acc)
    state = _capture_state(db, acc)
    return {
        "message": f"Demo account '{acc.name}' reset to initial clean state successfully",
        "account_id": acc.id,
        "provider": acc.provider,
        "state": state
    }
