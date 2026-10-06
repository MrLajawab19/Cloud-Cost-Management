"""
services/cleanup_advisor.py
----------------------------
Scans the Resource table and generates cleanup recommendations.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import uuid

from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import EscalationState

logger = logging.getLogger(__name__)

HIGH_SAVINGS_THRESHOLD   = 50.0   
MEDIUM_SAVINGS_THRESHOLD = 10.0   

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
    Generate or update recommendations using UPSERT.
    Resolves stale recommendations if their resource condition changed.
    """
    resources = db.query(Resource).all()
    
    # We will collect all generated natural keys to find stale ones.
    # Natural key: (account_id, resource_id, issue)
    current_cycle_keys = set()
    new_recs_count = 0

    for r in resources:
        cost = r.estimated_monthly_cost or 0.0
        
        # -- EC2 Rules --------------------------------------------
        if r.service_type == "EC2":
            if r.status == "running" and (r.runtime_hours or 0) > 168:
                cpu = r.cpu_utilization_avg or 0
                
                # Rule 1: Idle EC2 (Stop)
                if cpu < 1.0:
                    _upsert_rec(db, current_cycle_keys, r, 
                        issue="Idle EC2 Instance",
                        desc=f"Instance {r.resource_name} ({r.resource_type}) has {cpu:.1f}% CPU. It is completely idle.",
                        action="Stop the instance.",
                        remediation_type="stop",
                        severity=_severity(cost),
                        savings=cost)
                        
                # Rule 2: Underutilized EC2 (Resize)
                elif 1.0 <= cpu < 5.0:
                    _upsert_rec(db, current_cycle_keys, r, 
                        issue="Underutilized EC2 Instance",
                        desc=f"Instance {r.resource_name} ({r.resource_type}) has {cpu:.1f}% CPU. It is underutilized.",
                        action="Consider downsizing to a smaller instance type.",
                        remediation_type="resize",
                        severity=_severity(cost),
                        savings=round(cost * 0.6, 2))

            if r.status == "stopped":
                ebs_cost = 0.10 * 30 
                _upsert_rec(db, current_cycle_keys, r, 
                    issue="Stopped EC2 (EBS Costs Still Accruing)",
                    desc=f"Instance {r.resource_name} is stopped but its EBS volumes incur ~${ebs_cost:.2f}/month.",
                    action="Create an AMI snapshot, then terminate.",
                    remediation_type="manual",
                    severity="medium",
                    savings=round(ebs_cost, 2))

        # -- S3 Rules ---------------------------------------------
        elif r.service_type == "S3":
            if (r.storage_size_gb or 0) < 0.001 and (r.request_count or 0) == 0:
                _upsert_rec(db, current_cycle_keys, r, 
                    issue="Empty S3 Bucket",
                    desc=f"Bucket '{r.resource_name}' contains no objects and 0 requests.",
                    action="Delete the bucket.",
                    remediation_type="manual",
                    severity="low",
                    savings=0.0)

            elif (r.storage_size_gb or 0) > 500 and (r.request_count or 0) == 0:
                _upsert_rec(db, current_cycle_keys, r, 
                    issue="Large Unused S3 Bucket",
                    desc=f"Bucket '{r.resource_name}' holds {r.storage_size_gb:.1f} GB with zero requests.",
                    action="Move to Glacier or delete.",
                    remediation_type="manual",
                    severity=_severity(cost),
                    savings=round(cost * 0.9, 2))

        # -- RDS Rules --------------------------------------------
        elif r.service_type == "RDS":
            if r.status == "stopped":
                _upsert_rec(db, current_cycle_keys, r, 
                    issue="Stopped RDS Instance (Storage Cost)",
                    desc=f"RDS '{r.resource_name}' is stopped but charged for {(r.storage_size_gb or 0):.0f} GB.",
                    action="Take snapshot and delete.",
                    remediation_type="manual",
                    severity="medium",
                    savings=round((r.storage_size_gb or 0) * 0.115, 2))

        # -- Lambda Rules -----------------------------------------
        elif r.service_type == "Lambda":
            if (r.request_count or 0) == 0:
                _upsert_rec(db, current_cycle_keys, r, 
                    issue="Unused Lambda Function",
                    desc=f"Lambda '{r.resource_name}' has 0 invocations in 30 days.",
                    action="Delete the function.",
                    remediation_type="manual",
                    severity="low",
                    savings=0.0)

        # -- AzureVM Rules ----------------------------------------
        elif r.service_type == "AzureVM":
            if r.status == "running":
                # Real CPU metrics from Azure Monitor (or None if missing/unavailable)
                cpu = r.cpu_utilization_avg or 0.0
                if cpu < 1.0:
                    _upsert_rec(db, current_cycle_keys, r, 
                        issue="Idle AzureVM",
                        desc=f"Azure VM {r.resource_name} ({r.resource_type}) is completely idle.",
                        action="Stop the instance.",
                        remediation_type="manual",
                        severity=_severity(cost),
                        savings=cost)
                elif 1.0 <= cpu < 5.0:
                    _upsert_rec(db, current_cycle_keys, r, 
                        issue="Underutilized AzureVM",
                        desc=f"Azure VM {r.resource_name} ({r.resource_type}) is underutilized.",
                        action="Consider downsizing to a smaller instance type.",
                        remediation_type="manual",
                        severity=_severity(cost),
                        savings=round(cost * 0.6, 2))

    db.commit()
    
    # --- STALE CLEANUP PHASE ---
    # Scoped explicitly to the set of issues generated by cleanup_advisor.
    # This prevents blindly resolving SP recommendations or other external sources.
    ADVISOR_ISSUES = [
        "Idle EC2 Instance",
        "Underutilized EC2 Instance",
        "Stopped EC2 (EBS Costs Still Accruing)",
        "Empty S3 Bucket",
        "Large Unused S3 Bucket",
        "Stopped RDS Instance (Storage Cost)",
        "Unused Lambda Function",
        "Idle AzureVM",
        "Underutilized AzureVM"
    ]
    
    all_active = db.query(Recommendation).filter(
        Recommendation.is_resolved == False,
        Recommendation.issue.in_(ADVISOR_ISSUES)
    ).all()
    
    stale_count = 0
    for rec in all_active:
        key = (rec.account_id, rec.resource_id, rec.issue)
        if key not in current_cycle_keys:
            # Mark as resolved
            rec.is_resolved = True
            rec.resolved_at = datetime.utcnow()
            stale_count += 1
            
            # Cancel any associated pending escalation
            escalation = db.query(EscalationState).filter(
                EscalationState.recommendation_id == str(rec.id),
                EscalationState.status.in_(["pending", "escalated"])
            ).first()
            if escalation:
                escalation.status = "cancelled"
                logger.info(f"Cancelled escalation {escalation.id} because recommendation went stale.")
                
    db.commit()
    logger.info(f"Generated/Updated recs. Stale resolved: {stale_count}.")
    return len(current_cycle_keys)

