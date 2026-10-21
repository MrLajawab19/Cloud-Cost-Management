
import os
import sqlite3

db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
else:
    db_path = r'd:\Cloud Cost Management\backend\cloud_cost.db'

print(f"Engine Path: sqlite:///{db_path}")
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
cur = conn.cursor()
ACCOUNT = 'ba920050-7de7-4e98-935e-ba339b334d84'
cur.execute('SELECT COUNT(*) FROM cost_records WHERE account_id=?', (ACCOUNT,))
if cur.fetchone()[0] == 0:
    cur.execute('SELECT account_id FROM cost_records WHERE source LIKE "%demo%" OR source="synthetic_seed" LIMIT 1')
    row = cur.fetchone()
    if row:
        ACCOUNT = row[0]

print('=== 1b. Region values (tagging proxy) ===')
cur.execute('SELECT region, COUNT(*) FROM cost_records WHERE account_id=? GROUP BY region', (ACCOUNT,))
for r in cur.fetchall():
    print(r)

print()
print('=== 1b. Row count ===')
cur.execute('SELECT COUNT(*) FROM cost_records WHERE account_id=?', (ACCOUNT,))
print('Total rows:', cur.fetchone()[0])

print()
print('=== 1b. Date range ===')
cur.execute('SELECT MIN(record_date), MAX(record_date) FROM cost_records WHERE account_id=?', (ACCOUNT,))
print('Date range:', cur.fetchone())

print()
print('=== 1b. 2026-06-24 original row ===')
cur.execute('SELECT id, record_date, service_type, region, daily_cost_usd FROM cost_records WHERE record_date="2026-06-24" AND account_id=?', (ACCOUNT,))
for r in cur.fetchall():
    print(r)

print()
print('=== 1b. Sample seeded rows ===')
cur.execute('SELECT record_date, service_type, region, daily_cost_usd FROM cost_records WHERE account_id=? AND region="seeded" ORDER BY record_date LIMIT 6', (ACCOUNT,))
for r in cur.fetchall():
    print(r)

conn.close()
