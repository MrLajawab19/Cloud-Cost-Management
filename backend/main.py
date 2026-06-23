"""
main.py — FastAPI application entry point.
Handles app lifecycle, CORS, route registration, and startup data seed.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import engine, Base
from scheduler import start_scheduler, stop_scheduler, run_collection_pipeline

# Import all models so SQLAlchemy registers them before create_all
import models.resource      # noqa: F401
import models.cost_record   # noqa: F401

from routes import resources, costs, recommendations, predictions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger   = logging.getLogger(__name__)
settings = get_settings()


# ── Startup / Shutdown ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown of the FastAPI application."""
    logger.info("🚀 Cloud Cost Management API starting…")

    # Create all DB tables (idempotent — won't overwrite existing)
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables ensured.")

    # Run an immediate collection on startup so the dashboard has data
    logger.info("Running initial data collection…")
    run_collection_pipeline()

    # Start background scheduler
    start_scheduler()

    yield  # App is running

    # Shutdown
    stop_scheduler()
    logger.info("👋 Cloud Cost Management API shut down.")


# ── App Instance ─────────────────────────────────────────────────

app = FastAPI(
    title="Cloud Cost Management API",
    description=(
        "REST API for tracking AWS cloud resource usage, estimating monthly costs, "
        "recommending cleanup actions, and predicting future spend with ML."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",      # Swagger UI
    redoc_url="/redoc",    # ReDoc UI
)

# ── CORS ─────────────────────────────────────────────────────────
# Allow the React frontend (running on port 3000) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────
app.include_router(resources.router)
app.include_router(costs.router)
app.include_router(recommendations.router)
app.include_router(predictions.router)


# ── Health Check ─────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check():
    """Simple health check endpoint used by Docker and load balancers."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "demo_mode": settings.demo_mode,
        "region": settings.aws_default_region,
    }


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Cloud Cost Management API",
        "docs": "/docs",
        "health": "/health",
    }
