from __future__ import annotations

import os
from pathlib import Path
from typing import Literal


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = BACKEND_ROOT / "data" / "mock_data.parquet"
DEFAULT_DAILY_PARQUET_PATH = BACKEND_ROOT / "data" / "ashare_daily.parquet"
DEFAULT_FRONTEND_ORIGIN = "http://127.0.0.1:3000"
DEFAULT_DATA_SOURCE: Literal["auto", "parquet", "akshare"] = "auto"
DEFAULT_AKSHARE_UNIVERSE_SIZE = 300
DEFAULT_AKSHARE_HISTORY_DAYS = 120
DEFAULT_AKSHARE_MAX_WORKERS = 8
DEFAULT_AKSHARE_CACHE_TTL_SECONDS = 600
DEFAULT_DAILY_HISTORY_DAYS = 3650
DEFAULT_DAILY_CACHE_TTL_HOURS = 24


def get_data_path() -> Path:
    raw_path = os.getenv("DDTRADING_DATA_PATH")
    if not raw_path:
        return DEFAULT_DATA_PATH
    return Path(raw_path).expanduser().resolve()


def get_data_source() -> Literal["auto", "parquet", "akshare"]:
    raw_source = os.getenv("DDTRADING_DATA_SOURCE", DEFAULT_DATA_SOURCE).strip().lower()
    if raw_source in {"auto", "parquet", "akshare"}:
        return raw_source
    raise ValueError(
        "DDTRADING_DATA_SOURCE must be one of: auto, parquet, akshare."
    )


def _get_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError as exc:  # pragma: no cover - defensive parse boundary
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return parsed


def get_akshare_universe_size() -> int:
    return _get_int_env(
        "DDTRADING_AKSHARE_UNIVERSE_SIZE",
        default=DEFAULT_AKSHARE_UNIVERSE_SIZE,
        minimum=20,
    )


def get_akshare_history_days() -> int:
    return _get_int_env(
        "DDTRADING_AKSHARE_HISTORY_DAYS",
        default=DEFAULT_AKSHARE_HISTORY_DAYS,
        minimum=30,
    )


def get_akshare_max_workers() -> int:
    return _get_int_env(
        "DDTRADING_AKSHARE_MAX_WORKERS",
        default=DEFAULT_AKSHARE_MAX_WORKERS,
        minimum=1,
    )


def get_akshare_cache_ttl_seconds() -> int:
    return _get_int_env(
        "DDTRADING_AKSHARE_CACHE_TTL_SECONDS",
        default=DEFAULT_AKSHARE_CACHE_TTL_SECONDS,
        minimum=0,
    )


def get_daily_parquet_path() -> Path:
    """本地全市场日线 parquet 的存储路径。"""
    raw_path = os.getenv("DDTRADING_DAILY_PARQUET_PATH")
    if not raw_path:
        return DEFAULT_DAILY_PARQUET_PATH
    return Path(raw_path).expanduser().resolve()


def get_daily_history_days() -> int:
    """本地日线缓存覆盖的历史天数。默认约 10 年。"""
    return _get_int_env(
        "DDTRADING_DAILY_HISTORY_DAYS",
        default=DEFAULT_DAILY_HISTORY_DAYS,
        minimum=30,
    )


def get_daily_cache_ttl_hours() -> int:
    """本地日线 parquet 的 TTL（小时）。为 0 表示永不自动刷新，只走 /refresh。"""
    return _get_int_env(
        "DDTRADING_DAILY_CACHE_TTL_HOURS",
        default=DEFAULT_DAILY_CACHE_TTL_HOURS,
        minimum=0,
    )


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv("DDTRADING_CORS_ORIGINS", DEFAULT_FRONTEND_ORIGIN)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or [DEFAULT_FRONTEND_ORIGIN]
