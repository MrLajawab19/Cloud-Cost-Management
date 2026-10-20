"""
backend/scripts/cleanup_legacy_demo.py
Stage 3 Script: Clean up legacy demo account (00000000-0000-0000-0000-demoaccount01)
and retag real Azure account cost record source from aws_collected to azure_collected.

Usage:
  python cleanup_legacy_demo.py --db /path/to/cloud_cost.db [--dry-run | --execute]
"""

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import datetime

LEGACY_ACCOUNT_ID = "00000000-0000-0000-0000-demoaccount01"


def get_file_sha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_database(src_path: str) -> str:
    user_profile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "."
    backup_dir = os.path.join(user_profile, "ccm_backup")
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_filename = f"ccm_backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)
    if os.path.exists(backup_path):
        os.remove(backup_path)

    # Perform backup using shutil.copy2 to guarantee bit-for-bit identical file hash
    shutil.copy2(src_path, backup_path)

    src_hash = get_file_sha256(src_path)
    backup_hash = get_file_sha256(backup_path)

    print(f"[BACKUP] Created: {backup_path}")
    print(f"   Source SHA256: {src_hash}")
    print(f"   Backup SHA256: {backup_hash}")
    assert src_hash == backup_hash, "Backup verification failed: hash mismatch!"
    return backup_path


