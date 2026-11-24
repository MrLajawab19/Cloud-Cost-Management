"""
verify_azure_guided_remediation.py — Verification suite for Client Change #5:
Consistent guided remediation for Azure VMs.
Covers:
- Demo Azure recommendations with remediation_type (Idle AzureVM 'stop', Underutilized AzureVM 'resize', others 'manual').
- /remediation/status returns 2 guided items for the Azure VMs.
- Anomaly hold (held=True, held_reason naming AzureVM) while VM anomaly is unresolved.
- Fast-forward while anomaly is active remains HELD.
- Resolving the anomaly -> fast-forward transitions escalation to stage 'action_due'.
- Guided workflow state transitions: accept -> 'accepted'; complete -> 'completed', rec resolved, audit log with actor.
- Guided decline path: decline -> 'declined', rec dismissed, escalation closed, audit log with actor.
- Invalid transition returns HTTP 409 Conflict.
- Cross-user security: other user's account returns 403/404.
- Demo AWS guided items unchanged.
- Real Azure account with VM (cpu 0.3, runtime 300, cost 40) gets guided items; VM with cpu None or cost None gets none.
- Zero Cloud SDK calls (boto3 and azure modules patched to raise if called).
"""
import _bootstrap

import sys
import os
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.cost_record import Recommendation, format_recommendation_id_fk
from models.resource import Resource
from models.anomaly import Anomaly
from models.remediation import EscalationState, RemediationLog
from services.security import get_password_hash, create_access_token
from services.demo_data import ensure_demo_accounts, reset_demo_account
from services.cleanup_advisor import generate_recommendations
from services.escalation_manager import process_auto_resizes, process_escalations


