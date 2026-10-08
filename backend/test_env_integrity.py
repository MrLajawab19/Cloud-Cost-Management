import os
import sys

def get_encoding(path):
    with open(path, 'rb') as f:
        raw = f.read(4)
        if raw.startswith(b'\xff\xfe'): return 'UTF-16 LE BOM'
        elif raw.startswith(b'\xfe\xff'): return 'UTF-16 BE BOM'
        elif raw.startswith(b'\xef\xbb\xbf'): return 'UTF-8 BOM'
        else: return 'UTF-8 / ASCII'

root_env = '../.env'
backend_env = '.env'

print("--- INITIAL ENCODING ---")
if os.path.exists(root_env):
    print(f"../.env: {get_encoding(root_env)}")
if os.path.exists(backend_env):
    print(f".env: {get_encoding(backend_env)}")

# Force pydantic to load
sys.path.insert(0, os.path.abspath('.'))
from config import get_settings
settings = get_settings()
import sqlite3
from cryptography.fernet import Fernet

print("\n--- INITIAL LOAD ---")
print(f"DEMO_MODE: {settings.demo_mode}")
if settings.database_url:
    print(f"DATABASE_URL scheme: {settings.database_url.split('://')[0]}")
if settings.secret_key:
    print(f"SECRET_KEY length: {len(settings.secret_key)}, prefix: {settings.secret_key[:4]}")

try:
    f = Fernet(settings.secret_key.encode())
    conn = sqlite3.connect('cloud_cost.db')
    c = conn.cursor()
    c.execute("SELECT provider, encrypted_secret_key FROM cloud_accounts WHERE provider='aws'")
    rows = c.fetchall()
    print(f"Found {len(rows)} AWS accounts.")
    success_count = 0
    for row in rows:
        if row[1]:
            f.decrypt(row[1].encode())
            success_count += 1
    print(f"AWS decryption SUCCESS for {success_count} accounts")
except Exception as e:
    print(f"AWS decryption FAILED: {e}")

# FIX ENCODING
print("\n--- FIXING ENCODING ---")
def fix_encoding(path):
    if not os.path.exists(path): return
    with open(path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        data = f.read()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(data)
    print(f"Re-saved {path} as clean UTF-8.")

fix_encoding(root_env)
fix_encoding(backend_env)

# RE-VERIFY ENCODING
print("\n--- FINAL ENCODING ---")
if os.path.exists(root_env):
    print(f"../.env: {get_encoding(root_env)}")
if os.path.exists(backend_env):
    print(f".env: {get_encoding(backend_env)}")
