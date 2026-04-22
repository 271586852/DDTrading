"""单只股票回测封装。

基于 :mod:`akquant` 运行简单的"有仓则卖、无仓则买" 100 股策略；数据直接取自
:func:`app.market_data.load_ashare_daily` 维护的日线 parquet。主要职责：

- 把用户请求的 ``[start_date, end_date]`` clamp 到该股票在 parquet 里的可用
  区间，避免请求超出数据范围时直接报错。
- 结果中返回核心指标（``BacktestMetrics``），以及最近 100 条交易明细和最近 100
  条持仓快照（时间倒序，方便前端直接展示"最新先"）。
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

import pandas as pd
import polars as pl

from app.market_data import load_ashare_daily
from app.schemas import (
    BacktestDateRange,
    BacktestMetrics,
    BacktestRequest,
    BacktestResponse,
)


LOGGER = logging.getLogger(__name__)

MAX_DETAIL_ROWS = 100


def _to_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    # polars 可能返回 numpy.datetime64 / int64 天数；统一用 pd.Timestamp 兜底
    return pd.Timestamp(value).date()


def _sanitize_value(value: Any) -> Any:
    """把 DataFrame 行转 dict 后的非 JSON 原生类型转为可序列化类型。"""
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        # numpy scalar
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return str(value)
    return value


def _records(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    tail = frame.tail(limit).iloc[::-1]  # 倒序：最新在前
    return [
        {col: _sanitize_value(row[col]) for col in tail.columns}
        for _, row in tail.iterrows()
    ]


def _metric(metrics_df: pd.DataFrame, key: str, caster=float):
    if metrics_df is None or metrics_df.empty or key not in metrics_df.index:
        return None
    raw = metrics_df.loc[key, "value"]
    try:
        if pd.isna(raw):
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        return caster(raw)
    except (TypeError, ValueError):
        return None


class _DefaultBuyHoldFlipStrategy:
    """延迟导入 akquant.Strategy 基类后在运行期动态构造策略子类。"""


def _build_default_strategy_cls():
    from akquant import Strategy

    class _Flip100Strategy(Strategy):
        """最小化默认策略：无仓买 100 股，有仓平 100 股。"""

        def on_bar(self, bar):  # type: ignore[no-untyped-def]
            position = self.get_position(bar.symbol)
            if position == 0:
                self.buy(symbol=bar.symbol, quantity=100)
            elif position > 0:
                self.sell(symbol=bar.symbol, quantity=100)

    return _Flip100Strategy


def _resolve_symbol_window(
    symbol: str,
    start_req: date,
    end_req: date,
) -> tuple[pd.DataFrame, date, date]:
    """读 parquet → 过滤 symbol → clamp 到数据可用区间 → 返回 pandas 子集。"""
    daily = load_ashare_daily()
    sub = daily.filter(pl.col("symbol") == symbol).sort("date")
    if sub.height == 0:
        raise KeyError(
            f"symbol '{symbol}' not found in daily parquet. "
            "Ensure /refresh has been called and the symbol is in the universe."
        )

    data_min = _to_date(sub.select(pl.col("date").min()).item())
    data_max = _to_date(sub.select(pl.col("date").max()).item())

    start_eff = max(start_req, data_min)
    end_eff = min(end_req, data_max)
    if start_eff > end_eff:
        raise ValueError(
            f"requested range [{start_req}, {end_req}] has no overlap with "
            f"available data [{data_min}, {data_max}] for {symbol}."
        )

    start_ts = pd.Timestamp(start_eff)
    end_ts = pd.Timestamp(end_eff)
    window = sub.filter(
        (pl.col("date") >= start_ts) & (pl.col("date") <= end_ts)
    ).to_pandas()

    if len(window) < 2:
        raise ValueError(
            f"not enough bars for backtest after clamp: {len(window)} rows in "
            f"[{start_eff}, {end_eff}] for {symbol}."
        )

    return window, start_eff, end_eff


def run_single_symbol_backtest(
    request: BacktestRequest,
    *,
    commission_rate: float = 0.0003,
) -> BacktestResponse:
    """执行一次单只股票回测并打包为 ``BacktestResponse``。"""
    from akquant import run_backtest

    symbol = request.symbol.zfill(6)

    data, start_eff, end_eff = _resolve_symbol_window(
        symbol=symbol,
        start_req=request.start_date,
        end_req=request.end_date,
    )

    strategy_cls = _build_default_strategy_cls()
    LOGGER.info(
        "running backtest: symbol=%s range=[%s, %s] bars=%d cash=%.2f",
        symbol,
        start_eff,
        end_eff,
        len(data),
        request.initial_cash,
    )

    result = run_backtest(
        strategy=strategy_cls,
        data=data,
        symbols=symbol,
        initial_cash=request.initial_cash,
        commission_rate=commission_rate,
    )

    metrics_df = getattr(result, "metrics_df", pd.DataFrame())
    trades_df = getattr(result, "trades_df", pd.DataFrame())
    positions_df = getattr(result, "positions_df", pd.DataFrame())

    metrics = BacktestMetrics(
        total_return=_metric(metrics_df, "total_return_pct"),
        annualized_return=_metric(metrics_df, "annualized_return"),
        max_drawdown=_metric(metrics_df, "max_drawdown_pct"),
        sharpe_ratio=_metric(metrics_df, "sharpe_ratio"),
        win_rate=_metric(metrics_df, "win_rate"),
        trade_count=_metric(metrics_df, "trade_count", int),
        final_equity=_metric(metrics_df, "end_market_value"),
    )

    return BacktestResponse(
        symbol=symbol,
        requested_range=BacktestDateRange(
            start=request.start_date, end=request.end_date
        ),
        effective_range=BacktestDateRange(start=start_eff, end=end_eff),
        initial_cash=request.initial_cash,
        metrics=metrics,
        recent_trades=_records(trades_df, MAX_DETAIL_ROWS),
        recent_positions=_records(positions_df, MAX_DETAIL_ROWS),
    )
