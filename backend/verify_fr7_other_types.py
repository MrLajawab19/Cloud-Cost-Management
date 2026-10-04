from sqlalchemy.orm import Session
from database import SessionLocal
from models.account import AWSAccount
from models.resource import Resource
from models.cost_record import Recommendation
from services.cleanup_advisor import generate_recommendations
import uuid

def main():
    db = SessionLocal()
    account = db.query(AWSAccount).first()
    
    # 1. Empty S3 Bucket
    res_s3_empty = Resource(
        id=uuid.uuid4(), account_id=account.id, resource_id="s3-empty-1", service_type="S3", region="us-east-1",
        storage_size_gb=0.0001, request_count=0
    )
    # 2. Large Unused S3
    res_s3_large = Resource(
        id=uuid.uuid4(), account_id=account.id, resource_id="s3-large-1", service_type="S3", region="us-east-1",
        storage_size_gb=600.0, request_count=0
    )
    # 3. Stopped RDS
    res_rds = Resource(
        id=uuid.uuid4(), account_id=account.id, resource_id="rds-stopped-1", service_type="RDS", region="us-east-1",
        status="stopped", storage_size_gb=100.0
    )
    # 4. Unused Lambda
    res_lam = Resource(
        id=uuid.uuid4(), account_id=account.id, resource_id="lam-unused-1", service_type="Lambda", region="us-east-1",
        request_count=0
    )
    
    db.add_all([res_s3_empty, res_s3_large, res_rds, res_lam])
    db.commit()
    
    # Generate recommendations
    generate_recommendations(db)
    
    # Verify they were generated via upsert
    recs = db.query(Recommendation).filter(Recommendation.resource_id.in_(
        ["s3-empty-1", "s3-large-1", "rds-stopped-1", "lam-unused-1"]
    )).all()
    
    found = {r.issue for r in recs}
    expected = {
        "Empty S3 Bucket", 
        "Large Unused S3 Bucket", 
        "Stopped RDS Instance (Storage Cost)", 
        "Unused Lambda Function"
    }
    
    if found == expected:
        print("SUCCESS: All 4 non-EC2 recommendation types successfully generated via upsert.")
    else:
        print(f"FAILURE: Expected {expected}, but found {found}")

if __name__ == "__main__":
    main()