def run_cleanup(db_path: str, execute: bool = False):
    print(f"\n{'='*25} STAGE 3 CLEANUP SCRIPT {'='*25}")
    print(f"Database: {db_path}")
    print(f"Mode: {'EXECUTE' if execute else 'DRY-RUN'}")

    # 1. Backup first
    backup_database(db_path)

    # 2. Connect to database with FK ON
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    fk_enabled = cur.execute("PRAGMA foreign_keys").fetchone()[0]
    if fk_enabled != 1:
        raise RuntimeError("Failed to enable PRAGMA foreign_keys=ON")

    TABLES = [
        "cloud_accounts",
        "resources",
        "cost_records",
        "anomalies",
        "recommendations",
        "escalation_states",
        "remediation_logs",
    ]

    # Pre-checks & Baselines
    # Verify target legacy account exists and has NO credentials
    cur.execute("SELECT id, name, access_key_id, encrypted_secret_key FROM cloud_accounts WHERE id = ?", (LEGACY_ACCOUNT_ID,))
    legacy_row = cur.fetchone()
    if legacy_row:
        _, name, key_id, sec_key = legacy_row
        has_creds = bool((sec_key and sec_key.strip()) or (key_id and key_id.startswith("AKIA")))
        if has_creds:
            raise RuntimeError(f"Target account {LEGACY_ACCOUNT_ID} has credentials! Refusing to run.")
    else:
        print(f"Note: Target account {LEGACY_ACCOUNT_ID} does not exist in database.")

    # Find real AWS and Azure accounts
    cur.execute("SELECT id, name, provider FROM cloud_accounts WHERE id LIKE '4d62c035%'")
    real_aws = cur.fetchone()
    real_aws_id = real_aws[0] if real_aws else None

    cur.execute("SELECT id, name, provider FROM cloud_accounts WHERE id LIKE 'e72a125c%'")
    real_azure = cur.fetchone()
    real_azure_id = real_azure[0] if real_azure else None

    # Find UUID5 demo accounts (names start with 'Demo AWS' or 'Demo Azure')
    cur.execute("SELECT id, name FROM cloud_accounts WHERE id != ? AND (name LIKE 'Demo AWS%' OR name LIKE 'Demo Azure%')", (LEGACY_ACCOUNT_ID,))
    uuid5_accounts = cur.fetchall()
    uuid5_ids = [r[0] for r in uuid5_accounts]

    # Baseline counts for table-level summary
    before_counts = {}
    for t in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        before_counts[t] = cur.fetchone()[0]

    # Detailed baselines for protected accounts
    def get_acc_counts(acc_id):
        if not acc_id:
            return {}
        cur.execute("SELECT COUNT(*) FROM resources WHERE account_id = ?", (acc_id,))
        res_c = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cost_records WHERE account_id = ?", (acc_id,))
        cost_c = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM recommendations WHERE account_id = ?", (acc_id,))
        rec_c = cur.fetchone()[0]
        return {"resources": res_c, "cost_records": cost_c, "recommendations": rec_c}

    real_aws_baseline = get_acc_counts(real_aws_id)
    real_azure_baseline = get_acc_counts(real_azure_id)
    uuid5_baselines = {uid: get_acc_counts(uid) for uid in uuid5_ids}

    print("\n--- Before Counts ---")
    for t in TABLES:
        print(f"  {t:20s}: {before_counts[t]}")
    if real_aws_id:
        print(f"  Real AWS ({real_aws_id[:8]}): {real_aws_baseline}")
    if real_azure_id:
        print(f"  Real Azure ({real_azure_id[:8]}): {real_azure_baseline}")
    print(f"  UUID5 Demo Accounts: {len(uuid5_ids)} accounts")

    try:
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")

        if legacy_row:
            # 1. Delete remediation_logs for legacy account
            cur.execute("DELETE FROM remediation_logs WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))

            # 2. Delete escalation_states for legacy account recommendations
            # Handle both hyphenated UUID and 32-char hex formats
            cur.execute(
                """
                DELETE FROM escalation_states
                WHERE recommendation_id IN (
                    SELECT id FROM recommendations WHERE account_id = ?
                )
                OR recommendation_id IN (
                    SELECT REPLACE(id, '-', '') FROM recommendations WHERE account_id = ?
                )
                """,
                (LEGACY_ACCOUNT_ID, LEGACY_ACCOUNT_ID),
            )

            # 3. Delete recommendations
            cur.execute("DELETE FROM recommendations WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))

            # 4. Delete anomalies
            cur.execute("DELETE FROM anomalies WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))

            # 5. Delete cost_records
            cur.execute("DELETE FROM cost_records WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))

            # 6. Delete resources
            cur.execute("DELETE FROM resources WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))

            # 7. Delete cloud_account
            cur.execute("DELETE FROM cloud_accounts WHERE id = ?", (LEGACY_ACCOUNT_ID,))

        # Retag real Azure cost records from aws_collected to azure_collected
        if real_azure_id:
            cur.execute(
                "UPDATE cost_records SET source = 'azure_collected' WHERE account_id = ? AND source = 'aws_collected'",
                (real_azure_id,),
            )
            retagged_count = cur.rowcount
            print(f"\nRetagged {retagged_count} cost_record row(s) for Real Azure ({real_azure_id[:8]}).")

        # ASSERTIONS
        # 1. Target account is deleted
        cur.execute("SELECT COUNT(*) FROM cloud_accounts WHERE id = ?", (LEGACY_ACCOUNT_ID,))
        assert cur.fetchone()[0] == 0, "Legacy account still exists!"
        for t in ["resources", "cost_records", "anomalies", "recommendations", "remediation_logs"]:
            cur.execute(f"SELECT COUNT(*) FROM {t} WHERE account_id = ?", (LEGACY_ACCOUNT_ID,))
            assert cur.fetchone()[0] == 0, f"Legacy account still has rows in {t}!"

        # 2. Real AWS account is unchanged
        if real_aws_id:
            cur.execute("SELECT id FROM cloud_accounts WHERE id = ?", (real_aws_id,))
            assert cur.fetchone() is not None, "Real AWS account missing!"
            cur_aws = get_acc_counts(real_aws_id)
            assert cur_aws == real_aws_baseline, f"Real AWS counts changed: {cur_aws} vs {real_aws_baseline}"

        # 3. Real Azure account is unchanged (except source retag)
        if real_azure_id:
            cur.execute("SELECT id FROM cloud_accounts WHERE id = ?", (real_azure_id,))
            assert cur.fetchone() is not None, "Real Azure account missing!"
            cur_az = get_acc_counts(real_azure_id)
            assert cur_az == real_azure_baseline, f"Real Azure counts changed: {cur_az} vs {real_azure_baseline}"
            # Check retag
            cur.execute("SELECT COUNT(*) FROM cost_records WHERE account_id = ? AND source = 'aws_collected'", (real_azure_id,))
            assert cur.fetchone()[0] == 0, "Real Azure still has aws_collected cost_records!"

        # 4. UUID5 demo accounts are completely untouched
        for uid in uuid5_ids:
            cur.execute("SELECT id FROM cloud_accounts WHERE id = ?", (uid,))
            assert cur.fetchone() is not None, f"UUID5 account {uid} missing!"
            cur_u = get_acc_counts(uid)
            assert cur_u == uuid5_baselines[uid], f"UUID5 account {uid} counts changed: {cur_u} vs {uuid5_baselines[uid]}"

        # After Counts (uncommitted view)
        after_counts = {}
        for t in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            after_counts[t] = cur.fetchone()[0]

        print("\n--- After Counts ---")
        for t in TABLES:
            delta = after_counts[t] - before_counts[t]
            delta_str = f"({delta:+d})" if delta != 0 else "(no change)"
            print(f"  {t:20s}: {after_counts[t]} {delta_str}")

        if execute:
            conn.commit()
            print("\n[EXECUTE] Transaction committed successfully.")
        else:
            conn.rollback()
            print("\n[DRY-RUN] Changes rolled back. No rows were written.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Error during cleanup: {e}. Rolled back transaction.")
        conn.close()
        raise

    conn.close()
    return before_counts, after_counts


def main():
    parser = argparse.ArgumentParser(description="Clean up legacy demo account and retag Azure collected rows.")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--execute", action="store_true", default=False, help="Execute changes (default is dry-run)")
    parser.add_argument("--dry-run", dest="execute", action="store_false", help="Run in dry-run mode (default)")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Error: Database file not found: {args.db}")
        sys.exit(1)

    run_cleanup(args.db, execute=args.execute)


if __name__ == "__main__":
    main()