def _upsert_rec(db: Session, keys_set: set, r: Resource, issue: str, desc: str, action: str, remediation_type: str, severity: str, savings: float):
    # Natural key check
    key = (r.account_id, r.resource_id, issue)
    keys_set.add(key)
    
    # Look for existing unresolved recommendation with this key
    existing = db.query(Recommendation).filter(
        Recommendation.account_id == r.account_id,
        Recommendation.resource_id == r.resource_id,
        Recommendation.issue == issue,
        Recommendation.is_resolved == False
    ).first()
    
    if existing:
        # Update fields (e.g. savings might have changed)
        existing.description = desc
        existing.action = action
        existing.severity = severity
        existing.potential_savings_usd = savings
        existing.remediation_type = remediation_type
    else:
        # Create new
        new_rec = Recommendation(
            id=uuid.uuid4(),
            account_id=r.account_id,
            resource_id=r.resource_id,
            resource_name=r.resource_name or r.resource_id,
            service_type=r.service_type,
            region=r.region,
            issue=issue,
            description=desc,
            action=action,
            severity=severity,
            potential_savings_usd=savings,
            remediation_type=remediation_type
        )
        db.add(new_rec)
        db.flush() # ensure new_rec.id is available
        
        # If it's a "stop" action, generate EscalationState immediately.
        # It's created ONLY ONCE on INSERT.
        if remediation_type == "stop":
            from models.account import CloudAccount
            from datetime import timedelta
            account = db.query(CloudAccount).filter(CloudAccount.id == r.account_id).first()
            grace_hours = account.grace_period_hours if account else 48
            
            escalation = EscalationState(
                id=str(uuid.uuid4()),
                recommendation_id=str(new_rec.id),
                status="pending",
                due_at=datetime.utcnow() + timedelta(hours=grace_hours)
            )
            db.add(escalation)

