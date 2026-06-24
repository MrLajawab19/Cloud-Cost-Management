"""
services/aws_collector.py
─────────────────────────
Fetches resource data from AWS using boto3.
Supports: EC2, S3, RDS, Lambda.

In DEMO_MODE, returns realistic simulated data so the UI works
without real AWS credentials.
"""

import boto3
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── AWS Pricing (on-demand Linux, us-east-1) ─────────────────────
# Source: https://aws.amazon.com/ec2/pricing/on-demand/
EC2_HOURLY_PRICE: Dict[str, float] = {
    "t2.micro": 0.0116,   "t2.small": 0.023,    "t2.medium": 0.0464,
    "t2.large": 0.0928,   "t3.micro": 0.0104,   "t3.small": 0.0208,
    "t3.medium": 0.0416,  "t3.large": 0.0832,   "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328, "m5.large": 0.096,    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,  "c5.large": 0.085,    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,   "r5.large": 0.126,    "r5.xlarge": 0.252,
}

RDS_HOURLY_PRICE: Dict[str, float] = {
    "db.t3.micro": 0.017,  "db.t3.small": 0.034, "db.t3.medium": 0.068,
    "db.t3.large": 0.136,  "db.m5.large": 0.192, "db.m5.xlarge": 0.384,
    "db.r5.large": 0.24,   "db.r5.xlarge": 0.48,
}

S3_PRICE_PER_GB  = 0.023      # Standard storage per GB-month
S3_PRICE_PER_1K_REQUESTS = 0.0004  # GET requests per 1K
LAMBDA_PRICE_PER_GB_SEC  = 0.0000166667
LAMBDA_PRICE_PER_1M_REQ  = 0.20
HOURS_IN_MONTH = 730


def _get_boto3_session(access_key_id: str, secret_access_key: str, region_name: str):
    """Create a boto3 session using provided credentials."""
    return boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )


