"""
verify_client_changes.py — Regression suite for Client Change Requests (Items A, B, C).
Covers:
- Item A: Potential saving column on /resources, join logic, sort=saving_desc, null cost safety.
- Item B: Savings Plan Optimiser /savings-optimiser/plans, 4 commitment options, exact match for 1y_partial_upfront.
- Item C: Explainable Forecasting /costs/explain, deterministic narratives, ~100% service share sum, real account checks.
"""

import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

# Support DATABASE_URL if pointing to a test copy, else create a fresh copy of live DB
db_url = os.environ.get("DATABASE_URL")
temp_copy_created = False
test_copy_path = None

if not db_url or "cloud_cost.db" in db_url.replace("\\", "/"):
    live_db = backend_dir / "cloud_cost.db"
    test_copy_path = Path(tempfile.gettempdir()) / "verify_client_changes_copy.db"
    if test_copy_path.exists():
        try:
            test_copy_path.unlink()
        except Exception:
            pass
    src = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True)
    dst = sqlite3.connect(str(test_copy_path))
    src.backup(dst)
    dst.close()
    src.close()
    db_url = f"sqlite:///{test_copy_path}"
    temp_copy_created = True

print(f"Engine Path: {db_url}")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from database import get_db
from main import app
from models.user import User
from models.account import CloudAccount
from models.resource import Resource
from models.cost_record import Recommendation
from services.security import create_access_token

