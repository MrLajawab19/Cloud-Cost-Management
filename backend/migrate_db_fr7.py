import sqlite3

def migrate():
    conn = sqlite3.connect("cloud_cost.db")
    cursor = conn.cursor()
    
    # 1. Add fields to aws_accounts
    try:
        cursor.execute("ALTER TABLE aws_accounts ADD COLUMN auto_remediate_enabled BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute("ALTER TABLE aws_accounts ADD COLUMN budget_threshold_usd FLOAT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE aws_accounts ADD COLUMN grace_period_hours INTEGER DEFAULT 48")
    except sqlite3.OperationalError:
        pass
        
    # 2. Add fields to recommendations
    try:
        cursor.execute("ALTER TABLE recommendations ADD COLUMN remediation_type VARCHAR(50) DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE recommendations ADD COLUMN ignore_remediation BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()
    print("FR-7 Schema migration completed successfully on cloud_cost.db.")

if __name__ == "__main__":
    migrate()
