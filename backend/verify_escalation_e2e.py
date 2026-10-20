"""
backend/verify_escalation_e2e.py
End-to-end verification of escalation workflow with foreign_keys=ON:
1. Account with auto_remediate_enabled=True and idle EC2 (cpu 0.3, runtime 300, cost 40)
   -> generate_recommendations()
   -> EscalationState pending with due_at ~ created + grace
   -> advance time past due (monkeypatch datetime in escalation_manager)
   -> call process_escalations(db)
   -> RemediationLog with status 'simulated' and escalation closed (resolved)
2. Repeat for resize (underutilized EC2, cpu 3.2, runtime 300, cost 40)
   -> generate_recommendations()
   -> Recommendation created (resize)
   -> No EscalationState created (only 'stop' triggers escalation)
3. Print rows and report whether verify_fr7.py ever exercised escalation creation with FK ON.
"""

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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
from models.remediation import EscalationState, RemediationLog
from services.cleanup_advisor import generate_recommendations
from services.escalation_manager import process_escalations


def build_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def main():
    print("=== BACKEND ESCALATION E2E VERIFICATION (FK ON) ===")
    engine = build_engine()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    # 1. Setup User and Account
    user = User(
        id=str(uuid.uuid4()),
        email="e2e_esc@example.com",
        password_hash="fakehash",
    )
    db.add(user)
    db.commit()

    grace_hours = 48
    account = CloudAccount(
        id="acc-e2e-esc-aws",
        user_id=user.id,
        name="E2E Escalation Account",
        provider="aws",
        region="us-east-1",
        auto_remediate_enabled=True,
        grace_period_hours=grace_hours,
    )
    db.add(account)
    db.commit()

    print("\n--- Part 1: Idle EC2 (Stop Remediation & Escalation) ---")
    idle_res = Resource(
        id=uuid.uuid4(),
        resource_id="i-e2e-idle-ec2",
        account_id=account.id,
        resource_name="idle-ec2-test",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(idle_res)
    db.commit()

    # Generate recommendations
    recs_count = generate_recommendations(db)
    print(f"generate_recommendations returned count: {recs_count}")

    rec = db.query(Recommendation).filter_by(resource_id=idle_res.resource_id).first()
    assert rec is not None, "Expected Recommendation for idle EC2"
    print(f"Recommendation created: ID={rec.id} Issue='{rec.issue}' RemediationType='{rec.remediation_type}' Savings=${rec.potential_savings_usd}")

    esc = db.query(EscalationState).first()
    assert esc is not None, "Expected EscalationState for idle EC2 stop recommendation"
    print(f"EscalationState created: ID={esc.id} RecFK={esc.recommendation_id} Status={esc.status} DueAt={esc.due_at}")

    # Verify due_at is approximately created_at + grace_hours
    expected_due = esc.created_at + timedelta(hours=grace_hours)
    diff_seconds = abs((esc.due_at - expected_due).total_seconds())
    assert diff_seconds < 10, f"due_at difference too large: {diff_seconds}s"
    assert esc.status == "pending", f"Expected pending status, got {esc.status}"

    # Advance time past due_at and process escalations
    future_time = esc.due_at + timedelta(hours=2)
    print(f"\nAdvancing time to {future_time} (past due_at {esc.due_at})")

    # Monkeypatch datetime.utcnow in services.escalation_manager
    class MockDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return future_time

    with patch("services.escalation_manager.datetime", MockDatetime):
        processed_count = process_escalations(db)

    print(f"process_escalations executed: {processed_count}")

    db.refresh(esc)
    db.refresh(rec)
    print(f"EscalationState after processing: Status={esc.status}")
    assert esc.status == "resolved", f"Expected EscalationState status 'resolved', got {esc.status}"
    assert rec.is_resolved is True, f"Expected Recommendation is_resolved True, got {rec.is_resolved}"

    # Check RemediationLog
    logs = db.query(RemediationLog).all()
    print(f"RemediationLog rows found: {len(logs)}")
    for l in logs:
        print(f"  RemediationLog: ID={l.id} Resource={l.resource_id} Action={l.action_type} Status='{l.status}' Reason='{l.trigger_reason}'")
    assert len(logs) == 1, f"Expected 1 RemediationLog, got {len(logs)}"
    assert logs[0].status == "simulated", f"Expected status 'simulated', got {logs[0].status}"

    print("\n--- Part 2: Underutilized EC2 (Resize Remediation) ---")
    resize_res = Resource(
        id=uuid.uuid4(),
        resource_id="i-e2e-resize-ec2",
        account_id=account.id,
        resource_name="resize-ec2-test",
        service_type="EC2",
        region="us-east-1",
        status="running",
        resource_type="t3.medium",
        cpu_utilization_avg=3.2,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
        last_seen=datetime.now(timezone.utc),
    )
    db.add(resize_res)
    db.commit()

    generate_recommendations(db)

    resize_rec = db.query(Recommendation).filter_by(resource_id=resize_res.resource_id).first()
    assert resize_rec is not None, "Expected Recommendation for resize EC2"
    print(f"Recommendation created: ID={resize_rec.id} Issue='{resize_rec.issue}' RemediationType='{resize_rec.remediation_type}' Savings=${resize_rec.potential_savings_usd}")
    assert resize_rec.remediation_type == "resize", f"Expected 'resize', got {resize_rec.remediation_type}"

    # Check that NO new EscalationState was created for the resize recommendation
    resize_escs = db.query(EscalationState).filter(
        EscalationState.recommendation_id.in_([str(resize_rec.id), str(resize_rec.id).replace("-", "")])
    ).all()
    print(f"EscalationState rows for resize recommendation: {len(resize_escs)}")
    assert len(resize_escs) == 0, f"Expected 0 EscalationState rows for resize, got {len(resize_escs)}"

    print("\n--- Rows Summary ---")
    print(f"Total Recommendations: {db.query(Recommendation).count()}")
    for r in db.query(Recommendation).all():
        print(f"  Rec: id={r.id} res={r.resource_id} issue='{r.issue}' type={r.remediation_type} resolved={r.is_resolved}")
    print(f"Total EscalationState: {db.query(EscalationState).count()}")
    for e in db.query(EscalationState).all():
        print(f"  Esc: id={e.id} rec_id={e.recommendation_id} status={e.status} due_at={e.due_at}")
    print(f"Total RemediationLog: {db.query(RemediationLog).count()}")
    for l in db.query(RemediationLog).all():
        print(f"  Log: id={l.id} res={l.resource_id} action={l.action_type} status={l.status}")

    print("\n--- Question Analysis: Did verify_fr7.py ever exercise escalation creation with foreign keys ON? ---")
    print("Answer: NO. verify_fr7.py was committed on Sun Oct 4 12:28:42 2026 (commit 539db2c).")
    print("PRAGMA foreign_keys=ON was only introduced into database.py on Fri Oct 9 01:47:11 2026 (commit d01d2b8).")
    print("Moreover, verify_fr7.py inserts an EC2 without estimated_monthly_cost (which was later gated by null-cost checks),")
    print("and verify_fr7.py queries EscalationState.filter_by(recommendation_id=str(rec.id)) which uses the hyphenated string.")

    db.close()
    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
