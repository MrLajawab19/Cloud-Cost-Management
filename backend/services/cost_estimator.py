"""
services/cost_estimator.py
──────────────────────────
Takes the raw resource list from aws_collector and:
  1. Saves/updates Resource rows in the database.
  2. Appends a daily CostRecord for each resource.
  3. Returns a cost summary dict.
"""

import logging
from datetime import date, datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from models.resource import Resource
from models.cost_record import CostRecord

logger = logging.getLogger(__name__)


def upsert_resources(db: Session, resources: List[Dict[str, Any]]) -> int:
    """
    Insert or update Resource rows based on resource_id.
    Returns count of upserted records.
    """
    count = 0
    for r in resources:
        existing = db.query(Resource).filter(
            Resource.resource_id == r["resource_id"]
        ).first()

        if existing:
            # Update all fields
            for key, value in r.items():
                if hasattr(existing, key) and key not in ("id", "created_at"):
                    setattr(existing, key, value)
            existing.last_seen = datetime.utcnow()
        else:
            obj = Resource(**{k: v for k, v in r.items() if hasattr(Resource, k)})
            db.add(obj)

        count += 1

    db.commit()
    logger.info(f"Upserted {count} resources into DB.")
    return count


def record_daily_costs(db: Session, resources: List[Dict[str, Any]]) -> int:
    """
    Append a CostRecord for today for each resource.
    Skips if a record for today already exists for that resource.
    Returns count of new records inserted.
    """
    today = date.today()
    count = 0

    for r in resources:
        resource_id  = r["resource_id"]
        service_type = r["service_type"]
        region       = r.get("region", "unknown")
        daily_cost   = r.get("estimated_monthly_cost", 0.0) / 30  # monthly → daily

        exists = db.query(CostRecord).filter(
            CostRecord.resource_id == resource_id,
            CostRecord.record_date == today,
        ).first()

        if not exists:
            record = CostRecord(
                resource_id=resource_id,
                service_type=service_type,
                region=region,
                record_date=today,
                daily_cost_usd=round(daily_cost, 6),
                monthly_estimate=r.get("estimated_monthly_cost", 0.0),
            )
            db.add(record)
            count += 1

    db.commit()
    logger.info(f"Recorded {count} new daily cost entries.")
    return count


def get_cost_summary(db: Session) -> Dict[str, Any]:
    """
    Compute a cost summary from the current resource table.
    Returns:
      - total_monthly_cost
      - cost_by_service  { EC2: X, S3: X, RDS: X, Lambda: X }
      - total_resources
      - idle_resources
      - potential_savings (sum of idle resource costs)
    """
    resources = db.query(Resource).all()

    total_cost = 0.0
    cost_by_service: Dict[str, float] = {}
    idle_count = 0
    potential_savings = 0.0

    for r in resources:
        cost = r.estimated_monthly_cost or 0.0
        total_cost += cost
        cost_by_service[r.service_type] = cost_by_service.get(r.service_type, 0.0) + cost

        if r.is_idle:
            idle_count += 1
            potential_savings += cost

    return {
        "total_monthly_cost_usd": round(total_cost, 2),
        "cost_by_service": {k: round(v, 2) for k, v in cost_by_service.items()},
        "total_resources": len(resources),
        "idle_resources": idle_count,
        "potential_savings_usd": round(potential_savings, 2),
        "as_of": datetime.utcnow().isoformat(),
    }


def get_daily_cost_trend(db: Session, days: int = 30) -> List[Dict[str, Any]]:
    """
    Return aggregated daily cost totals for the past N days.
    Used by the frontend cost trend chart.
    """
    from sqlalchemy import func
    from datetime import timedelta

    start_date = date.today() - timedelta(days=days)

    rows = (
        db.query(
            CostRecord.record_date,
            func.sum(CostRecord.daily_cost_usd).label("total_daily_cost"),
        )
        .filter(CostRecord.record_date >= start_date)
        .group_by(CostRecord.record_date)
        .order_by(CostRecord.record_date)
        .all()
    )

    return [
        {"date": str(row.record_date), "cost": round(row.total_daily_cost, 4)}
        for row in rows
    ]
