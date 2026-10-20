"""
backend/verify_ec2_cpu_gate.py
Verify Item L:
1. In-memory SQLite with foreign_keys=ON.
2. EC2 running with runtime 300:
   - cpu is None -> 0 recs
   - cpu 0.0 -> Idle EC2 Instance (remediation_type="stop")
   - cpu 0.19 -> Idle EC2 Instance (remediation_type="stop")
   - cpu 3.0 -> Underutilized EC2 Instance (remediation_type="resize")
3. CloudWatch helper returns None when client raises or has no datapoints.
"""

import sys
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

# Setup in-memory SQLite with FK ON
engine = create_engine("sqlite:///:memory:")

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Base
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import EscalationState, RemediationLog
from services.cleanup_advisor import generate_recommendations
from services.aws_collector import _get_cloudwatch_metric

Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)

def test_ec2_cpu_rules():
    db = Session()
    # Check FK pragma
    fk_status = db.execute(text("PRAGMA foreign_keys")).fetchone()[0]
    assert fk_status == 1, f"Expected FK=ON, got {fk_status}"
    print(f"PRAGMA foreign_keys = {fk_status} (ON)")

    # Create user and account
    user = User(id=str(uuid.uuid4()), email="test_l@example.com", password_hash="pw")
    db.add(user)
    db.commit()

    account = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Test-EC2-Gate",
        provider="aws",
        region="us-east-1",
        access_key_id="TESTKEY",
        encrypted_secret_key="TESTENC"
    )
    db.add(account)
    db.commit()

    def set_resource(cpu_val):
        db.query(EscalationState).delete()
        db.query(RemediationLog).delete()
        db.query(Recommendation).delete()
        db.query(Resource).delete()
        db.commit()

        res = Resource(
            id=uuid.uuid4(),
            account_id=account.id,
            resource_id="i-test-instance-cpu-gate",
            resource_name="test-instance",
            service_type="EC2",
            region="us-east-1",
            status="running",
            resource_type="t3.medium",
            cpu_utilization_avg=cpu_val,
            runtime_hours=300.0,
            estimated_monthly_cost=30.0,
            is_idle=(cpu_val is not None and cpu_val < 5.0),
        )
        db.add(res)
        db.commit()

    # Case 1: cpu is None, runtime 300 -> 0 recommendations
    set_resource(None)
    generate_recommendations(db)
    recs = db.query(Recommendation).all()
    print(f"Case 1 (cpu=None, runtime=300): recs count={len(recs)}")
    assert len(recs) == 0, f"Expected 0 recs for cpu=None, got {len(recs)}"

    # Case 2: cpu is 0.0 -> Idle EC2 Instance (remediation_type='stop')
    set_resource(0.0)
    generate_recommendations(db)
    recs = db.query(Recommendation).all()
    print(f"Case 2 (cpu=0.0): recs count={len(recs)}, issue='{recs[0].issue if recs else None}', type={recs[0].remediation_type if recs else None}")
    assert len(recs) == 1
    assert recs[0].issue == "Idle EC2 Instance"
    assert recs[0].remediation_type == "stop"

    # Case 3: cpu is 0.19 -> Idle EC2 Instance
    set_resource(0.19)
    generate_recommendations(db)
    recs = db.query(Recommendation).all()
    print(f"Case 3 (cpu=0.19): recs count={len(recs)}, issue='{recs[0].issue if recs else None}', type={recs[0].remediation_type if recs else None}")
    assert len(recs) == 1
    assert recs[0].issue == "Idle EC2 Instance"
    assert recs[0].remediation_type == "stop"

    # Case 4: cpu is 3.0 -> Underutilized EC2 Instance (remediation_type='resize')
    set_resource(3.0)
    generate_recommendations(db)
    recs = db.query(Recommendation).all()
    print(f"Case 4 (cpu=3.0): recs count={len(recs)}, issue='{recs[0].issue if recs else None}', type={recs[0].remediation_type if recs else None}")
    assert len(recs) == 1
    assert recs[0].issue == "Underutilized EC2 Instance"
    assert recs[0].remediation_type == "resize"

    db.close()
    print("ALL EC2 cleanup_advisor cases PASSED.")

def test_cloudwatch_helper():
    class RaisingCWClient:
        def get_metric_statistics(self, **kwargs):
            raise Exception("AccessDenied: User is not authorized to perform cloudwatch:GetMetricStatistics")

    class EmptyCWClient:
        def get_metric_statistics(self, **kwargs):
            return {"Datapoints": []}

    class ValidCWClient:
        def get_metric_statistics(self, **kwargs):
            return {"Datapoints": [{"Average": 4.25}]}

    res_raising = _get_cloudwatch_metric(RaisingCWClient(), "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": "i-123"}])
    print(f"Raising CW Client: result={res_raising}")
    assert res_raising is None, f"Expected None on exception/AccessDenied, got {res_raising}"

    res_empty = _get_cloudwatch_metric(EmptyCWClient(), "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": "i-123"}])
    print(f"Empty CW Client: result={res_empty}")
    assert res_empty is None, f"Expected None on empty datapoints, got {res_empty}"

    res_valid = _get_cloudwatch_metric(ValidCWClient(), "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": "i-123"}])
    print(f"Valid CW Client: result={res_valid}")
    assert res_valid == 4.25, f"Expected 4.25, got {res_valid}"

    print("ALL CloudWatch helper cases PASSED.")

if __name__ == "__main__":
    test_ec2_cpu_rules()
    test_cloudwatch_helper()
    print("VERIFY_EC2_CPU_GATE COMPLETE: ALL CHECKS PASSED.")
