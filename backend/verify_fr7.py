from sqlalchemy.orm import Session
from database import SessionLocal
from models.account import AWSAccount
from models.resource import Resource
from models.cost_record import Recommendation
from models.remediation import EscalationState
from services.cleanup_advisor import generate_recommendations
import uuid
import datetime

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    
    print("\n--- 1. Testing Idle EC2 Generation and Escalation ---")
    res_id = "i-testidle123"
    r = db.query(Resource).filter_by(resource_id=res_id).first()
    if not r:
        r = Resource(
            id=uuid.uuid4(),
            account_id=account.id,
            resource_id=res_id,
            resource_name="Test Idle EC2",
            service_type="EC2",
            region="us-east-1",
            status="running",
            cpu_utilization_avg=0.5, # CPU < 1.0 (Idle)
            runtime_hours=200
        )
        db.add(r)
        db.commit()
    else:
        r.cpu_utilization_avg = 0.5
        db.commit()

    # Clear existing recommendations for this resource to get a clean start
    db.query(Recommendation).filter_by(resource_id=res_id).delete()
    db.query(EscalationState).delete()
    db.commit()

    # Run collection
    generate_recommendations(db)

    # Verify Stop recommendation and EscalationState
    rec = db.query(Recommendation).filter_by(resource_id=res_id, remediation_type="stop").first()
    if rec and not rec.is_resolved:
        print(f"  SUCCESS: Generated Stop recommendation (Idle EC2) for {res_id}")
    else:
        print("  FAILURE: Stop recommendation not found.")
        return

    esc = db.query(EscalationState).filter_by(recommendation_id=str(rec.id)).first()
    if esc and esc.status == "pending":
        print("  SUCCESS: EscalationState created and is pending.")
    else:
        print("  FAILURE: EscalationState missing or not pending.")
        return

    print("\n--- 2. Testing Escalation NOT recreated on Update ---")
    # Change description manually to force an update difference
    rec.description = "Old description"
    db.commit()
    
    # Store old due_at and ID
    old_due_at = esc.due_at
    old_esc_id = esc.id

    # Run collection again
    generate_recommendations(db)
    
    esc_after = db.query(EscalationState).filter_by(recommendation_id=str(rec.id)).all()
    if len(esc_after) == 1 and esc_after[0].id == old_esc_id and esc_after[0].due_at == old_due_at:
        print("  SUCCESS: EscalationState remained identical, NOT recreated on upsert.")
    else:
        print("  FAILURE: EscalationState was recreated or duplicated.")


    print("\n--- 3. Testing Stale Cleanup (CPU Recovers) ---")
    # Resource CPU increases to 15% (no longer idle nor underutilized)
    r.cpu_utilization_avg = 15.0
    db.commit()

    # Run collection
    generate_recommendations(db)

    # Check that recommendation is marked resolved
    db.refresh(rec)
    if rec.is_resolved:
        print("  SUCCESS: Recommendation marked resolved due to stale cleanup.")
    else:
        print("  FAILURE: Recommendation is still active.")

    # Check that escalation is cancelled
    esc_final = db.query(EscalationState).filter_by(id=old_esc_id).first()
    if esc_final and esc_final.status == "cancelled":
        print("  SUCCESS: EscalationState was cancelled correctly.")
    else:
        print("  FAILURE: Escalation state is not cancelled.")

if __name__ == "__main__":
    main()
