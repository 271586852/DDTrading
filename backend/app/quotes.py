"""单只代码的报价 / 近期 K 线读取层。

纯 parquet 消费者：从 ``ashare_daily.parquet`` + ``stock_names.parquet`` 取数，
不联网。用于前端主分析卡展示价格、涨跌幅、最近 N 根 K 线。

- 代码未落在缓存中 → ``KeyError``（API 层映射 404）。
- 代码格式非法 → ``ValueError``（API 层映射 400）。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import polars as pl

from app.config import get_baostock_daily_parquet_path
from app.market_data import (
    _is_etf_symbol,
    _is_stock_symbol,
    _normalize_symbol,
    ensure_symbol_cached,
)


DEFAULT_HISTORY_BARS = 120


def _resolve_name(symbol: str) -> str | None:
    path = get_baostock_daily_parquet_path().parent / "stock_names.parquet"
    if not path.exists():
        return None
    try:
        names = pl.read_parquet(path)
    except Exception:  # noqa: BLE001  - 名称缺失不是致命错误
        return None

    matched = names.filter(pl.col("symbol") == symbol)
    if matched.height == 0:
        return None
    value = matched["name"].to_list()[0]
    return str(value) if value else None


def _classify(symbol: str) -> str:
    if _is_stock_symbol(symbol):
        return "stock"
    if _is_etf_symbol(symbol):
        return "etf"
    return "unknown"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return str(value)[:10]
    except Exception:  # noqa: BLE001
        return None


def fetch_quote(symbol: str, *, bars: int = DEFAULT_HISTORY_BARS) -> dict[str, Any]:
    """从本地 parquet 取单只标的的报价快照 + 近期 K 线。

    返回结构：
    ``{"symbol", "name", "kind", "latest_close", "prev_close", "change_pct",
       "as_of_date", "history": [{"date", "open", "high", "low", "close", "volume"}...]}``

    ``kind`` 为 ``'stock' | 'etf' | 'unknown'``；便于前端判断是否禁用评分按钮。
    """
    normalized = _normalize_symbol(symbol)

    path = get_baostock_daily_parquet_path()
    if path.exists():
        daily = pl.read_parquet(path)
    else:
        daily = pl.DataFrame(
            schema={
                "date": pl.Datetime,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Float64,
                "symbol": pl.Utf8,
            }
        )

    sliced = (
        daily.filter(pl.col("symbol") == normalized)
        .sort("date")
        .tail(max(bars, 2))
    )
    if sliced.height == 0 and _is_stock_symbol(normalized) and not _is_etf_symbol(normalized):
        ensure_symbol_cached(normalized)
        daily = pl.read_parquet(path)
        sliced = (
            daily.filter(pl.col("symbol") == normalized)
            .sort("date")
            .tail(max(bars, 2))
        )

    if sliced.height == 0:
        raise KeyError(
            f"Symbol '{normalized}' has no daily bars in the parquet cache. "
            "Please POST /refresh first."
        )

    rows = list(sliced.iter_rows(named=True))
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else None

    latest_close = _safe_float(latest.get("close"))
    prev_close = _safe_float(prev["close"]) if prev is not None else None

    change_pct: float | None = None
    if latest_close is not None and prev_close not in (None, 0):
        change_pct = round((latest_close - prev_close) / prev_close * 100.0, 4)

    history: list[dict[str, Any]] = []
    for row in rows:
        history.append(
            {
                "date": _iso_date(row.get("date")),
                "open": _safe_float(row.get("open")),
                "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")),
                "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume")),
            }
        )

    return {
        "symbol": normalized,
        "name": _resolve_name(normalized),
        "kind": _classify(normalized),
        "latest_close": latest_close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "as_of_date": _iso_date(latest.get("date")),
        "bars": len(history),
        "history": history,
    }
