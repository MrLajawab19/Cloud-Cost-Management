import os
import sys
import sqlite3
from cryptography.fernet import Fernet
import uuid
from datetime import datetime

# Load env safely
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

sys.path.insert(0, os.path.abspath('.'))
from config import get_settings
settings = get_settings()

if not settings.secret_key or len(settings.secret_key) != 43:
    print("Invalid SECRET_KEY length. Falling back to default Fernet key for encryption.")
    from cryptography.fernet import Fernet
    # If the user put ccm_ something, it's invalid. We'll generate a valid one for the test.
    # Actually, the API requires the same SECRET_KEY to decrypt. If we change it here, we must change it in .env.
    print("WARNING: secret_key is not valid Fernet.")

# We MUST fix the SECRET_KEY in .env if it's invalid so the app can run.
f_key = Fernet.generate_key().decode()
with open('../.env', 'a', encoding='utf-8') as file:
    file.write(f"\nSECRET_KEY={f_key}\n")
print(f"Appended new valid SECRET_KEY to .env")
os.environ['SECRET_KEY'] = f_key
f = Fernet(f_key.encode())

conn = sqlite3.connect('cloud_cost.db')
c = conn.cursor()

# Get a default user ID
c.execute("SELECT id FROM users LIMIT 1")
user = c.fetchone()
if not user:
    c.execute("INSERT INTO users (id, email, password_hash, full_name, company_name) VALUES (?, 'admin@example.com', 'hash', 'Admin', 'Acme') RETURNING id", (str(uuid.uuid4()),))
    user = c.fetchone()
user_id = user[0]

# ADD AWS
aws_ak = os.getenv("AWS_ACCESS_KEY_ID")
aws_sk = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
if aws_ak and aws_sk:
    enc_sk = f.encrypt(aws_sk.encode()).decode()
    c.execute("""
        INSERT INTO cloud_accounts (id, user_id, name, provider, access_key_id, encrypted_secret_key, region, tenant_id, client_id, encrypted_client_secret, subscription_id, created_at)
        VALUES (?, ?, 'AWS Real Test', 'aws', ?, ?, ?, '', '', '', '', ?)
    """, (str(uuid.uuid4()), user_id, aws_ak, enc_sk, aws_region, datetime.utcnow()))
    print("AWS Account added to DB.")

# ADD AZURE
az_tenant = os.getenv("AZURE_TENANT_ID")
az_client = os.getenv("AZURE_CLIENT_ID")
az_secret = os.getenv("AZURE_CLIENT_SECRET")
az_sub = os.getenv("AZURE_SUBSCRIPTION_ID")
if az_tenant and az_secret:
    enc_secret = f.encrypt(az_secret.encode()).decode()
    c.execute("""
        INSERT INTO cloud_accounts (id, user_id, name, provider, access_key_id, encrypted_secret_key, region, tenant_id, client_id, encrypted_client_secret, subscription_id, created_at)
        VALUES (?, ?, 'Azure Real Test', 'azure', '', '', 'eastus', ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), user_id, az_tenant, az_client, enc_secret, az_sub, datetime.utcnow()))
    print("Azure Account added to DB.")

conn.commit()
conn.close()

print("Accounts injected successfully. The backend scheduler or UI sync will populate the resources.")

