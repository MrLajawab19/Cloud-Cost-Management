"""
services/demo_data.py
Deterministic synthetic demo data generation and demo account lifecycle management.
No external network, boto3, azure-identity/mgmt, or requests imports.
"""

import math
import random
import uuid
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import CostRecord, Recommendation, format_recommendation_id_fk
from models.remediation import EscalationState, RemediationLog
from models.anomaly import Anomaly
from services.cost_estimator import is_aws_real, is_azure_real

logger = logging.getLogger(__name__)


def generate_demo_resources(account: CloudAccount) -> List[Dict[str, Any]]:
    """
    Generate deterministic resource dicts in the collector format for the demo account.
    """
    rng = random.Random(str(account.id))
    now = datetime.now(timezone.utc)
    acc_id = str(account.id)

    if account.provider == "aws":
        return [
            # 1. Idle EC2 (CPU 0.3, runtime 300h) -> Stop recommendation
            {
                "account_id": acc_id,
                "resource_id": f"i-demo-idle-{acc_id[:8]}",
                "resource_name": "demo-idle-worker",
                "service_type": "EC2",
                "region": account.region or "us-east-1",
                "status": "running",
                "resource_type": "t3.medium",
                "tags": '{"Env":"demo","Role":"worker"}',
                "cpu_utilization_avg": 0.3,
                "runtime_hours": 300.0,
                "estimated_monthly_cost": 40.0,
                "daily_cost_usd": round(40.0 / 30.0, 4),
                "launch_time": now - timedelta(days=20),
                "is_idle": True,
            },
            # 2. Underutilized EC2 (CPU 3.2, resize) -> Resize recommendation
            {
                "account_id": acc_id,
                "resource_id": f"i-demo-resize-{acc_id[:8]}",
                "resource_name": "demo-underutilized-api",
                "service_type": "EC2",
                "region": account.region or "us-east-1",
                "status": "running",
                "resource_type": "t3.medium",
                "tags": '{"Env":"demo","Role":"api"}',
                "cpu_utilization_avg": 3.2,
                "runtime_hours": 300.0,
                "estimated_monthly_cost": 40.0,
                "daily_cost_usd": round(40.0 / 30.0, 4),
                "launch_time": now - timedelta(days=20),
                "is_idle": False,
            },
            # 3. Stopped EC2 with EBS -> Stopped EC2 recommendation
            {
                "account_id": acc_id,
                "resource_id": f"i-demo-stopped-{acc_id[:8]}",
                "resource_name": "demo-stopped-batch",
                "service_type": "EC2",
                "region": account.region or "us-east-1",
                "status": "stopped",
                "resource_type": "t3.large",
                "tags": '{"Env":"demo","Role":"batch"}',
                "cpu_utilization_avg": 0.0,
                "runtime_hours": 0.0,
                "estimated_monthly_cost": 3.0,
                "daily_cost_usd": 0.10,
                "launch_time": now - timedelta(days=40),
                "is_idle": True,
            },
            # 4. Empty S3 -> Empty S3 recommendation
            {
                "account_id": acc_id,
                "resource_id": f"demo-empty-bucket-{acc_id[:8]}",
                "resource_name": "demo-empty-bucket",
                "service_type": "S3",
                "region": account.region or "us-east-1",
                "status": "available",
                "resource_type": "S3 Bucket",
                "tags": '{"Env":"demo"}',
                "storage_size_gb": 0.0,
                "request_count": 0,
                "estimated_monthly_cost": 0.0,
                "daily_cost_usd": 0.0,
                "launch_time": now - timedelta(days=60),
                "is_idle": True,
            },
            # 5. Large unused S3 (600 GB) -> Large unused S3 recommendation
            {
                "account_id": acc_id,
                "resource_id": f"demo-large-unused-bucket-{acc_id[:8]}",
                "resource_name": "demo-large-unused-bucket",
                "service_type": "S3",
                "region": account.region or "us-east-1",
                "status": "available",
                "resource_type": "S3 Bucket",
                "tags": '{"Env":"demo"}',
                "storage_size_gb": 600.0,
                "request_count": 0,
                "estimated_monthly_cost": 13.80,
                "daily_cost_usd": 0.46,
                "launch_time": now - timedelta(days=120),
                "is_idle": True,
            },
            # 6. Unused Lambda -> Unused Lambda recommendation
            {
                "account_id": acc_id,
                "resource_id": f"arn:aws:lambda:us-east-1:123456789012:function:demo-unused-{acc_id[:8]}",
                "resource_name": "demo-unused-function",
                "service_type": "Lambda",
                "region": account.region or "us-east-1",
                "status": "active",
                "resource_type": "python3.11",
                "tags": '{"Env":"demo"}',
                "request_count": 0,
                "estimated_monthly_cost": 0.0,
                "daily_cost_usd": 0.0,
                "launch_time": None,
                "is_idle": True,
            },
            # 7. Stopped RDS -> Stopped RDS recommendation
            {
                "account_id": acc_id,
                "resource_id": f"demo-stopped-rds-{acc_id[:8]}",
                "resource_name": "demo-stopped-db",
                "service_type": "RDS",
                "region": account.region or "us-east-1",
                "status": "stopped",
                "resource_type": "db.t3.medium",
                "tags": '{"Env":"demo"}',
                "storage_size_gb": 50.0,
                "estimated_monthly_cost": 5.76,
                "daily_cost_usd": 0.192,
                "launch_time": now - timedelta(days=50),
                "is_idle": True,
            },
            # 8. Normal running resources
            {
                "account_id": acc_id,
                "resource_id": f"i-demo-running-prod-{acc_id[:8]}",
                "resource_name": "demo-prod-backend",
                "service_type": "EC2",
                "region": account.region or "us-east-1",
                "status": "running",
                "resource_type": "m5.large",
                "tags": '{"Env":"prod","Role":"backend"}',
                "cpu_utilization_avg": 65.0,
                "runtime_hours": 720.0,
                "estimated_monthly_cost": 95.0,
                "daily_cost_usd": round((5.775 + 0.005 * 45 + 0.12 * math.sin(45 * 1.5)) - (40.0 / 30.0 + 40.0 / 30.0 + 0.10), 4),
                "launch_time": now - timedelta(days=60),
                "is_idle": False,
            },
            {
                "account_id": acc_id,
                "resource_id": f"demo-prod-assets-s3-{acc_id[:8]}",
                "resource_name": "demo-prod-assets",
                "service_type": "S3",
                "region": account.region or "us-east-1",
                "status": "available",
                "resource_type": "S3 Bucket",
                "tags": '{"Env":"prod"}',
                "storage_size_gb": 250.0,
                "request_count": 50000,
                "estimated_monthly_cost": 10.20,
                "daily_cost_usd": 0.34,
                "launch_time": now - timedelta(days=180),
                "is_idle": False,
            },
            {
                "account_id": acc_id,
                "resource_id": f"demo-prod-rds-main-{acc_id[:8]}",
                "resource_name": "demo-prod-database",
                "service_type": "RDS",
                "region": account.region or "us-east-1",
                "status": "available",
                "resource_type": "db.m5.large",
                "tags": '{"Env":"prod"}',
                "storage_size_gb": 100.0,
                "estimated_monthly_cost": 140.04,
                "daily_cost_usd": 4.668,
                "launch_time": now - timedelta(days=120),
                "is_idle": False,
            },
            {
                "account_id": acc_id,
                "resource_id": f"arn:aws:lambda:us-east-1:123456789012:function:demo-prod-{acc_id[:8]}",
                "resource_name": "demo-prod-api-handler",
                "service_type": "Lambda",
                "region": account.region or "us-east-1",
                "status": "active",
                "resource_type": "python3.11",
                "tags": '{"Env":"prod"}',
                "request_count": 100000,
                "estimated_monthly_cost": 1.50,
                "daily_cost_usd": 0.05,
                "launch_time": None,
                "is_idle": False,
            },
        ]
    elif account.provider == "azure":
        return [
            # 1. Idle VM (Standard_B2s, cpu 0.4, runtime 250h) -> Idle AzureVM recommendation
            {
                "account_id": acc_id,
                "resource_id": f"demo-azure-vm-idle-{acc_id[:8]}",
                "resource_name": "demo-azure-idle-vm",
                "service_type": "AzureVM",
                "resource_type": "Standard_B2s",
                "region": account.region or "eastus",
                "status": "running",
                "cpu_utilization_avg": 0.4,
                "runtime_hours": 250.0,
                "storage_size_gb": 64.0,
                "estimated_monthly_cost": 36.0,
                "daily_cost_usd": 1.20,
                "launch_time": now - timedelta(days=15),
                "is_idle": True,
            },
            # 2. Underutilized VM (Standard_B2s, cpu 3.5, runtime 250h) -> Underutilized AzureVM recommendation
            {
                "account_id": acc_id,
                "resource_id": f"demo-azure-vm-resize-{acc_id[:8]}",
                "resource_name": "demo-azure-underutilized-vm",
                "service_type": "AzureVM",
                "resource_type": "Standard_B2s",
                "region": account.region or "eastus",
                "status": "running",
                "cpu_utilization_avg": 3.5,
                "runtime_hours": 250.0,
                "storage_size_gb": 64.0,
                "estimated_monthly_cost": 36.0,
                "daily_cost_usd": 1.20,
                "launch_time": now - timedelta(days=15),
                "is_idle": False,
            },
            # 3. Stable VM (Standard_D2s_v3, running, cpu 45.0, runtime 500h)
            {
                "account_id": acc_id,
                "resource_id": f"demo-azure-vm-stable-{acc_id[:8]}",
                "resource_name": "demo-azure-stable-vm",
                "service_type": "AzureVM",
                "resource_type": "Standard_D2s_v3",
                "region": account.region or "eastus",
                "status": "running",
                "cpu_utilization_avg": 45.0,
                "runtime_hours": 500.0,
                "storage_size_gb": 128.0,
                "estimated_monthly_cost": 348.0,
                "daily_cost_usd": 11.60,
                "launch_time": now - timedelta(days=40),
                "is_idle": False,
            },
            # 4. Stopped VM (Standard_B2s, status="stopped")
            {
                "account_id": acc_id,
                "resource_id": f"demo-azure-vm-stopped-{acc_id[:8]}",
                "resource_name": "demo-azure-stopped-vm",
                "service_type": "AzureVM",
                "resource_type": "Standard_B2s",
                "region": account.region or "eastus",
                "status": "stopped",
                "cpu_utilization_avg": None,
                "runtime_hours": 0.0,
                "storage_size_gb": 64.0,
                "estimated_monthly_cost": 1.5,
                "daily_cost_usd": 0.05,
                "launch_time": now - timedelta(days=25),
                "is_idle": True,
            },
        ]
    return []


