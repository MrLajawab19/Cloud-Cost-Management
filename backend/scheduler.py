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


def run_collection_pipeline():
    """
    Full pipeline:
      1. Fetch resources from AWS (or demo data)
      2. Upsert into Resource table
      3. Record daily cost snapshot
      4. Regenerate recommendations
    """
    logger.info("⏰ Scheduled collection pipeline started.")
    db = SessionLocal()
    try:
        if settings.demo_mode:
            resources = aws_collector.collect_demo_data()
            logger.info("DEMO MODE: Using simulated AWS data.")
        else:
            resources = aws_collector.collect_all()

        upsert_resources(db, resources)
        record_daily_costs(db, resources)
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
