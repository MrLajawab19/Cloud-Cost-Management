"""
config.py — Application configuration loaded from environment variables.
All secrets are read from .env (never hardcoded).
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── AWS ──────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "postgresql://ccm_user:password@db:5432/cloud_cost_db"

    # ── App ──────────────────────────────────────────────────────
    demo_mode: bool = False          # True → use simulated data
    collection_interval_hours: int = 6
    secret_key: str = "change_me"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