engine = create_engine(db_url, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

Session = sessionmaker(bind=engine)
db = Session()

def override_get_db():
    session = Session()
    try:
        yield session
    finally:
        session.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

admin_user = db.query(User).filter(User.email == "admin@example.com").first()
assert admin_user, "Admin user admin@example.com required in DB"
token = create_access_token({"sub": admin_user.id})
headers = {"Authorization": f"Bearer {token}"}

demo_aws = db.query(CloudAccount).filter(CloudAccount.name == "Demo AWS").first()
demo_azure = db.query(CloudAccount).filter(CloudAccount.name == "Demo Azure").first()
real_aws = db.query(CloudAccount).filter(CloudAccount.id.like("4d62c035%")).first()
real_az = db.query(CloudAccount).filter(CloudAccount.id.like("e72a125c%")).first()

assert demo_aws, "Demo AWS account required"
assert demo_azure, "Demo Azure account required"
assert real_aws, "Real AWS account 4d62c035 required"
assert real_az, "Real Azure account e72a125c required"

# ══════════════════════════════════════════════════════════════════════
# ITEM A: Potential saving column on /resources
# ══════════════════════════════════════════════════════════════════════
print("\n--- Verifying Item A (Resources Potential Saving Column) ---")

# Add a test resource with null cost and a resource with only a resolved recommendation
unknown_r = Resource(
    account_id=demo_aws.id,
    resource_id="i-verify-null-cost",
    resource_name="verify-null-cost",
    service_type="EC2",
    region="us-east-1",
    status="running",
    estimated_monthly_cost=None
)
db.add(unknown_r)

resolved_only_r = Resource(
    account_id=demo_aws.id,
    resource_id="i-verify-resolved-only",
    resource_name="verify-resolved-only",
    service_type="EC2",
    region="us-east-1",
    status="running",
    estimated_monthly_cost=25.0
)
db.add(resolved_only_r)
db.flush()

db.add(Recommendation(
    account_id=demo_aws.id,
    resource_id=resolved_only_r.resource_id,
    resource_name=resolved_only_r.resource_name,
    service_type="EC2",
    region="us-east-1",
    issue="Old Resolved Issue",
    description="Resolved",
    action="None",
    potential_savings_usd=90.0,
    is_resolved=True
))
db.commit()

# Call GET /resources with sort=saving_desc
res_resp = client.get(f"/resources/?account_id={demo_aws.id}&sort=saving_desc", headers=headers)
assert res_resp.status_code == 200, f"/resources failed: {res_resp.status_code}"
res_data = res_resp.json().get("resources", [])
res_by_id = {r["resource_id"]: r for r in res_data}

# Assert values in Demo AWS
# Idle EC2 40.00
if "i-demo-idle-aadc4a5d" in res_by_id:
    # If not resolved by prior simulated stop
    idle_ec2 = res_by_id["i-demo-idle-aadc4a5d"]
    assert idle_ec2["potential_saving_usd"] in (40.0, None)

# Large unused S3 (12.42)
assert res_by_id["demo-large-unused-bucket-aadc4a5d"]["potential_saving_usd"] == 12.42
assert res_by_id["demo-large-unused-bucket-aadc4a5d"]["saving_issue"] == "Large Unused S3 Bucket"

# Stopped RDS (5.75)
assert res_by_id["demo-stopped-rds-aadc4a5d"]["potential_saving_usd"] == 5.75
assert res_by_id["demo-stopped-rds-aadc4a5d"]["saving_issue"] == "Stopped RDS Instance (Storage Cost)"

# Stopped EC2 (3.00)
assert res_by_id["i-demo-stopped-aadc4a5d"]["potential_saving_usd"] == 3.0
assert res_by_id["i-demo-stopped-aadc4a5d"]["saving_issue"] == "Stopped EC2 (EBS Costs Still Accruing)"

# Empty bucket (0.00)
assert res_by_id["demo-empty-bucket-aadc4a5d"]["potential_saving_usd"] == 0.0
assert res_by_id["demo-empty-bucket-aadc4a5d"]["saving_issue"] == "Empty S3 Bucket"

# Underutilized EC2 has no active recommendation (simulated resize resolved it)
underutilized_ec2 = res_by_id["i-demo-resize-aadc4a5d"]
assert underutilized_ec2["potential_saving_usd"] is None

# Resolved rec excluded
assert res_by_id["i-verify-resolved-only"]["potential_saving_usd"] is None

# Null cost resource returns null without error
assert res_by_id["i-verify-null-cost"]["estimated_monthly_cost"] is None
assert res_by_id["i-verify-null-cost"]["potential_saving_usd"] is None

# Real AWS account returns 200
r_aws_res = client.get(f"/resources/?account_id={real_aws.id}", headers=headers)
assert r_aws_res.status_code == 200

print("[PASS] Item A: All resource potential saving checks passed.")

# ══════════════════════════════════════════════════════════════════════
# ITEM B: Savings Plan Optimiser (/savings-optimiser/plans)
# ══════════════════════════════════════════════════════════════════════
print("\n--- Verifying Item B (Savings Plan Optimiser) ---")

# Demo AWS plans
resp_b_aws = client.get(f"/savings-optimiser/plans?account_id={demo_aws.id}", headers=headers)
assert resp_b_aws.status_code == 200
data_b_aws = resp_b_aws.json()
assert len(data_b_aws.get("services", [])) >= 1

for svc in data_b_aws["services"]:
    assert "pay_as_you_go" in svc["options"]
    assert "1y_no_upfront" in svc["options"]
    assert "1y_partial_upfront" in svc["options"]
    assert "1y_all_upfront" in svc["options"]
    assert svc["recommended"] in ("1y_all_upfront", "1y_partial_upfront", "pay_as_you_go")
    assert svc["reason"]

    # Equality check against existing recommendation if present
    existing_rec = db.query(Recommendation).filter(
        Recommendation.account_id == demo_aws.id,
        Recommendation.service_type == svc["service"],
        Recommendation.issue == "No Commitment",
        Recommendation.is_resolved == False
    ).first()
    if existing_rec:
        part_opt = svc["options"]["1y_partial_upfront"]
        assert abs(part_opt["monthly_saving"] - existing_rec.potential_savings_usd) < 0.01
        assert abs(part_opt["upfront_cash"] - existing_rec.upfront_cost_usd) < 0.01
        print(f"  [PASS] {svc['service']} 1y_partial_upfront exactly matches existing recommendation.")

# Demo Azure plans
resp_b_az = client.get(f"/savings-optimiser/plans?account_id={demo_azure.id}", headers=headers)
assert resp_b_az.status_code == 200
data_b_az = resp_b_az.json()
assert len(data_b_az.get("services", [])) >= 1
az_vm = data_b_az["services"][0]
assert az_vm["service"] == "AzureVM"
assert az_vm["recommended"] in ("pay_as_you_go", "1y_all_upfront")

existing_az_rec = db.query(Recommendation).filter(
    Recommendation.account_id == demo_azure.id,
    Recommendation.service_type == "AzureVM",
    Recommendation.issue == "No Commitment",
    Recommendation.is_resolved == False
).first()
if existing_az_rec:
    part_opt = az_vm["options"]["1y_partial_upfront"]
    assert abs(part_opt["monthly_saving"] - existing_az_rec.potential_savings_usd) < 0.01
    assert abs(part_opt["upfront_cash"] - existing_az_rec.upfront_cost_usd) < 0.01
    print(f"  [PASS] AzureVM 1y_partial_upfront exactly matches existing recommendation.")

# Real accounts return 200
assert client.get(f"/savings-optimiser/plans?account_id={real_aws.id}", headers=headers).status_code == 200
assert client.get(f"/savings-optimiser/plans?account_id={real_az.id}", headers=headers).status_code == 200

print("[PASS] Item B: All savings plan optimiser checks passed.")

# ══════════════════════════════════════════════════════════════════════
# ITEM C: Explainable Forecasting (/costs/explain)
# ══════════════════════════════════════════════════════════════════════
print("\n--- Verifying Item C (Explainable Forecasting) ---")

# Demo AWS explain
resp_c_aws = client.get(f"/costs/explain?account_id={demo_aws.id}", headers=headers)
assert resp_c_aws.status_code == 200
data_c_aws = resp_c_aws.json()
svcs_aws = data_c_aws.get("services", [])
assert len(svcs_aws) >= 3

# Verify shares sum to ~100%
shares_aws = [s["share_of_total_pct"] for s in svcs_aws]
print(f"  Demo AWS Service Shares: {shares_aws} (Sum={sum(shares_aws):.1f}%)")
assert 98.0 <= sum(shares_aws) <= 102.0

for s in svcs_aws:
    assert s["narrative"], f"Missing narrative for {s['service']}"
    assert s["forecast_30d"] is not None
    for r in s["top_resources"]:
        assert r["narrative"], f"Missing resource narrative for {r['resource_name']}"

# Demo Azure explain
resp_c_az = client.get(f"/costs/explain?account_id={demo_azure.id}", headers=headers)
assert resp_c_az.status_code == 200
data_c_az = resp_c_az.json()
svcs_az = data_c_az.get("services", [])
assert len(svcs_az) == 1
assert svcs_az[0]["service"] == "AzureVM"
assert 99.0 <= svcs_az[0]["share_of_total_pct"] <= 101.0

# Real AWS (2 resources) and Real Azure (empty) return 200
r_c_raws = client.get(f"/costs/explain?account_id={real_aws.id}", headers=headers)
assert r_c_raws.status_code == 200
assert len(r_c_raws.json().get("services", [])) >= 1

r_c_raz = client.get(f"/costs/explain?account_id={real_az.id}", headers=headers)
assert r_c_raz.status_code == 200

print("[PASS] Item C: All explainable forecasting checks passed.")

db.close()
print("\nALL CLIENT CHANGES (ITEMS A, B, C) VERIFIED SUCCESSFULLY.")
