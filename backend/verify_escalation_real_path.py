"""
backend/verify_escalation_real_path.py
Runs the REAL generate_recommendations for an idle EC2 on an in-memory DB
built exactly the way database.py builds its engine.
Runs twice: with foreign_keys=ON and foreign_keys=OFF.
"""

import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from database import Base
import models.user
import models.account
import models.resource
import models.cost_record
import models.remediation
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import EscalationState
from services.cleanup_advisor import generate_recommendations


def test_with_fk(foreign_keys_on: bool):
    label = "ON" if foreign_keys_on else "OFF"
    print(f"\n{'='*20} Testing with PRAGMA foreign_keys={label} {'='*20}")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys_on else 'OFF'}")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    user = User(
        id=str(uuid.uuid4()),
        email=f"esc_{label.lower()}@example.com",
        password_hash="hash",
    )
    db.add(user)
    db.commit()

    account = CloudAccount(
        id=f"acc-esc-{label.lower()}",
        user_id=user.id,
        name=f"Escalation Account {label}",
        provider="aws",
        region="us-east-1",
        auto_remediate_enabled=True,
        grace_period_hours=48,
    )
    db.add(account)
    db.commit()

    r = Resource(
        id=uuid.uuid4(),
        resource_id=f"i-idle-ec2-{label.lower()}",
        account_id=account.id,
        resource_name=f"idle-ec2-{label.lower()}",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(r)
    db.commit()

    rec_created = False
    esc_created = False
    exc_info = None

    try:
        generate_recommendations(db)
        recs = db.query(Recommendation).filter(Recommendation.resource_id == r.resource_id).all()
        rec_created = len(recs) > 0
        escs = db.query(EscalationState).all()
        esc_created = len(escs) > 0
    except Exception as e:
        exc_info = f"{type(e).__name__}: {e}"

    print(f"Recommendation created?: {rec_created}")
    print(f"Escalation row created?: {esc_created}")
    print(f"Any exception?:          {exc_info if exc_info else 'None'}")

    db.close()
    return rec_created, esc_created, exc_info


def main():
    print("=== ESCALATION REAL PATH VERIFICATION ===")
    test_with_fk(foreign_keys_on=True)
    test_with_fk(foreign_keys_on=False)


if __name__ == "__main__":
    main()
