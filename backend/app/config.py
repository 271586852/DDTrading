from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TUSHARE_DAILY_PARQUET_PATH = BACKEND_ROOT / "data" / "tushare_daily.parquet"
DEFAULT_MARKET_DUCKDB_PATH = BACKEND_ROOT / "data" / "market.duckdb"
DEFAULT_FRONTEND_ORIGINS: tuple[str, ...] = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
)
DEFAULT_FRONTEND_ORIGIN = DEFAULT_FRONTEND_ORIGINS[0]
DEFAULT_TUSHARE_MAX_WORKERS = 4
# Tushare 常见 500 次/分钟（多为自然分钟口径）；默认略保守，配合 market_data 内最小间隔限流。
DEFAULT_TUSHARE_MAX_REQUESTS_PER_MINUTE = 420
# 平台文档上限；环境变量不可超过此值（避免误配仍被服务端拒）。
TUSHARE_PLATFORM_MAX_RPM = 500
DEFAULT_DAILY_HISTORY_DAYS = 3650
DEFAULT_DAILY_CACHE_TTL_HOURS = 24
# POST /refresh 成功完成后，在多少小时内直接跳过重复刷新（0 表示不启用）。
DEFAULT_MARKET_REFRESH_COOLDOWN_HOURS = 24


def get_tushare_token() -> str:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise ValueError("TUSHARE_TOKEN is required for Tushare data source.")
    return token


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


def get_tushare_max_workers() -> int:
    return _get_int_env(
        "DDTRADING_TUSHARE_MAX_WORKERS",
        default=DEFAULT_TUSHARE_MAX_WORKERS,
        minimum=1,
    )


def get_tushare_max_requests_per_minute() -> int:
    """Tushare API 每分钟最大请求数（滑动窗口），不超过平台常见 500 上限。"""
    parsed = _get_int_env(
        "DDTRADING_TUSHARE_MAX_REQUESTS_PER_MINUTE",
        default=DEFAULT_TUSHARE_MAX_REQUESTS_PER_MINUTE,
        minimum=1,
    )
    return min(parsed, TUSHARE_PLATFORM_MAX_RPM)


def get_tushare_daily_parquet_path() -> Path:
    """旧 parquet 路径配置，保留给历史脚本兼容；主数据层已迁移到 DuckDB。"""
    raw_path = os.getenv("DDTRADING_TUSHARE_DAILY_PARQUET_PATH")
    if not raw_path:
        return DEFAULT_TUSHARE_DAILY_PARQUET_PATH
    return Path(raw_path).expanduser().resolve()


def get_market_duckdb_path() -> Path:
    """DuckDB 市场数据文件路径。"""
    raw_path = os.getenv("DDTRADING_MARKET_DUCKDB_PATH")
    if not raw_path:
        return DEFAULT_MARKET_DUCKDB_PATH
    return Path(raw_path).expanduser().resolve()


def get_daily_history_days() -> int:
    """本地日线缓存覆盖的历史天数。默认约 10 年。"""
    return _get_int_env(
        "DDTRADING_DAILY_HISTORY_DAYS",
        default=DEFAULT_DAILY_HISTORY_DAYS,
        minimum=30,
    )


def get_daily_cache_ttl_hours() -> int:
    """本地日线 DuckDB 缓存的 TTL（小时）。为 0 表示永不自动刷新，只走 /refresh。"""
    return _get_int_env(
        "DDTRADING_DAILY_CACHE_TTL_HOURS",
        default=DEFAULT_DAILY_CACHE_TTL_HOURS,
        minimum=0,
    )


def get_market_refresh_cooldown_hours() -> int:
    """全市场 POST /refresh 成功后的冷却时间（小时）。为 0 表示每次都会执行刷新逻辑。"""
    return _get_int_env(
        "DDTRADING_MARKET_REFRESH_COOLDOWN_HOURS",
        default=DEFAULT_MARKET_REFRESH_COOLDOWN_HOURS,
        minimum=0,
    )


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv("DDTRADING_CORS_ORIGINS")
    if not raw_origins:
        return list(DEFAULT_FRONTEND_ORIGINS)
    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or list(DEFAULT_FRONTEND_ORIGINS)