def seed_demo_history(db: Session, account: CloudAccount, days: int = 45):
    """
    Generate deterministic history >= 45 days.
    History: low noise + deliberate EC2 cost spike (+80% for 2 days) 9-11 days before today.
    """
    today = date.today()
    acc_id = str(account.id)

    if account.provider == "aws":
        profiles = {
            "EC2":    {"base": 5.775, "trend": 0.005},
            "RDS":    {"base": 4.815, "trend": 0.001},
            "S3":     {"base": 0.7775, "trend": 0.0005},
            "Lambda": {"base": 0.05, "trend": 0.0},
        }
        rng = random.Random(9999)
        sigma = 0.02
        weekly_amp = 0.02
        spike_mult = 1.5

        for day_offset in range(days, 0, -1):
            rec_date = today - timedelta(days=day_offset)
            t = days - day_offset
            for svc, p in profiles.items():
                trend = p["trend"] * t
                weekly = weekly_amp * math.sin(2 * math.pi * t / 7.0)
                raw_noise = rng.gauss(0, sigma)
                clipped_noise = max(-2 * sigma, min(2 * sigma, raw_noise))
                daily_cost = p["base"] * (1.0 + weekly + clipped_noise) + trend

                # ONE deliberate single-day EC2 cost spike 12 days before today
                if svc == "EC2" and day_offset == 12:
                    daily_cost *= spike_mult

                source = "synthetic_seed" if day_offset > 1 else "aws_demo"
                cr = CostRecord(
                    account_id=acc_id,
                    resource_id=None,
                    service_type=svc,
                    region=account.region or "us-east-1",
                    record_date=rec_date,
                    daily_cost_usd=round(max(0.001, daily_cost), 6),
                    monthly_estimate=round(daily_cost * 30, 4),
                    source=source,
                )
                db.add(cr)

    elif account.provider == "azure":
        profile = {"base": 13.87, "trend": 0.004}
        rng = random.Random(101)
        sigma = 0.02
        weekly_amp = 0.02
        spike_mult = 1.3

        for day_offset in range(days, 0, -1):
            rec_date = today - timedelta(days=day_offset)
            t = days - day_offset
            trend = profile["trend"] * t
            weekly = weekly_amp * math.sin(2 * math.pi * t / 7.0)
            raw_noise = rng.gauss(0, sigma)
            clipped_noise = max(-2 * sigma, min(2 * sigma, raw_noise))
            daily_cost = profile["base"] * (1.0 + weekly + clipped_noise) + trend

            # ONE small single-day AzureVM cost spike 7 days before today
            if day_offset == 7:
                daily_cost *= spike_mult

            source = "synthetic_seed" if day_offset > 1 else "azure_demo"
            cr = CostRecord(
                account_id=acc_id,
                resource_id=None,
                service_type="AzureVM",
                region=account.region or "eastus",
                record_date=rec_date,
                daily_cost_usd=round(max(0.001, daily_cost), 6),
                monthly_estimate=round(daily_cost * 30, 4),
                source=source,
            )
            db.add(cr)

    db.commit()


