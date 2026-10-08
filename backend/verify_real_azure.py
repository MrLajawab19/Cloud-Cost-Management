import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

# Manually parse to avoid python-dotenv encoding issues with UTF-16 BOM
def load_env_manually(path):
    try:
        with open(path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ[k.strip()] = v.strip()
    except Exception:
        pass

load_env_manually(os.path.join(os.path.dirname(__file__), '.env'))
load_env_manually(os.path.join(os.path.dirname(__file__), '..', '.env'))

vars_to_check = [
    "AZURE_TENANT_ID",
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_SUBSCRIPTION_ID"
]

print("--- 2. CREDENTIAL PRESENCE CHECK ---")
missing = []
for var in vars_to_check:
    val = os.getenv(var)
    if val and val.strip():
        print(f"[OK] {var} is present.")
    else:
        print(f"[MISSING] {var} is not set or empty.")
        missing.append(var)

if missing:
    print("Cannot proceed with missing credentials.")
    sys.exit(1)

tenant = os.getenv("AZURE_TENANT_ID")
client = os.getenv("AZURE_CLIENT_ID")
secret = os.getenv("AZURE_CLIENT_SECRET")
sub = os.getenv("AZURE_SUBSCRIPTION_ID")

print("\n--- 3. MASKED CREDENTIALS ---")
print(f"Tenant ID:       ***{tenant[-4:] if len(tenant) > 4 else tenant}")
print(f"Client ID:       ***{client[-4:] if len(client) > 4 else client}")
print(f"Client Secret:   [HIDDEN, length={len(secret)}]")
print(f"Subscription ID: ***{sub[-4:] if len(sub) > 4 else sub}")

print("\n--- 4. RUNNING REAL PIPELINE ---")
from services.azure_collector import collect_all
from azure.identity import ClientSecretCredential
print("Testing Authentication implicitly via collect_all()...")
# We intercept logger warnings to detect specific API failures
class LogInterceptor(logging.Handler):
    def __init__(self):
        super().__init__()
        self.warnings = []
    def emit(self, record):
        self.warnings.append(record.getMessage())

interceptor = LogInterceptor()
logging.getLogger("services.azure_collector").addHandler(interceptor)

resources = collect_all(tenant, client, secret, sub, "default", "real_test")

print("\n--- DISCOVERED VMS ---")
if not resources:
    print("No VMs discovered. Either none exist, or Virtual Machine Contributor/Reader role is missing.")
    
for r in resources:
    cpu = r.get('cpu_utilization_avg')
    cost = r.get('daily_cost_usd')
    
    print(f"\nVM Name: {r.get('resource_name')}")
    print(f"  Region: {r.get('region')}")
    print(f"  Power State: {r.get('status')}")
    
    if cpu is None:
        print("  CPU Avg: None [WARNING: 'Monitoring Reader' role may be missing, metrics API failed, or VM lacks metric history]")
    else:
        print(f"  CPU Avg: {cpu:.2f}%")
        
    if cost == 0.0 or cost is None:
        print(f"  Daily Cost: ${cost} [WARNING: Cost is zero. Either new subscription (24-48h delay), 'Cost Management Reader' role missing, or silent API failure]")
    else:
        print(f"  Daily Cost: ${cost:.4f}")

print("\n--- API CALL STATUS ---")
cost_failed = any("Cost Management" in w for w in interceptor.warnings)
metrics_failed = any("metrics" in w for w in interceptor.warnings)
compute_failed = any("VM" in w and "metrics" not in w and "Cost Management" not in w for w in interceptor.warnings)

print(f"Cost Management API: {'[WARNING logged]' if cost_failed else '[SUCCESS (or empty)]'}")
print(f"Azure Monitor API:   {'[WARNING logged]' if metrics_failed else '[SUCCESS (or empty)]'}")
print(f"Compute VM API:      {'[WARNING logged]' if compute_failed else '[SUCCESS]'}")
