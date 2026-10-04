from sqlalchemy.orm import Session
from database import SessionLocal
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import RemediationLog, EscalationState
from models.anomaly import Anomaly
from services.cleanup_advisor import generate_recommendations
from services.savings_plan_optimiser import generate_sp_recommendations
from services.escalation_manager import process_escalations
import uuid
import datetime

def main():
    db = SessionLocal()
    account = db.query(CloudAccount).first()
    
    print("\n--- 1. Testing SP Recommendation Independence ---")
    # Seed a stable service with enough baseline for SP
    # But wait, predict_costs uses historical CostRecords. 
    # To bypass predict_costs and test the UI interaction, we will just manually insert an SP recommendation 
    # and run generate_recommendations() to see if it survives.
    
    sp_issue = "No Commitment"
    db.query(Recommendation).filter_by(issue=sp_issue).delete()
    db.commit()
    
    sp_rec = Recommendation(
        id=uuid.uuid4(),
        account_id=account.id,
        resource_id="EC2-SP-1YR",
        service_type="EC2",
        region="global",
        issue=sp_issue,
        description="Test SP",
        action="Purchase Savings Plan",
        severity="medium",
        potential_savings_usd=100.0,
        remediation_type="manual"
    )
    db.add(sp_rec)
    db.commit()
    
    # Run cleanup_advisor
    generate_recommendations(db)
    
    # Check if SP is still unresolved
    db.refresh(sp_rec)
    if not sp_rec.is_resolved:
        print("  SUCCESS: SP Recommendation ignored by cleanup_advisor stale loop.")
    else:
        print("  FAILURE: SP Recommendation was erroneously resolved by cleanup_advisor.")

    print("\n--- 2. Testing Escalation Execution ---")
    res_id = "i-exec-test-123"

    # Cleanup prior runs for this resource
    db.query(Recommendation).filter_by(resource_id=res_id).delete()
    db.query(EscalationState).filter(
        EscalationState.recommendation_id.in_(
            [str(r.id) for r in db.query(Recommendation).filter_by(resource_id=res_id).all()]
        )
    ).delete(synchronize_session=False)
    # Clear any leftover EC2 anomalies from prior test runs so they don't block this execution test
    db.query(Anomaly).filter_by(account_id=account.id, service_type="EC2").delete()
    db.commit()
    due_rec = Recommendation(
        id=uuid.uuid4(),
        account_id=account.id,
        resource_id=res_id,
        service_type="EC2",
        region="us-east-1",
        issue="Idle EC2 Instance",
        description="Will be executed",
        action="Stop the instance.",
        severity="low",
        remediation_type="stop"
    )
    db.add(due_rec)
    db.flush()
    
    esc_due = EscalationState(
        id=str(uuid.uuid4()),
        recommendation_id=str(due_rec.id),
        status="pending",
        due_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1) # Past due
    )
    db.add(esc_due)
    
    # Enable auto_remediate
    account.auto_remediate_enabled = True
    db.commit()
    
    # Process
    process_escalations(db)
    
    # Verify execution
    db.refresh(esc_due)
    db.refresh(due_rec)
    if esc_due.status == "resolved" and due_rec.is_resolved:
        log = db.query(RemediationLog).filter_by(resource_id=res_id).first()
        if log:
            print(f"  SUCCESS: Escalation executed and logged correctly. Status: {log.status}")
        else:
            print("  FAILURE: Escalation resolved but no RemediationLog written.")
    else:
        print("  FAILURE: Escalation did not execute.")

    print("\n--- 3. Testing Escalation Abort (Anomaly Exists) ---")
    # This test inserts an Anomaly using the EXACT same field names as anomaly_detector.py's
    # _upsert_anomalies() INSERT path (lines 278-293 of anomaly_detector.py), so the
    # test and the implementation cannot share a wrong assumption and both pass.
    res_id_2 = "i-abort-test-123"

    # Cleanup prior runs
    db.query(Recommendation).filter_by(resource_id=res_id_2).delete()
    db.query(Anomaly).filter_by(account_id=account.id, service_type="EC2").delete()
    db.commit()

    due_rec_2 = Recommendation(
        id=uuid.uuid4(),
        account_id=account.id,
        resource_id=res_id_2,
        service_type="EC2",
        region="us-east-1",
        issue="Idle EC2 Instance",
        description="Will be aborted",
        action="Stop the instance.",
        severity="low",
        remediation_type="stop"
    )
    db.add(due_rec_2)
    db.flush()

    esc_due_2 = EscalationState(
        id=str(uuid.uuid4()),
        recommendation_id=str(due_rec_2.id),
        status="pending",
        due_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1)  # Past due
    )
    db.add(esc_due_2)

    # Insert anomaly using the IDENTICAL constructor used by anomaly_detector._upsert_anomalies().
    # Fields: account_id, service_type, record_date, actual_cost, forecast_cost, residual,
    #         z_score, iqr_flagged, severity, direction, driver_service, is_resolved
    # (same as lines 278-293 of anomaly_detector.py)
    anom = Anomaly(
        account_id=account.id,
        service_type="EC2",
        record_date=datetime.datetime.utcnow().date(),
        actual_cost=500.0,
        forecast_cost=100.0,
        residual=400.0,
        z_score=4.0,
        iqr_flagged=True,
        severity="critical",
        direction="spike",
        driver_service="EC2",
        is_resolved=False,
    )
    db.add(anom)
    db.commit()

    # Independently verify the anomaly is readable via the same query
    # escalation_manager uses for the FR-7.6 abort check.
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=14)
    found = db.query(Anomaly).filter(
        Anomaly.account_id == account.id,
        Anomaly.record_date >= cutoff.date(),
        Anomaly.is_resolved == False,
        Anomaly.service_type == "EC2"
    ).first()
    if found:
        print(f"  PRE-CHECK: Anomaly readable by the exact FR-7.6 query (service={found.service_type}, "
              f"severity={found.severity}, direction={found.direction}, z_score={found.z_score})")
    else:
        print("  PRE-CHECK FAILURE: Anomaly not found by FR-7.6 query — abort test would be meaningless.")
        return

    # Now run process_escalations — it should hit the abort path
    process_escalations(db)

    # Verify abort
    db.refresh(esc_due_2)
    db.refresh(due_rec_2)
    if esc_due_2.status == "pending" and not due_rec_2.is_resolved:
        print("  SUCCESS: Escalation safely deferred due to active Anomaly (verified via real query path).")
    else:
        print(f"  FAILURE: Escalation fired incorrectly. Escalation status: {esc_due_2.status}, "
              f"rec.is_resolved: {due_rec_2.is_resolved}")

if __name__ == "__main__":
    main()

