"""评分宽表组装层（Tushare 缓存版）。

从 :mod:`app.market_data` 维护的三张 parquet
（``ashare_daily`` / ``stock_names`` / ``pe_snapshot``）中读取数据，计算出评分
所需的因子（``momentum_20d``、``volatility``），并与静态字段（``name``、
``pe_ratio``）合并成一张宽表：

    ticker / name / pe_ratio / momentum_20d / volatility

该模块不直接联网；数据刷新通过 ``/refresh`` 入口驱动。
"""
from __future__ import annotations

import logging

import pandas as pd
import polars as pl
from akquant import talib as ak_talib

from app.market_data import load_tushare_daily, load_pe_snapshot, load_stock_names


LOGGER = logging.getLogger(__name__)

MOMENTUM_LOOKBACK = 20
VOLATILITY_LOOKBACK = 20


def _compute_latest_factors_from_close(
    close: pd.Series,
    *,
    momentum_lookback: int,
    volatility_lookback: int,
) -> tuple[float, float] | None:
    roc_series = ak_talib.ROC(close, timeperiod=momentum_lookback, as_series=True)
    std_series = ak_talib.STDDEV(
        close,
        timeperiod=volatility_lookback,
        as_series=True,
    )
    sma_series = ak_talib.SMA(
        close,
        timeperiod=volatility_lookback,
        as_series=True,
    )

    momentum_val = pd.to_numeric(roc_series, errors="coerce").iloc[-1]
    std_val = pd.to_numeric(std_series, errors="coerce").iloc[-1]
    sma_val = pd.to_numeric(sma_series, errors="coerce").iloc[-1]
    volatility_val = (
        float(std_val) / float(sma_val)
        if not pd.isna(std_val) and not pd.isna(sma_val) and float(sma_val) != 0.0
        else float("nan")
    )
    if pd.isna(momentum_val) or pd.isna(volatility_val):
        return None
    return float(momentum_val) / 100.0, float(volatility_val)


def compute_latest_factors_from_daily(
    daily: pl.DataFrame,
    *,
    momentum_lookback: int = MOMENTUM_LOOKBACK,
    volatility_lookback: int = VOLATILITY_LOOKBACK,
) -> tuple[float, float] | None:
    if daily.height == 0 or "close" not in daily.columns:
        return None
    close = pd.to_numeric(
        daily.sort("date").select("close").to_pandas()["close"],
        errors="coerce",
    ).dropna()
    min_required = max(momentum_lookback, volatility_lookback) + 1
    if close.shape[0] < min_required:
        return None
    return _compute_latest_factors_from_close(
        close.astype(float).reset_index(drop=True),
        momentum_lookback=momentum_lookback,
        volatility_lookback=volatility_lookback,
    )


def _compute_factors(daily: pl.DataFrame) -> pl.DataFrame:
    """按 symbol 分组计算 momentum_20d 和 volatility（AKQuant 版本）。

    - ``momentum_20d``: ``akquant.talib.ROC(close, 20)`` 最新值（百分比转小数）
    - ``volatility``: ``akquant.talib.STDDEV(close, 20) / SMA(close, 20)`` 最新值
    """
    if daily.height == 0:
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "momentum_20d": pl.Float64,
                "volatility": pl.Float64,
            }
        )

    pdf = (
        daily.sort(["symbol", "date"])
        .select(["symbol", "date", "close"])
        .to_pandas()
    )
    pdf["close"] = pd.to_numeric(pdf["close"], errors="coerce")
    pdf = pdf.dropna(subset=["close"])

    rows: list[dict[str, float | str]] = []
    for symbol, group in pdf.groupby("symbol", sort=False):
        close = group["close"].astype(float).reset_index(drop=True)
        if len(close) <= MOMENTUM_LOOKBACK:
            continue

        factors = _compute_latest_factors_from_close(
            close,
            momentum_lookback=MOMENTUM_LOOKBACK,
            volatility_lookback=VOLATILITY_LOOKBACK,
        )
        if factors is None:
            continue
        momentum_val, volatility_val = factors

        rows.append(
            {
                "symbol": symbol,
                "momentum_20d": momentum_val,
                "volatility": float(volatility_val),
            }
        )

    if not rows:
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "momentum_20d": pl.Float64,
                "volatility": pl.Float64,
            }
        )

    return pl.DataFrame(rows).select(["symbol", "momentum_20d", "volatility"])


def _assemble(
    factors: pl.DataFrame,
    names: pl.DataFrame,
    pe: pl.DataFrame,
    universe_size: int | None,
) -> pl.DataFrame:
    joined = (
        factors.join(pe, on="symbol", how="inner")
        .join(names, on="symbol", how="left")
        .with_columns(pl.col("name").fill_null(pl.col("symbol")))
        .rename({"symbol": "ticker"})
        .select(["ticker", "name", "pe_ratio", "momentum_20d", "volatility"])
        .drop_nulls()
    )

    if universe_size is not None and universe_size > 0 and joined.height > universe_size:
        # 没有市值/成交额列时，按 ticker 字典序截断，保持确定性。
        joined = joined.sort("ticker").head(universe_size)

    return joined


def load_tushare_dataset(
    universe_size: int,
) -> pl.DataFrame:
    """组装评分宽表（纯读 parquet，不联网）。

    若对应 parquet 不存在或已过期，会联网重建；期望常规情况下由
    ``/refresh`` 端点提前触发。
    """
    daily = load_tushare_daily()
    names = load_stock_names()
    pe_snapshot = load_pe_snapshot()

    factors = _compute_factors(daily)
    dataset = _assemble(
        factors=factors,
        names=names,
        pe=pe_snapshot,
        universe_size=universe_size,
    )

    if dataset.height == 0:
        raise RuntimeError(
            "Assembled dataset is empty. Ensure daily/pe/names parquet files "
            "are populated (run POST /refresh first)."
        )

    LOGGER.info(
        "tushare dataset assembled: %d tickers (universe_size=%s)",
        dataset.height,
        universe_size,
    )
    return dataset