def ensure_demo_accounts(db: Session, user_id: str):
    """
    Ensure Demo AWS and Demo Azure accounts exist for user_id with uuid.uuid5 ids.
    Grace period is set to 1 hour so pending escalations mature shortly after initial run.
    """
    u_uuid = uuid.UUID(str(user_id))
    aws_id = str(uuid.uuid5(u_uuid, "demo-aws"))
    azure_id = str(uuid.uuid5(u_uuid, "demo-azure"))

    acc_aws = db.query(CloudAccount).filter(CloudAccount.id == aws_id).first()
    if not acc_aws:
        acc_aws = CloudAccount(
            id=aws_id,
            user_id=str(user_id),
            name="Demo AWS",
            provider="aws",
            region="us-east-1",
            access_key_id="",
            encrypted_secret_key="",
            auto_remediate_enabled=True,
            grace_period_hours=1,
            budget_threshold_usd=500.0,
        )
        db.add(acc_aws)
    else:
        acc_aws.name = "Demo AWS"
        acc_aws.auto_remediate_enabled = True
        acc_aws.grace_period_hours = 1
        acc_aws.budget_threshold_usd = 500.0

    acc_azure = db.query(CloudAccount).filter(CloudAccount.id == azure_id).first()
    if not acc_azure:
        acc_azure = CloudAccount(
            id=azure_id,
            user_id=str(user_id),
            name="Demo Azure",
            provider="azure",
            region="eastus",
            tenant_id="",
            client_id="",
            encrypted_client_secret="",
            subscription_id="",
            auto_remediate_enabled=True,
            grace_period_hours=1,
            budget_threshold_usd=500.0,
        )
        db.add(acc_azure)
    else:
        acc_azure.name = "Demo Azure"
        acc_azure.auto_remediate_enabled = True
        acc_azure.grace_period_hours = 1
        acc_azure.budget_threshold_usd = 500.0

    db.commit()
    return acc_aws, acc_azure