def run_suite():
    print("=" * 70)
    print("RUNNING VERIFICATION: Consistent Guided Remediation for Azure VMs")
    print("=" * 70)

    # Safety: ensure no real cloud SDK is called
    sdk_mock = MagicMock(side_effect=RuntimeError("Cloud SDK strictly blocked!"))
    boto_patch = patch.dict("sys.modules", {"boto3": sdk_mock, "azure": sdk_mock})
    boto_patch.start()

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

    print(f"Engine Path: sqlite:///:memory: (FK ON)")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()

    # Create primary user and secondary user (for 403 test)
    user1 = User(id=str(uuid.uuid4()), email="user1@azure.demo", password_hash=get_password_hash("Pass123!"))
    user2 = User(id=str(uuid.uuid4()), email="user2@azure.demo", password_hash=get_password_hash("Pass123!"))
    db.add_all([user1, user2])
    db.commit()

    token1 = create_access_token({"sub": str(user1.id)})
    headers1 = {"Authorization": f"Bearer {token1}"}
    token2 = create_access_token({"sub": str(user2.id)})
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Setup Demo accounts
    ensure_demo_accounts(db, str(user1.id))
    acc_azure = db.query(CloudAccount).filter(CloudAccount.user_id == str(user1.id), CloudAccount.provider == "azure").first()
    acc_aws = db.query(CloudAccount).filter(CloudAccount.user_id == str(user1.id), CloudAccount.provider == "aws").first()
    assert acc_azure and acc_aws
    reset_demo_account(db, acc_azure)
    reset_demo_account(db, acc_aws)

    # ──────────────────────────────────────────────────────────────────
    # Check 1: Recommendations remediation_type on Demo Azure
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 1] Recommendations remediation_type on Demo Azure")
    recs_az = db.query(Recommendation).filter(
        Recommendation.account_id == acc_azure.id,
        Recommendation.is_resolved == False
    ).all()
    rec_type_map = {r.issue: r.remediation_type for r in recs_az}
    for issue, rtype in sorted(rec_type_map.items()):
        print(f"  - {issue}: {rtype}")

    assert rec_type_map.get("Idle AzureVM") == "stop", f"Expected Idle AzureVM to have remediation_type 'stop', got {rec_type_map.get('Idle AzureVM')}"
    assert rec_type_map.get("Underutilized AzureVM") == "resize", f"Expected Underutilized AzureVM to have remediation_type 'resize', got {rec_type_map.get('Underutilized AzureVM')}"
    assert rec_type_map.get("Empty Azure Blob Storage") == "manual"
    assert rec_type_map.get("Large Unused Blob Storage") == "manual"
    assert rec_type_map.get("Idle Azure SQL Database") == "manual"
    assert rec_type_map.get("Paused Azure SQL Database (storage cost)") == "manual"
    assert rec_type_map.get("Unused Azure Function App") == "manual"
    print("  PASS: Idle AzureVM is 'stop', Underutilized AzureVM is 'resize', other services are 'manual'.")

    # ──────────────────────────────────────────────────────────────────
    # Check 2: /remediation/status shows 2 guided items & stop is HELD
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 2] /remediation/status on Demo Azure (2 items, stop HELD)")
    resp_st = client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1)
    assert resp_st.status_code == 200
    st_data = resp_st.json()
    escs = st_data.get("escalations", [])
    print(f"  Demo Azure Guided Items count: {len(escs)}")
    for e in escs:
        print(f"    - [{e['issue']}] stage={e['stage']} held={e['held']} reason={e.get('held_reason')} hrs_rem={e.get('hours_remaining')}")

    assert len(escs) == 2, f"Expected exactly 2 guided items for Azure VMs, got {len(escs)}"
    stop_item = next((e for e in escs if e["issue"] == "Idle AzureVM"), None)
    resize_item = next((e for e in escs if e["issue"] == "Underutilized AzureVM"), None)
    assert stop_item is not None, "Missing Idle AzureVM in guided items"
    assert resize_item is not None, "Missing Underutilized AzureVM in guided items"

    assert resize_item["stage"] == "recommended"
    assert resize_item["held"] is False
    assert "accept" in resize_item["allowed_actions"]

    assert stop_item["stage"] in ["pending", "action_due"]
    assert stop_item["hours_remaining"] is not None
    assert stop_item["held"] is True, f"Expected held=True for stop item initially, got {stop_item['held']}"
    assert "AzureVM" in (stop_item.get("held_reason") or ""), f"Expected held_reason naming AzureVM, got {stop_item.get('held_reason')}"
    print("  PASS: 2 guided items returned for Azure VMs (stop HELD, resize recommended).")

    # ──────────────────────────────────────────────────────────────────
    # Check 3: Fast-forward while VM anomaly unresolved -> remains HELD
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 3] Fast-forward with unresolved AzureVM anomaly -> remains HELD")
    ff_resp = client.post(f"/remediation/demo/fast-forward?account_id={acc_azure.id}", headers=headers1)
    assert ff_resp.status_code == 200
    print(f"  Fast-forward response: {ff_resp.json()}")

    resp_st2 = client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1)
    escs2 = resp_st2.json().get("escalations", [])
    stop_item2 = next(e for e in escs2 if e["issue"] == "Idle AzureVM")
    assert stop_item2["held"] is True, f"Expected held=True for stop item, got {stop_item2['held']}"
    assert "AzureVM" in (stop_item2.get("held_reason") or ""), f"Expected held_reason naming AzureVM, got {stop_item2.get('held_reason')}"
    assert stop_item2["allowed_actions"] == [], "HELD item must have no allowed actions"
    print(f"  PASS: Fast-forwarded stop is HELD: held_reason='{stop_item2['held_reason']}'.")

    # ──────────────────────────────────────────────────────────────────
    # Check 4: Resolve AzureVM anomaly -> Fast-forward -> stage action_due
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 4] Resolve AzureVM anomaly -> stage becomes action_due")
    az_anoms = db.query(Anomaly).filter(Anomaly.account_id == acc_azure.id, Anomaly.service_type == "AzureVM").all()
    for a in az_anoms:
        client.post(f"/anomalies/{a.id}/resolve", headers=headers1)
    db.commit()

    ff_resp2 = client.post(f"/remediation/demo/fast-forward?account_id={acc_azure.id}", headers=headers1)
    assert ff_resp2.status_code == 200

    resp_st3 = client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1)
    stop_item3 = next(e for e in resp_st3.json().get("escalations", []) if e["issue"] == "Idle AzureVM")
    assert stop_item3["held"] is False, "Hold must be lifted once anomaly is resolved"
    assert stop_item3["stage"] == "action_due", f"Expected stage 'action_due', got {stop_item3['stage']}"
    assert "accept" in stop_item3["allowed_actions"]
    print(f"  PASS: Hold lifted. Stage transitioned to '{stop_item3['stage']}' with allowed actions: {stop_item3['allowed_actions']}.")

    # ──────────────────────────────────────────────────────────────────
    # Check 5: Accept -> Accepted, Complete -> Completed + Audit Log
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 5] Accept -> Complete workflow on Idle AzureVM")
    rec_stop_id = stop_item3["recommendation_id"]
    acc_res = client.post(f"/remediation/guided/{rec_stop_id}/accept", headers=headers1)
    assert acc_res.status_code == 200
    assert acc_res.json()["guided_state"] == "accepted"

    # Check status reflects accepted state
    resp_st4 = client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1)
    stop_item4 = next(e for e in resp_st4.json().get("escalations", []) if e["recommendation_id"] == rec_stop_id)
    assert stop_item4["stage"] == "accepted"
    assert stop_item4["allowed_actions"] == ["complete"]

    # Complete the recommendation
    comp_res = client.post(f"/remediation/guided/{rec_stop_id}/complete", headers=headers1)
    assert comp_res.status_code == 200
    assert comp_res.json()["guided_state"] == "completed"

    # Verify recommendation is resolved in DB
    rec_db = db.query(Recommendation).filter(Recommendation.id == uuid.UUID(rec_stop_id)).first()
    assert rec_db.is_resolved is True

    # Verify audit logs in /remediation/status contain user email
    logs = client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1).json().get("logs", [])
    assert len(logs) >= 2
    comp_log = next(l for l in logs if l["status"] == "guided_completed")
    assert user1.email in comp_log["before_state"] or user1.email in comp_log["trigger_reason"]
    print(f"  PASS: Complete workflow confirmed: rec resolved, escalation completed, audit log actor='{user1.email}'.")

    # ──────────────────────────────────────────────────────────────────
    # Check 6: Decline workflow on Underutilized AzureVM
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 6] Decline workflow on Underutilized AzureVM")
    rec_resize_id = resize_item["recommendation_id"]
    dec_res = client.post(f"/remediation/guided/{rec_resize_id}/decline", headers=headers1)
    assert dec_res.status_code == 200
    assert dec_res.json()["guided_state"] == "declined"

    rec_resize_db = db.query(Recommendation).filter(Recommendation.id == uuid.UUID(rec_resize_id)).first()
    assert rec_resize_db.ignore_remediation is True

    dec_log = next(l for l in client.get(f"/remediation/status?account_id={acc_azure.id}", headers=headers1).json().get("logs", []) if l["status"] == "guided_declined")
    assert user1.email in dec_log["before_state"] or user1.email in dec_log["trigger_reason"]
    print("  PASS: Decline workflow confirmed: rec dismissed, audit log recorded.")

    # ──────────────────────────────────────────────────────────────────
    # Check 7: Invalid state transitions -> HTTP 409 Conflict
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 7] Invalid state transitions return HTTP 409")
    # Trying to complete an already completed item
    inv_comp = client.post(f"/remediation/guided/{rec_stop_id}/complete", headers=headers1)
    assert inv_comp.status_code == 409, f"Expected 409 for invalid complete, got {inv_comp.status_code}"
    # Trying to accept an already declined item
    inv_acc = client.post(f"/remediation/guided/{rec_resize_id}/accept", headers=headers1)
    assert inv_acc.status_code == 409, f"Expected 409 for invalid accept, got {inv_acc.status_code}"
    print("  PASS: Invalid state transitions strictly rejected with 409.")

    # ──────────────────────────────────────────────────────────────────
    # Check 8: Security - Cross-user access returns 403/404
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 8] Security - Cross-user access returns 403/404")
    sec_ff = client.post(f"/remediation/demo/fast-forward?account_id={acc_azure.id}", headers=headers2)
    assert sec_ff.status_code == 403, f"Expected 403 for unauthorized demo fast-forward, got {sec_ff.status_code}"

    sec_acc = client.post(f"/remediation/guided/{rec_stop_id}/accept", headers=headers2)
    assert sec_acc.status_code in [403, 404], f"Expected 403 or 404 for unauthorized accept, got {sec_acc.status_code}"
    print("  PASS: Cross-user access correctly rejected.")

    # ──────────────────────────────────────────────────────────────────
    # Check 9: Demo AWS output unchanged
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 9] Demo AWS output remains unchanged")
    aws_st = client.get(f"/remediation/status?account_id={acc_aws.id}", headers=headers1).json()
    aws_escs = aws_st.get("escalations", [])
    print(f"  Demo AWS Guided Items ({len(aws_escs)}):")
    for e in aws_escs:
        print(f"    - [{e['issue']}] stage={e['stage']} held={e['held']}")
    assert len(aws_escs) == 2, f"Expected 2 guided items on Demo AWS, got {len(aws_escs)}"
    assert any(e["issue"] == "Idle EC2 Instance" for e in aws_escs)
    assert any(e["issue"] == "Underutilized EC2 Instance" for e in aws_escs)
    print("  PASS: Demo AWS guided items unchanged.")

    # ──────────────────────────────────────────────────────────────────
    # Check 10: Real Azure Account VM behavior
    # ──────────────────────────────────────────────────────────────────
    print("\n[Check 10] Real Azure Account VM behavior")
    real_az_acc = CloudAccount(
        id=str(uuid.uuid4()),
        user_id=str(user1.id),
        name="Real Azure Test",
        provider="azure",
        region="eastus",
        tenant_id="real-tenant",
        client_id="real-client",
        encrypted_secret_key="secret",
        auto_remediate_enabled=True,
        grace_period_hours=24,
    )
    db.add(real_az_acc)
    db.commit()

    # VM 1: idle -> gets guided stop item
    vm_idle = Resource(
        id=uuid.uuid4(),
        account_id=real_az_acc.id,
        resource_id="real-az-idle-vm",
        resource_name="real-az-idle-vm",
        service_type="AzureVM",
        region="eastus",
        status="running",
        resource_type="Standard_B2s",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
    )
    # VM 2: cpu None -> gets none
    vm_no_cpu = Resource(
        id=uuid.uuid4(),
        account_id=real_az_acc.id,
        resource_id="real-az-no-cpu",
        resource_name="real-az-no-cpu",
        service_type="AzureVM",
        region="eastus",
        status="running",
        resource_type="Standard_B2s",
        cpu_utilization_avg=None,
        runtime_hours=300.0,
        estimated_monthly_cost=40.0,
    )
    # VM 3: cost None -> gets none
    vm_no_cost = Resource(
        id=uuid.uuid4(),
        account_id=real_az_acc.id,
        resource_id="real-az-no-cost",
        resource_name="real-az-no-cost",
        service_type="AzureVM",
        region="eastus",
        status="running",
        resource_type="Standard_B2s",
        cpu_utilization_avg=0.3,
        runtime_hours=300.0,
        estimated_monthly_cost=None,
    )
    db.add_all([vm_idle, vm_no_cpu, vm_no_cost])
    db.commit()

    generate_recommendations(db)
    process_auto_resizes(db)

    real_st = client.get(f"/remediation/status?account_id={real_az_acc.id}", headers=headers1).json()
    real_escs = real_st.get("escalations", [])
    assert len(real_escs) == 1, f"Expected exactly 1 guided item for real Azure account, got {len(real_escs)}"
    assert real_escs[0]["resource_id"] == "real-az-idle-vm"
    assert real_escs[0]["issue"] == "Idle AzureVM"
    assert real_escs[0]["stage"] == "pending"
    assert real_escs[0]["hours_remaining"] <= 24.0
    print("  PASS: Real Azure account gets guided stop item for valid VM, none for null cpu/cost VMs.")

    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED FOR AZURE GUIDED REMEDIATION!")
    print("=" * 70)


if __name__ == "__main__":
    run_suite()
