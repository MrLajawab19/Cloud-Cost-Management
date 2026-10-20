"""
migrate_db_currency.py
────────────────────────
Database migration for Item I: Currency support.
Adds `original_cost_amount` and `cost_currency` to the `resources` table.
Backs up target database to a timestamped .bak before applying changes.
"""

import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime


def migrate(db_path: str = "cloud_cost.db"):
    db_file = Path(db_path).resolve()
    print(f"Target database: {db_file}")

    if not db_file.exists():
        print(f"Database file does not exist: {db_file}")
        return

    # 1. Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_file.with_name(f"{db_file.name}.bak_{timestamp}")
    shutil.copy2(db_file, backup_path)
    print(f"Created backup: {backup_path}")

    # 2. Inspect existing columns
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(resources)")
    existing_cols = {row[1]: row for row in cursor.fetchall()}

    # 3. Add missing columns only
    if "original_cost_amount" not in existing_cols:
        cursor.execute("ALTER TABLE resources ADD COLUMN original_cost_amount FLOAT")
        print("Added column: original_cost_amount FLOAT")
    else:
        print("Column original_cost_amount already exists, skipping.")

    if "cost_currency" not in existing_cols:
        cursor.execute("ALTER TABLE resources ADD COLUMN cost_currency VARCHAR(10)")
        print("Added column: cost_currency VARCHAR(10)")
    else:
        print("Column cost_currency already exists, skipping.")

    conn.commit()

    # 4. Print PRAGMA table_info after migration
    print("\nPRAGMA table_info(resources) after migration:")
    cursor.execute("PRAGMA table_info(resources)")
    rows = cursor.fetchall()
    for row in rows:
        print(f"  cid={row[0]:<2} name={row[1]:<25} type={row[2]:<15} notnull={row[3]} dflt={row[4]} pk={row[5]}")

    conn.close()
    print("\nMigration finished successfully.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "cloud_cost.db"
    migrate(target)