def reset_demo_account(db: Session, acc: CloudAccount):
    """
    Reset a demo account relative to today.
    Deletes only that account's rows in FK-safe order:
      remediation_logs -> escalation_states -> recommendations -> anomalies -> cost_records -> resources.
    Must assert the account has NO credentials before deleting anything.
    """
    assert not (is_aws_real(acc) or is_azure_real(acc)), (
        f"Security violation: Refusing to reset account {acc.id} because it has real credentials!"
    )

    acc_id = str(acc.id)

    # 1. RemediationLog
    db.query(RemediationLog).filter(RemediationLog.account_id == acc_id).delete(synchronize_session=False)

    # 2. EscalationState (FK references recommendations)
    rec_ids = [r.id for r in db.query(Recommendation).filter(Recommendation.account_id == acc_id).all()]
    if rec_ids:
        rec_fks = [format_recommendation_id_fk(rid, db) for rid in rec_ids] + [str(rid) for rid in rec_ids]
        db.query(EscalationState).filter(EscalationState.recommendation_id.in_(rec_fks)).delete(synchronize_session=False)

    # 3. Recommendation
    db.query(Recommendation).filter(Recommendation.account_id == acc_id).delete(synchronize_session=False)

    # 4. Anomaly
    db.query(Anomaly).filter(Anomaly.account_id == acc_id).delete(synchronize_session=False)

    # 5. CostRecord
    db.query(CostRecord).filter(CostRecord.account_id == acc_id).delete(synchronize_session=False)

    # 6. Resource
    db.query(Resource).filter(Resource.account_id == acc_id).delete(synchronize_session=False)

    db.commit()

    # Regenerate relative to today
    res_dicts = generate_demo_resources(acc)
    for rd in res_dicts:
        r = Resource(
            id=uuid.uuid4(),
            account_id=acc_id,
            resource_id=rd["resource_id"],
            resource_name=rd["resource_name"],
            service_type=rd["service_type"],
            region=rd["region"],
            status=rd["status"],
            resource_type=rd.get("resource_type"),
            tags=rd.get("tags"),
            cpu_utilization_avg=rd.get("cpu_utilization_avg"),
            runtime_hours=rd.get("runtime_hours"),
            storage_size_gb=rd.get("storage_size_gb"),
            request_count=rd.get("request_count"),
            estimated_monthly_cost=rd.get("estimated_monthly_cost"),
            last_seen=datetime.now(timezone.utc),
        )
        db.add(r)
    db.commit()

    seed_demo_history(db, acc, days=45)

    from services.cleanup_advisor import generate_recommendations
    from services.savings_plan_optimiser import generate_sp_recommendations
    from services.anomaly_detector import detect_anomalies

    generate_recommendations(db)
    generate_sp_recommendations(db, acc_id)
    detect_anomalies(db, [acc_id])
    db.commit()
