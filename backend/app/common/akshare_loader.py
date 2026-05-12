"""评分宽表组装层（Tushare + DuckDB 缓存版）。

从 :mod:`app.common.market_data` 维护的 DuckDB 表读取日线，计算
``momentum_20d``、``volatility``；可选地与 ``pe_snapshot`` 合并得到
``pe_ratio``。默认输出列：

    ticker / name / pe_ratio / momentum_20d / volatility

当 ``load_tushare_dataset(required_factor_columns=...)`` 不包含 ``pe_ratio``
时，仅输出 ``ticker`` / ``name`` / ``momentum_20d`` / ``volatility``（样本为
有 K 线即参评，不再要求 PE 快照命中）。

该模块不直接联网；数据刷新通过 ``/refresh`` 入口驱动。
"""
from __future__ import annotations

import pandas as pd
import polars as pl

from app.common.market_data import load_tushare_daily, load_pe_snapshot, load_stock_names

MOMENTUM_LOOKBACK = 20
VOLATILITY_LOOKBACK = 20


def _compute_latest_factors_from_close(
    close: pd.Series,
    *,
    momentum_lookback: int,
    volatility_lookback: int,
) -> tuple[float, float] | None:
    clean = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    min_required = max(momentum_lookback, volatility_lookback) + 1
    if clean.shape[0] < min_required:
        return None

    momentum_val = (clean.iloc[-1] / clean.iloc[-momentum_lookback - 1] - 1.0) * 100.0
    window = clean.iloc[-volatility_lookback:]
    std_val = window.std(ddof=0)
    sma_val = window.mean()
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
    """按 symbol 分组计算 momentum_20d 和 volatility。

    - ``momentum_20d``: 近 20 根收盘价涨跌幅
    - ``volatility``: 近 20 根收盘价标准差 / 均值
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
    pe: pl.DataFrame | None,
    *,
    include_pe: bool,
) -> pl.DataFrame:
    base = (
        factors.join(names, on="symbol", how="left")
        .with_columns(pl.col("name").fill_null(pl.col("symbol")))
    )
    if include_pe:
        if pe is None:
            raise ValueError("include_pe=True requires a non-null pe snapshot frame.")
        out = (
            base.join(pe, on="symbol", how="inner")
            .rename({"symbol": "ticker"})
            .select(["ticker", "name", "pe_ratio", "momentum_20d", "volatility"])
        )
        return out.drop_nulls()

    out = (
        base.rename({"symbol": "ticker"})
        .select(["ticker", "name", "momentum_20d", "volatility"])
    )
    return out.drop_nulls()


_DEFAULT_SCORE_FACTORS: frozenset[str] = frozenset(
    {"pe_ratio", "momentum_20d", "volatility"}
)


def load_tushare_dataset(
    *,
    required_factor_columns: frozenset[str] | None = None,
) -> pl.DataFrame:
    """组装评分宽表（优先读 DuckDB 缓存）。

    ``required_factor_columns`` 为 ``None`` 时与旧版一致：内连接 PE，三因子齐全。
    若不包含 ``pe_ratio``，则仅依赖日线因子 + 名称，样本为「有 K 线即参评」。

    若对应本地缓存不存在或已过期，会联网重建；期望常规情况下由
    ``/refresh`` 端点提前触发。
    """
    cols = required_factor_columns or _DEFAULT_SCORE_FACTORS
    unknown = cols - _DEFAULT_SCORE_FACTORS
    if unknown:
        raise ValueError(
            f"required_factor_columns must be a subset of {_DEFAULT_SCORE_FACTORS!r}, "
            f"got extra: {sorted(unknown)}"
        )
    if not cols:
        raise ValueError("required_factor_columns cannot be empty.")
    if not {"momentum_20d", "volatility"}.issubset(cols):
        raise ValueError(
            "required_factor_columns must include 'momentum_20d' and 'volatility' "
            "(both are produced from the daily close pipeline)."
        )

    include_pe = "pe_ratio" in cols
    daily = load_tushare_daily()
    names = load_stock_names()
    pe_snapshot = load_pe_snapshot() if include_pe else None

    factors = _compute_factors(daily)
    dataset = _assemble(
        factors=factors,
        names=names,
        pe=pe_snapshot,
        include_pe=include_pe,
    )

    if dataset.height == 0:
        raise RuntimeError(
            "Assembled dataset is empty. Ensure daily/pe/names DuckDB tables "
            "are populated (run POST /refresh first)."
        )

    return dataset
