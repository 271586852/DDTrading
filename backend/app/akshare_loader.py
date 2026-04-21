from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import logging
import math
import time
from threading import Lock
from typing import Any

import pandas as pd
import polars as pl

try:
    import akshare as ak
except ImportError:  # pragma: no cover - optional dependency guard
    ak = None


LOGGER = logging.getLogger(__name__)

_CACHE_LOCK = Lock()
_CACHE_DATASET: pl.DataFrame | None = None
_CACHE_EXPIRES_AT = 0.0


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if cleaned in {"", "-", "--", "nan", "None"}:
            return None
        value = cleaned

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None
    return parsed


def _pick_column(frame: pd.DataFrame, candidates: list[str]) -> str:
    for column_name in candidates:
        if column_name in frame.columns:
            return column_name
    raise RuntimeError(
        f"AKShare data missing required columns. candidates={candidates}, got={list(frame.columns)}"
    )


def _extract_candidates(
    spot_frame: pd.DataFrame, universe_size: int
) -> list[dict[str, Any]]:
    code_col = _pick_column(
        spot_frame,
        ["\u4ee3\u7801", "symbol", "\u80a1\u7968\u4ee3\u7801"],
    )
    name_col = _pick_column(
        spot_frame,
        ["\u540d\u79f0", "name", "\u80a1\u7968\u7b80\u79f0"],
    )
    pe_col = _pick_column(
        spot_frame,
        ["\u5e02\u76c8\u7387-\u52a8\u6001", "\u5e02\u76c8\u7387", "pe"],
    )
    market_cap_col = _pick_column(
        spot_frame,
        ["\u603b\u5e02\u503c", "\u6d41\u901a\u5e02\u503c", "market_cap"],
    )

    candidates: list[dict[str, Any]] = []
    for _, row in spot_frame.iterrows():
        symbol_raw = str(row.get(code_col, "")).strip()
        symbol = "".join(ch for ch in symbol_raw if ch.isdigit())
        if len(symbol) != 6:
            continue

        name = str(row.get(name_col, "")).strip() or symbol
        pe_ratio = _to_float(row.get(pe_col))
        market_cap = _to_float(row.get(market_cap_col))
        if pe_ratio is None or market_cap is None:
            continue

        candidates.append(
            {
                "ticker": symbol,
                "name": name,
                "pe_ratio": pe_ratio,
                "market_cap": market_cap,
            }
        )

    candidates.sort(key=lambda item: item["market_cap"], reverse=True)
    return candidates[:universe_size]


def _fetch_single_symbol_factors(
    ticker: str, name: str, pe_ratio: float, history_days: int
) -> dict[str, float | str] | None:
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=history_days)).strftime("%Y%m%d")

    history_frame = ak.stock_zh_a_hist(
        symbol=ticker,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )
    if history_frame is None or history_frame.empty:
        return None

    close_col = _pick_column(history_frame, ["\u6536\u76d8", "close"])
    close_series = pd.to_numeric(history_frame[close_col], errors="coerce").dropna()

    if close_series.shape[0] < 25:
        return None

    momentum_20d = close_series.iloc[-1] / close_series.iloc[-21] - 1.0
    returns = close_series.pct_change().dropna()
    if returns.shape[0] < 20:
        return None

    volatility = returns.tail(20).std(ddof=0)
    if not math.isfinite(momentum_20d) or not math.isfinite(volatility):
        return None

    return {
        "ticker": ticker,
        "name": name,
        "pe_ratio": float(pe_ratio),
        "momentum_20d": float(momentum_20d),
        "volatility": float(volatility),
    }


def _build_dataset(
    universe_size: int,
    history_days: int,
    max_workers: int,
) -> pl.DataFrame:
    if ak is None:
        raise ModuleNotFoundError(
            "AKShare is not installed. Install backend dependencies first: "
            "`python -m pip install -e .`"
        )

    spot_frame = ak.stock_zh_a_spot_em()
    if spot_frame is None or spot_frame.empty:
        raise RuntimeError("AKShare returned empty snapshot data from stock_zh_a_spot_em.")

    candidates = _extract_candidates(spot_frame, universe_size=universe_size)
    if not candidates:
        raise RuntimeError("No valid A-share candidates extracted from AKShare snapshot.")

    rows: list[dict[str, float | str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _fetch_single_symbol_factors,
                candidate["ticker"],
                candidate["name"],
                candidate["pe_ratio"],
                history_days,
            ): candidate["ticker"]
            for candidate in candidates
        }
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - network dependent branch
                LOGGER.warning("AKShare history fetch failed for %s: %s", ticker, exc)
                continue
            if result is not None:
                rows.append(result)

    if not rows:
        raise RuntimeError("AKShare produced zero valid factor rows.")

    dataset = pl.DataFrame(rows).drop_nulls(
        subset=["ticker", "name", "pe_ratio", "momentum_20d", "volatility"]
    )
    if dataset.height == 0:
        raise RuntimeError("AKShare dataset is empty after null filtering.")

    return dataset


def load_akshare_dataset(
    universe_size: int,
    history_days: int,
    max_workers: int,
    cache_ttl_seconds: int,
) -> pl.DataFrame:
    global _CACHE_DATASET
    global _CACHE_EXPIRES_AT

    if cache_ttl_seconds > 0:
        with _CACHE_LOCK:
            if _CACHE_DATASET is not None and time.time() < _CACHE_EXPIRES_AT:
                return _CACHE_DATASET.clone()

    dataset = _build_dataset(
        universe_size=universe_size,
        history_days=history_days,
        max_workers=max_workers,
    )

    if cache_ttl_seconds > 0:
        with _CACHE_LOCK:
            _CACHE_DATASET = dataset
            _CACHE_EXPIRES_AT = time.time() + cache_ttl_seconds

    return dataset.clone()
