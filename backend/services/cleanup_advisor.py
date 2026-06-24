"""
services/cleanup_advisor.py
────────────────────────────
Scans the Resource table and generates cleanup recommendations.

Rules:
  EC2  | CPU < 5% for 7+ days AND running       → "Underutilized Instance"
  EC2  | status = stopped                        → "Stopped Instance (EBS cost)"
  S3   | 0 objects AND 0 requests                → "Empty Bucket"
  S3   | > 500 GB AND 0 requests for 30 days     → "Large Unused Bucket"
  RDS  | status = stopped                        → "Stopped RDS (storage cost)"
  Lambda | 0 invocations for 30 days             → "Unused Lambda Function"
"""

import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from models.resource import Resource
from models.cost_record import Recommendation

logger = logging.getLogger(__name__)

# Severity thresholds
HIGH_SAVINGS_THRESHOLD   = 50.0   # USD/month → high severity
MEDIUM_SAVINGS_THRESHOLD = 10.0   # USD/month → medium


def _severity(monthly_cost: float) -> str:
    if monthly_cost >= HIGH_SAVINGS_THRESHOLD:
        return "high"
    elif monthly_cost >= MEDIUM_SAVINGS_THRESHOLD:
        return "medium"
    elif monthly_cost > 0:
        return "low"
    return "low"


def generate_recommendations(db: Session) -> int:
    """
    Clear old recommendations and regenerate from current resource state.
    Returns count of new recommendations created.
    """
    # Clear existing unresolved recommendations
    db.query(Recommendation).filter(Recommendation.is_resolved == False).delete()
    db.commit()

    resources: List[Resource] = db.query(Resource).all()
    recs = []

    for r in resources:
        cost = r.estimated_monthly_cost or 0.0

        # ── EC2 Rules ────────────────────────────────────────────
        if r.service_type == "EC2":

            if r.status == "running" and (r.cpu_utilization_avg or 0) < 5.0 \
                    and (r.runtime_hours or 0) > 168:
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name or r.resource_id,
                    service_type="EC2",
                    region=r.region,
                    issue="Underutilized EC2 Instance",
                    description=(
                        f"Instance {r.resource_name} ({r.resource_type}) has been running "
                        f"for {int((r.runtime_hours or 0) / 24)} days with an average CPU "
                        f"utilization of only {r.cpu_utilization_avg:.1f}%. "
                        f"This is well below the 5% idle threshold."
                    ),
                    action=(
                        "Consider downsizing to a smaller instance type, switching to "
                        "a Spot/Reserved instance, or terminating if no longer needed."
                    ),
                    severity=_severity(cost),
                    potential_savings_usd=round(cost * 0.6, 2),  # ~60% savings by downsizing
                ))

            if r.status == "stopped":
                ebs_cost = 0.10 * 30  # estimate 30 GB EBS at $0.10/GB
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name or r.resource_id,
                    service_type="EC2",
                    region=r.region,
                    issue="Stopped EC2 (EBS Costs Still Accruing)",
                    description=(
                        f"Instance {r.resource_name} is stopped but its EBS volumes "
                        f"continue to incur storage charges (~${ebs_cost:.2f}/month estimated)."
                    ),
                    action=(
                        "Create an AMI snapshot, then terminate the instance and detach "
                        "unused EBS volumes to eliminate ongoing storage costs."
                    ),
                    severity="medium",
                    potential_savings_usd=round(ebs_cost, 2),
                ))

        # ── S3 Rules ─────────────────────────────────────────────
        elif r.service_type == "S3":

            if (r.storage_size_gb or 0) < 0.001 and (r.request_count or 0) == 0:
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name,
                    service_type="S3",
                    region=r.region,
                    issue="Empty S3 Bucket",
                    description=(
                        f"Bucket '{r.resource_name}' contains no objects and has received "
                        f"no requests. It may be a leftover from a deprecated feature."
                    ),
                    action=(
                        "Verify the bucket is not referenced by any active application, "
                        "then delete it to keep your account tidy."
                    ),
                    severity="low",
                    potential_savings_usd=0.0,
                ))

            elif (r.storage_size_gb or 0) > 500 and (r.request_count or 0) == 0:
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name,
                    service_type="S3",
                    region=r.region,
                    issue="Large Unused S3 Bucket",
                    description=(
                        f"Bucket '{r.resource_name}' holds {r.storage_size_gb:.1f} GB "
                        f"but has received zero requests. This data may be stale."
                    ),
                    action=(
                        "Review bucket contents. Move infrequently accessed data to "
                        "S3 Glacier (90% cheaper) or delete if no longer needed."
                    ),
                    severity=_severity(cost),
                    potential_savings_usd=round(cost * 0.9, 2),
                ))

        # ── RDS Rules ────────────────────────────────────────────
        elif r.service_type == "RDS":

            if r.status == "stopped":
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name,
                    service_type="RDS",
                    region=r.region,
                    issue="Stopped RDS Instance (Storage Cost)",
                    description=(
                        f"RDS instance '{r.resource_name}' is stopped but you are still "
                        f"being charged for {r.storage_size_gb or 0:.0f} GB of storage "
                        f"at ~$0.115/GB/month."
                    ),
                    action=(
                        "Take a final snapshot and delete the instance if no longer needed. "
                        "Restore from snapshot when required."
                    ),
                    severity="medium",
                    potential_savings_usd=round((r.storage_size_gb or 0) * 0.115, 2),
                ))

        # ── Lambda Rules ─────────────────────────────────────────
        elif r.service_type == "Lambda":

            if (r.request_count or 0) == 0:
                recs.append(Recommendation(
                    account_id=r.account_id,
                    resource_id=r.resource_id,
                    resource_name=r.resource_name,
                    service_type="Lambda",
                    region=r.region,
                    issue="Unused Lambda Function",
                    description=(
                        f"Lambda function '{r.resource_name}' has had zero invocations "
                        f"in the past 30 days. It may be an orphaned deployment."
                    ),
                    action=(
                        "Verify the function is not triggered by a rare schedule. "
                        "If unused, delete it to reduce attack surface and clutter."
                    ),
                    severity="low",
                    potential_savings_usd=0.0,
                ))

    if recs:
        db.add_all(recs)
        db.commit()

    logger.info(f"Generated {len(recs)} cleanup recommendations.")
    return len(recs)
