from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    data_dir: Path
    model_hub_dir: Path | None
    public_base_path: str
    default_admin_username: str
    default_admin_password: str
    user_provision_token: str | None


def load_settings() -> Settings:
    data_dir = Path(os.getenv("BOLTZ_DATA_DIR", "/data")).resolve()
    model_hub_raw = os.getenv("BOLTZ_MODEL_HUB_DIR", "/modelhub")
    model_hub_dir = Path(model_hub_raw).resolve() if model_hub_raw else None
    return Settings(
        database_url=os.getenv(
            "BOLTZ_DATABASE_URL",
            "postgresql+psycopg://boltz:boltz@127.0.0.1:5432/boltz",
        ),
        redis_url=os.getenv("BOLTZ_REDIS_URL", "redis://127.0.0.1:6379/0"),
        data_dir=data_dir,
        model_hub_dir=model_hub_dir,
        public_base_path=os.getenv("BOLTZ_PUBLIC_BASE_PATH", "/app/com.ictrek.boltz/"),
        default_admin_username=os.getenv("BOLTZ_DEFAULT_ADMIN_USERNAME", "admin"),
        default_admin_password=os.getenv("BOLTZ_DEFAULT_ADMIN_PASSWORD", "admin123456"),
        user_provision_token=os.getenv("BOLTZ_USER_PROVISION_TOKEN") or None,
    )
