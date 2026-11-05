"""
backend/tests/verify_s3_missing_metrics.py

Verifies that S3 collection handles missing CloudWatch metrics gracefully:
1. Fake S3 and CloudWatch clients returning missing metrics for one bucket and valid 0 metrics for another.
2. Verified that location lookup failure does not abort bucket collection.
3. Verified that unknown metrics result in None storage_size_gb, request_count, and estimated_monthly_cost.
4. Verified that cleanup_advisor does not generate false recommendations for unknown buckets, but correctly creates Empty S3 Bucket for a real 0.0 GB / 0 requests bucket.
"""
import _bootstrap

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
from services.aws_collector import collect_s3_buckets
from services.cleanup_advisor import generate_recommendations


class FakeS3Client:
    def list_buckets(self):
        return {
            "Buckets": [
                {"Name": "bucket-unknown", "CreationDate": datetime.now(timezone.utc)},
                {"Name": "bucket-known", "CreationDate": datetime.now(timezone.utc)},
            ]
        }

    def get_bucket_location(self, Bucket):
        if Bucket == "bucket-unknown":
            raise Exception("AccessDenied: Cannot get bucket location")
        return {"LocationConstraint": "us-west-2"}


class FakeCloudWatchClient:
    def get_metric_statistics(self, Namespace, MetricName, Dimensions, StartTime, EndTime, Period, Statistics):
        bname = None
        for d in Dimensions:
            if d.get("Name") == "BucketName":
                bname = d.get("Value")
        if bname == "bucket-unknown":
            # Missing CloudWatch data -> Datapoints empty
            return {"Datapoints": []}
        elif bname == "bucket-known":
            # Real 0.0 metrics
            return {"Datapoints": [{"Average": 0.0}]}
        return {"Datapoints": []}


class FakeBotoSession:
    region_name = "us-east-1"

    def client(self, service_name):
        if service_name == "s3":
            return FakeS3Client()
        if service_name == "cloudwatch":
            return FakeCloudWatchClient()
        raise ValueError(f"Unexpected service: {service_name}")


def main():
    print("=== Running verify_s3_missing_metrics ===")

    # 1. Test collector with fake session
    session = FakeBotoSession()
    resources = collect_s3_buckets(session)

    print(f"collect_s3_buckets returned {len(resources)} resources.")
    assert len(resources) == 2, f"Expected 2 resources, got {len(resources)}"

    res_map = {r["resource_id"]: r for r in resources}
    assert "bucket-unknown" in res_map, "bucket-unknown missing from returned resources"
    assert "bucket-known" in res_map, "bucket-known missing from returned resources"

    unk = res_map["bucket-unknown"]
    print(f"bucket-unknown: region={unk['region']}, storage_size_gb={unk['storage_size_gb']}, "
          f"request_count={unk['request_count']}, cost={unk['estimated_monthly_cost']}, is_idle={unk['is_idle']}")
    assert unk["region"] == "us-east-1", f"Expected default region us-east-1, got {unk['region']}"
    assert unk["storage_size_gb"] is None, f"Expected storage_size_gb is None, got {unk['storage_size_gb']}"
    assert unk["request_count"] is None, f"Expected request_count is None, got {unk['request_count']}"
    assert unk["estimated_monthly_cost"] is None, f"Expected estimated_monthly_cost is None, got {unk['estimated_monthly_cost']}"
    assert unk["is_idle"] is False, f"Expected is_idle is False for unknown metrics, got {unk['is_idle']}"
    assert unk["status"] == "available", f"Expected status 'available', got {unk['status']}"

    kno = res_map["bucket-known"]
    print(f"bucket-known: region={kno['region']}, storage_size_gb={kno['storage_size_gb']}, "
          f"request_count={kno['request_count']}, cost={kno['estimated_monthly_cost']}, is_idle={kno['is_idle']}")
    assert kno["region"] == "us-west-2", f"Expected region us-west-2, got {kno['region']}"
    assert kno["storage_size_gb"] == 0.0, f"Expected storage_size_gb == 0.0, got {kno['storage_size_gb']}"
    assert kno["request_count"] == 0.0, f"Expected request_count == 0.0, got {kno['request_count']}"
    assert kno["estimated_monthly_cost"] == 0.0, f"Expected estimated_monthly_cost == 0.0, got {kno['estimated_monthly_cost']}"
    assert kno["is_idle"] is True, f"Expected is_idle is True, got {kno['is_idle']}"

    # 2. Test in-memory DB with cleanup_advisor
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

    print(f"Engine Path: sqlite:///:memory: (PRAGMA foreign_keys=ON)")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    user_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())

    user = User(id=user_id, email="s3test@example.com", password_hash="dummy")
    db.add(user)
    db.commit()

    acc = CloudAccount(id=account_id, user_id=user.id, name="S3TestAcc", provider="aws", region="us-east-1")
    db.add(acc)
    db.commit()

    db.add(Resource(
        id=uuid.uuid4(),
        account_id=acc.id,
        resource_id="bucket-unknown",
        resource_name="bucket-unknown",
        service_type="S3",
        region="us-east-1",
        status="available",
        storage_size_gb=None,
        request_count=None,
        estimated_monthly_cost=None,
        is_idle=False,
    ))
    db.add(Resource(
        id=uuid.uuid4(),
        account_id=acc.id,
        resource_id="bucket-known",
        resource_name="bucket-known",
        service_type="S3",
        region="us-west-2",
        status="available",
        storage_size_gb=0.0,
        request_count=0.0,
        estimated_monthly_cost=0.0,
        is_idle=True,
    ))
    db.commit()

    rec_count = generate_recommendations(db)
    print(f"generate_recommendations created {rec_count} recommendations.")

    recs_unknown = db.query(Recommendation).filter(Recommendation.resource_id == "bucket-unknown").all()
    recs_known = db.query(Recommendation).filter(Recommendation.resource_id == "bucket-known").all()

    print(f"Unknown bucket recommendations: {len(recs_unknown)}")
    print(f"Known bucket recommendations: {len(recs_known)}")

    assert len(recs_unknown) == 0, f"Expected 0 recommendations for bucket-unknown, got {len(recs_unknown)}"
    assert len(recs_known) == 1, f"Expected 1 recommendation for bucket-known, got {len(recs_known)}"
    assert recs_known[0].issue == "Empty S3 Bucket", f"Expected issue 'Empty S3 Bucket', got {recs_known[0].issue}"

    db.close()
    print("ALL S3 MISSING METRICS VERIFICATION CHECKS PASSED.")


if __name__ == "__main__":
    main()
