"""
config.py — Application configuration loaded from environment variables.
All secrets are read from .env (never hardcoded).
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache

_ENV_PATH = Path(__file__).resolve().parent / ".env"
_BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ── AWS ──────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "sqlite:///./cloud_cost.db"

    @field_validator("database_url", mode="after")
    @classmethod
    def _resolve_sqlite_db_url(cls, v: str) -> str:
        if v.startswith("sqlite:///"):
            raw_path = v[len("sqlite:///"):]
            if raw_path != ":memory:" and raw_path:
                path_obj = Path(raw_path)
                if not path_obj.is_absolute():
                    resolved = (_BACKEND_DIR / path_obj).resolve()
                    return f"sqlite:///{resolved.as_posix()}"
        return v

    # ── App ──────────────────────────────────────────────────────
    demo_mode: bool = False  # True → use simulated data
    collection_interval_hours: int = 6
    secret_key: str = "change_me"

    model_config = {
        "env_file": _ENV_PATH,
        "case_sensitive": False,
        "extra": "ignore",  # Silently ignore VITE_*, POSTGRES_*, etc.
    }


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()

# Currency fixed conversion rates relative to USD (fixed assumption)
CURRENCY_FIXED_RATES = {"USD": 1.0, "INR": 0.0115}