def _get_cloudwatch_metric(cw_client, namespace: str, metric_name: str,
                            dimensions: list, days: int = 7) -> float:
    """
    Fetch the average value of a CloudWatch metric over the past N days.
    Returns 0.0 if no data points exist.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        resp = cw_client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start,
            EndTime=end,
            Period=86400 * days,    # Single aggregated bucket
            Statistics=["Average"],
        )
        points = resp.get("Datapoints", [])
        if points:
            return round(points[0]["Average"], 2)
    except Exception as e:
        logger.warning(f"CloudWatch fetch failed ({metric_name}): {e}")
    return 0.0


# ══════════════════════════════════════════════════════════════════
#  REAL AWS COLLECTORS
# ══════════════════════════════════════════════════════════════════

def collect_ec2_instances(session) -> List[Dict[str, Any]]:
    """Fetch all EC2 instances with state, type, uptime, and CPU metrics."""
    ec2 = session.client("ec2")
    cw  = session.client("cloudwatch")
    resources = []

    try:
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page["Reservations"]:
                for inst in reservation["Instances"]:
                    instance_id   = inst["InstanceId"]
                    instance_type = inst.get("InstanceType", "unknown")
                    state         = inst["State"]["Name"]
                    launch_time   = inst.get("LaunchTime")
                    az            = inst.get("Placement", {}).get("AvailabilityZone", "")
                    region        = az[:-1] if az else session.region_name

                    # Name from tags
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    name = tags.get("Name", instance_id)

                    # Runtime hours (0 if stopped)
                    runtime_hours = 0.0
                    if state == "running" and launch_time:
                        delta = datetime.now(timezone.utc) - launch_time
                        runtime_hours = round(delta.total_seconds() / 3600, 2)

                    # CPU utilisation (7-day avg)
                    cpu_avg = 0.0
                    if state == "running":
                        cpu_avg = _get_cloudwatch_metric(
                            cw, "AWS/EC2", "CPUUtilization",
                            [{"Name": "InstanceId", "Value": instance_id}],
                        )

                    # Cost estimate
                    hourly = EC2_HOURLY_PRICE.get(instance_type, 0.05)
                    monthly_cost = hourly * HOURS_IN_MONTH if state == "running" else 0.0

                    resources.append({
                        "resource_id":   instance_id,
                        "resource_name": name,
                        "service_type":  "EC2",
                        "region":        region,
                        "status":        state,
                        "resource_type": instance_type,
                        "tags":          json.dumps(tags),
                        "cpu_utilization_avg":    cpu_avg,
                        "runtime_hours":          runtime_hours,
                        "estimated_monthly_cost": round(monthly_cost, 4),
                        "launch_time":            launch_time,
                        "is_idle": (state == "running" and cpu_avg < 5.0 and runtime_hours > 168),
                    })
    except Exception as e:
        logger.error(f"EC2 collection failed: {e}")

    return resources


def collect_s3_buckets(session) -> List[Dict[str, Any]]:
    """Fetch all S3 buckets with size and request count metrics."""
    s3  = session.client("s3")
    cw  = session.client("cloudwatch")
    resources = []

    try:
        buckets = s3.list_buckets().get("Buckets", [])
        for bucket in buckets:
            name          = bucket["Name"]
            creation_date = bucket.get("CreationDate")

            # Try to get bucket region
            try:
                loc = s3.get_bucket_location(Bucket=name)
                region = loc.get("LocationConstraint") or "us-east-1"
            except Exception:
                region = session.region_name

            # Storage size (CloudWatch BucketSizeBytes, daily metric)
            size_gb = _get_cloudwatch_metric(
                cw, "AWS/S3", "BucketSizeBytes",
                [{"Name": "BucketName", "Value": name},
                 {"Name": "StorageType", "Value": "StandardStorage"}],
                days=1,
            ) / (1024 ** 3)  # bytes → GB

            # Number of objects
            obj_count = _get_cloudwatch_metric(
                cw, "AWS/S3", "NumberOfObjects",
                [{"Name": "BucketName", "Value": name},
                 {"Name": "StorageType", "Value": "AllStorageTypes"}],
                days=1,
            )

            monthly_cost = round(size_gb * S3_PRICE_PER_GB, 4)

            resources.append({
                "resource_id":   name,
                "resource_name": name,
                "service_type":  "S3",
                "region":        region,
                "status":        "available",
                "resource_type": "S3 Bucket",
                "tags":          "{}",
                "storage_size_gb":        round(size_gb, 4),
                "request_count":          obj_count,
                "estimated_monthly_cost": monthly_cost,
                "launch_time":            creation_date,
                "is_idle": (size_gb < 0.001 and obj_count == 0),
            })
    except Exception as e:
        logger.error(f"S3 collection failed: {e}")

    return resources


def collect_rds_instances(session) -> List[Dict[str, Any]]:
    """Fetch all RDS instances with state and cost estimate."""
    rds = session.client("rds")
    resources = []

    try:
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for inst in page["DBInstances"]:
                db_id    = inst["DBInstanceIdentifier"]
                db_class = inst.get("DBInstanceClass", "db.t3.micro")
                engine   = inst.get("Engine", "unknown")
                status   = inst.get("DBInstanceStatus", "unknown")
                az       = inst.get("AvailabilityZone", "")
                region   = az[:-1] if az else session.region_name
                storage  = inst.get("AllocatedStorage", 0)

                hourly = RDS_HOURLY_PRICE.get(db_class, 0.05)
                monthly_cost = hourly * HOURS_IN_MONTH if status == "available" else 0.0

                resources.append({
                    "resource_id":   db_id,
                    "resource_name": db_id,
                    "service_type":  "RDS",
                    "region":        region,
                    "status":        status,
                    "resource_type": f"{db_class} ({engine})",
                    "tags":          "{}",
                    "storage_size_gb":        float(storage),
                    "estimated_monthly_cost": round(monthly_cost, 4),
                    "launch_time":            inst.get("InstanceCreateTime"),
                    "is_idle": (status == "stopped"),
                })
    except Exception as e:
        logger.error(f"RDS collection failed: {e}")

    return resources


def collect_lambda_functions(session) -> List[Dict[str, Any]]:
    """Fetch all Lambda functions with invocation counts and cost estimate."""
    lam = session.client("lambda")
    cw  = session.client("cloudwatch")
    resources = []

    try:
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page["Functions"]:
                fn_name  = fn["FunctionName"]
                fn_arn   = fn["FunctionArn"]
                runtime  = fn.get("Runtime", "unknown")
                memory   = fn.get("MemorySize", 128)      # MB
                region   = session.region_name

                # Invocation count (30 days)
                invocations = _get_cloudwatch_metric(
                    cw, "AWS/Lambda", "Invocations",
                    [{"Name": "FunctionName", "Value": fn_name}],
                    days=30,
                )

                # Average duration (ms)
                avg_duration_ms = _get_cloudwatch_metric(
                    cw, "AWS/Lambda", "Duration",
                    [{"Name": "FunctionName", "Value": fn_name}],
                    days=30,
                )

                # Cost: (invocations/1M * $0.20) + (invocations * duration_sec * memory_GB * $0.0000166667)
                memory_gb       = memory / 1024
                duration_sec    = avg_duration_ms / 1000
                gb_seconds      = invocations * duration_sec * memory_gb
                monthly_cost    = (
                    (invocations / 1_000_000) * LAMBDA_PRICE_PER_1M_REQ
                    + gb_seconds * LAMBDA_PRICE_PER_GB_SEC
                )

                resources.append({
                    "resource_id":   fn_arn,
                    "resource_name": fn_name,
                    "service_type":  "Lambda",
                    "region":        region,
                    "status":        "active",
                    "resource_type": f"{runtime} ({memory}MB)",
                    "tags":          "{}",
                    "request_count":          invocations,
                    "estimated_monthly_cost": round(monthly_cost, 6),
                    "launch_time":            None,
                    "is_idle": (invocations == 0),
                })
    except Exception as e:
        logger.error(f"Lambda collection failed: {e}")

    return resources


def collect_all(access_key_id: str, secret_access_key: str, region_name: str, account_id: str) -> List[Dict[str, Any]]:
    """Run all collectors and return combined resource list for an account."""
    logger.info(f"Starting AWS resource collection for account {account_id}…")
    session = _get_boto3_session(access_key_id, secret_access_key, region_name)
    all_resources = []
    all_resources.extend(collect_ec2_instances(session))
    all_resources.extend(collect_s3_buckets(session))
    all_resources.extend(collect_rds_instances(session))
    all_resources.extend(collect_lambda_functions(session))
    
    # Append account_id
    for r in all_resources:
        r["account_id"] = account_id

    logger.info(f"Collection complete for account {account_id}. Total resources: {len(all_resources)}")
    return all_resources


# ══════════════════════════════════════════════════════════════════
#  DEMO MODE — Simulated data for testing without AWS credentials
# ══════════════════════════════════════════════════════════════════

def collect_demo_data() -> List[Dict[str, Any]]:
    """Return realistic simulated AWS resource data for demo/testing."""
    now = datetime.now(timezone.utc)
    return [
        # EC2 Instances
        {
            "resource_id": "i-0a1b2c3d4e5f00001", "resource_name": "web-server-prod",
            "service_type": "EC2", "region": "us-east-1", "status": "running",
            "resource_type": "t3.medium", "tags": '{"Env":"prod","Team":"backend"}',
            "cpu_utilization_avg": 72.3, "runtime_hours": 720.0,
            "estimated_monthly_cost": 30.37, "launch_time": now - timedelta(days=30),
            "is_idle": False,
        },
        {
            "resource_id": "i-0a1b2c3d4e5f00002", "resource_name": "api-server-prod",
            "service_type": "EC2", "region": "us-east-1", "status": "running",
            "resource_type": "m5.large", "tags": '{"Env":"prod","Team":"api"}',
            "cpu_utilization_avg": 45.1, "runtime_hours": 720.0,
            "estimated_monthly_cost": 70.08, "launch_time": now - timedelta(days=60),
            "is_idle": False,
        },
        {
            "resource_id": "i-0a1b2c3d4e5f00003", "resource_name": "dev-instance-old",
            "service_type": "EC2", "region": "us-east-1", "status": "running",
            "resource_type": "t3.micro", "tags": '{"Env":"dev","Team":"devops"}',
            "cpu_utilization_avg": 1.2, "runtime_hours": 2160.0,
            "estimated_monthly_cost": 7.59, "launch_time": now - timedelta(days=90),
            "is_idle": True,
        },
        {
            "resource_id": "i-0a1b2c3d4e5f00004", "resource_name": "staging-server",
            "service_type": "EC2", "region": "us-west-2", "status": "stopped",
            "resource_type": "t3.large", "tags": '{"Env":"staging"}',
            "cpu_utilization_avg": 0.0, "runtime_hours": 0.0,
            "estimated_monthly_cost": 0.0, "launch_time": now - timedelta(days=45),
            "is_idle": True,
        },
        # S3 Buckets
        {
            "resource_id": "my-company-prod-assets", "resource_name": "my-company-prod-assets",
            "service_type": "S3", "region": "us-east-1", "status": "available",
            "resource_type": "S3 Bucket", "tags": '{"Env":"prod"}',
            "storage_size_gb": 342.5, "request_count": 150000,
            "estimated_monthly_cost": 7.88, "launch_time": now - timedelta(days=365),
            "is_idle": False,
        },
        {
            "resource_id": "my-company-backups-2023", "resource_name": "my-company-backups-2023",
            "service_type": "S3", "region": "us-east-1", "status": "available",
            "resource_type": "S3 Bucket", "tags": '{}',
            "storage_size_gb": 890.0, "request_count": 0,
            "estimated_monthly_cost": 20.47, "launch_time": now - timedelta(days=200),
            "is_idle": True,
        },
        {
            "resource_id": "temp-dev-uploads-bucket", "resource_name": "temp-dev-uploads-bucket",
            "service_type": "S3", "region": "us-east-1", "status": "available",
            "resource_type": "S3 Bucket", "tags": '{"Env":"dev"}',
            "storage_size_gb": 0.0, "request_count": 0,
            "estimated_monthly_cost": 0.0, "launch_time": now - timedelta(days=120),
            "is_idle": True,
        },
        # RDS Instances
        {
            "resource_id": "prod-postgres-main", "resource_name": "prod-postgres-main",
            "service_type": "RDS", "region": "us-east-1", "status": "available",
            "resource_type": "db.m5.large (postgres)", "tags": '{"Env":"prod"}',
            "storage_size_gb": 100.0, "estimated_monthly_cost": 140.16,
            "launch_time": now - timedelta(days=120), "is_idle": False,
        },
        {
            "resource_id": "staging-mysql-db", "resource_name": "staging-mysql-db",
            "service_type": "RDS", "region": "us-east-1", "status": "stopped",
            "resource_type": "db.t3.medium (mysql)", "tags": '{"Env":"staging"}',
            "storage_size_gb": 20.0, "estimated_monthly_cost": 0.0,
            "launch_time": now - timedelta(days=60), "is_idle": True,
        },
        # Lambda Functions
        {
            "resource_id": "arn:aws:lambda:us-east-1:123456789:function:image-resizer",
            "resource_name": "image-resizer",
            "service_type": "Lambda", "region": "us-east-1", "status": "active",
            "resource_type": "python3.11 (512MB)", "tags": '{}',
            "request_count": 45000, "estimated_monthly_cost": 0.02,
            "launch_time": None, "is_idle": False,
        },
        {
            "resource_id": "arn:aws:lambda:us-east-1:123456789:function:old-report-gen",
            "resource_name": "old-report-gen",
            "service_type": "Lambda", "region": "us-east-1", "status": "active",
            "resource_type": "python3.8 (128MB)", "tags": '{}',
            "request_count": 0, "estimated_monthly_cost": 0.0,
            "launch_time": None, "is_idle": True,
        },
    ]
