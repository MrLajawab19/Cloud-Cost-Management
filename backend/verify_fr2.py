import sqlite3

conn = sqlite3.connect(r'd:\Cloud Cost Management\backend\cloud_cost.db')
cur = conn.cursor()
ACCOUNT = 'ba920050-7de7-4e98-935e-ba339b334d84'

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
