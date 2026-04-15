from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = BACKEND_ROOT / "data" / "mock_data.parquet"
DEFAULT_FRONTEND_ORIGIN = "http://127.0.0.1:3000"


def get_data_path() -> Path:
    raw_path = os.getenv("DDTRADING_DATA_PATH")
    if not raw_path:
        return DEFAULT_DATA_PATH
    return Path(raw_path).expanduser().resolve()


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv("DDTRADING_CORS_ORIGINS", DEFAULT_FRONTEND_ORIGIN)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or [DEFAULT_FRONTEND_ORIGIN]
