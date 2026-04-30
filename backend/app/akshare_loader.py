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

import polars as pl

from app.market_data import load_ashare_daily, load_pe_snapshot, load_stock_names


LOGGER = logging.getLogger(__name__)

MOMENTUM_LOOKBACK = 20
VOLATILITY_LOOKBACK = 20


def _compute_factors(daily: pl.DataFrame) -> pl.DataFrame:
    """按 symbol 分组计算 momentum_20d 和 volatility。

    - ``momentum_20d``: 最新收盘价 / 20 交易日前收盘价 - 1
    - ``volatility``: 最近 20 个日收益率的总体标准差
    """
    if daily.height == 0:
        return pl.DataFrame(
            schema={
                "symbol": pl.Utf8,
                "momentum_20d": pl.Float64,
                "volatility": pl.Float64,
            }
        )

    prepared = daily.sort(["symbol", "date"]).with_columns(
        pl.col("close").pct_change().over("symbol").alias("daily_return")
    )

    factors = prepared.group_by("symbol", maintain_order=True).agg(
        [
            pl.col("close").last().alias("close_last"),
            pl.col("close").shift(MOMENTUM_LOOKBACK).last().alias("close_base"),
            pl.col("daily_return").tail(VOLATILITY_LOOKBACK).std(ddof=0).alias("volatility"),
            pl.col("daily_return").drop_nulls().count().alias("valid_returns"),
        ]
    )

    factors = factors.with_columns(
        (pl.col("close_last") / pl.col("close_base") - 1.0).alias("momentum_20d")
    )

    factors = factors.filter(
        pl.col("close_base").is_not_null()
        & pl.col("volatility").is_not_null()
        & (pl.col("valid_returns") >= VOLATILITY_LOOKBACK)
    )

    return factors.select(["symbol", "momentum_20d", "volatility"])


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
    history_days: int | None = None,  # 保留签名兼容，不再生效
    max_workers: int | None = None,   # 保留签名兼容，不再生效
    cache_ttl_seconds: int | None = None,  # 保留签名兼容，不再生效
) -> pl.DataFrame:
    """组装评分宽表（纯读 parquet，不联网）。

    若对应 parquet 不存在或已过期，会联网重建；期望常规情况下由
    ``/refresh`` 端点提前触发。
    """
    del history_days, max_workers, cache_ttl_seconds  # 仅为了签名兼容

    daily = load_ashare_daily()
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


# Backward-compatible alias.
def load_akshare_dataset(
    universe_size: int,
    history_days: int | None = None,
    max_workers: int | None = None,
    cache_ttl_seconds: int | None = None,
) -> pl.DataFrame:
    return load_tushare_dataset(
        universe_size=universe_size,
        history_days=history_days,
        max_workers=max_workers,
        cache_ttl_seconds=cache_ttl_seconds,
    )
