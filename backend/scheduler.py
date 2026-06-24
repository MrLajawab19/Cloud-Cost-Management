"""
scheduler.py — APScheduler background job.
Runs the full AWS collection pipeline on a configurable interval.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import get_settings
from database import SessionLocal
from services import aws_collector
from services.cost_estimator import upsert_resources, record_daily_costs
from services.cleanup_advisor import generate_recommendations

logger    = logging.getLogger(__name__)
settings  = get_settings()
scheduler = BackgroundScheduler(timezone="UTC")


def run_collection_pipeline(user_id=None, account_id=None):
    """
    Full pipeline:
      1. Fetch resources from AWS for targeted accounts (or all if none specified)
      2. Upsert into Resource table
      3. Record daily cost snapshot
      4. Regenerate recommendations
    """
    logger.info("⏰ Scheduled collection pipeline started.")
    db = SessionLocal()
    try:
        from models.account import AWSAccount
        from services.security import decrypt_secret
        
        query = db.query(AWSAccount)
        if user_id:
            query = query.filter(AWSAccount.user_id == user_id)
        if account_id:
            query = query.filter(AWSAccount.id == account_id)
            
        accounts = query.all()
        if not accounts and not settings.demo_mode:
            logger.info("No AWS Accounts matching criteria. Skipping collection.")
            return

        all_resources = []
        synced_account_ids = []
        if settings.demo_mode:
            all_resources = aws_collector.collect_demo_data()
            logger.info("DEMO MODE: Using simulated AWS data.")
        else:
            for acc in accounts:
                try:
                    decrypted_secret = decrypt_secret(acc.encrypted_secret_key)
                    resources = aws_collector.collect_all(
                        access_key_id=acc.access_key_id,
                        secret_access_key=decrypted_secret,
                        region_name=acc.region,
                        account_id=acc.id
                    )
                    all_resources.extend(resources)
                    synced_account_ids.append(acc.id)
                except Exception as e:
                    logger.error(f"Failed to collect for account {acc.id}: {e}")

        # Upsert resources and delete stale ones for synced accounts
        upsert_resources(db, all_resources, synced_account_ids)
        
        if all_resources:
            record_daily_costs(db, all_resources)
            
        generate_recommendations(db)
        logger.info("✅ Collection pipeline complete.")
    except Exception as e:
        logger.error(f"❌ Collection pipeline failed: {e}", exc_info=True)
    finally:
        db.close()


def start_scheduler():
    """Register and start the background scheduler."""
    interval_hours = settings.collection_interval_hours

    scheduler.add_job(
        run_collection_pipeline,
        trigger=IntervalTrigger(hours=interval_hours),
        id="aws_collection",
        name="AWS Resource Collection",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started — collecting every {interval_hours}h.")


def stop_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
