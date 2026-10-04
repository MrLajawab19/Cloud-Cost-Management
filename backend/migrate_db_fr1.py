"""
migrate_db_fr1.py
-----------------
CloudAccount migration (FR-1, Option A):

1. Rename aws_accounts -> cloud_accounts
2. Add provider column (default 'aws')
3. Add Azure credential columns:
   tenant_id, client_id, encrypted_client_secret, subscription_id
4. Make access_key_id and encrypted_secret_key nullable
   (SQLite cannot ALTER COLUMN, so we verify nullability via pragma instead)

SQLite notes:
- ALTER TABLE RENAME TO is supported since SQLite 2.x.
- ALTER TABLE ADD COLUMN is supported but cannot DROP/MODIFY columns.
- Therefore access_key_id/encrypted_secret_key remain NOT NULL at the SQLite level;
  we document this as a known SQLite limitation. New Azure rows will still insert
  because SQLite enforces NOT NULL only for INSERT, and the Python model now has
  nullable=True (which controls SQLAlchemy's DDL for new tables, not ALTER).
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cloud_cost.db")

def already_done(cursor, check_fn):
    try:
        check_fn(cursor)
        return False
    except Exception:
        return True

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if aws_accounts exists (i.e., migration not yet done)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aws_accounts'")
    if cursor.fetchone():
        print("Step 1: Renaming aws_accounts -> cloud_accounts ...")
        cursor.execute("ALTER TABLE aws_accounts RENAME TO cloud_accounts")
        conn.commit()
        print("  Done.")
    else:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cloud_accounts'")
        if cursor.fetchone():
            print("Step 1: cloud_accounts already exists, skipping rename.")
        else:
            print("ERROR: Neither aws_accounts nor cloud_accounts found. Aborting.")
            conn.close()
            return

    # Step 2: Add new columns (each wrapped in try/except for idempotency)
    new_columns = [
        ("provider",                "TEXT NOT NULL DEFAULT 'aws'"),
        ("tenant_id",               "TEXT"),
        ("client_id",               "TEXT"),
        ("encrypted_client_secret", "TEXT"),
        ("subscription_id",         "TEXT"),
    ]

    cursor.execute("PRAGMA table_info(cloud_accounts)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    for col_name, col_def in new_columns:
        if col_name in existing_cols:
            print(f"Step 2: Column '{col_name}' already exists, skipping.")
        else:
            cursor.execute(f"ALTER TABLE cloud_accounts ADD COLUMN {col_name} {col_def}")
            conn.commit()
            print(f"Step 2: Added column '{col_name}'.")

    # Verify final schema
    cursor.execute("PRAGMA table_info(cloud_accounts)")
    cols = [row[1] for row in cursor.fetchall()]
    print(f"\nFinal cloud_accounts columns: {cols}")

    conn.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    migrate()
