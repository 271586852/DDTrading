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
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from app.market_data import load_ashare_daily
from app.schemas import (
    BacktestDateRange,
    BacktestMetrics,
    BacktestRequest,
    BacktestReportRequest,
    BacktestResponse,
    EquityPoint,
    PricePoint,
    TradeMarker,
    TradeStrategyInfo,
)
from app.trade_strategies import (
    DEFAULT_TRADE_STRATEGY_ID,
    TradeStrategySpec,
    get_trade_strategy,
)


LOGGER = logging.getLogger(__name__)

MAX_DETAIL_ROWS = 100
MAX_DAILY_POSITION_ROWS = 2000


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


def _records_asc(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    """按时间升序取最近 N 行，便于展示每日持仓明细。"""
    if frame is None or frame.empty:
        return []
    sorted_frame = frame
    for col in ("date", "timestamp", "time"):
        if col in frame.columns:
            sorted_frame = frame.sort_values(col)
            break
    tail = sorted_frame.tail(limit)
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


def _resolve_trade_strategy(strategy_id: str | None) -> TradeStrategySpec:
    return get_trade_strategy(strategy_id or DEFAULT_TRADE_STRATEGY_ID)


def _coerce_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:  # noqa: BLE001
        return None


def _equity_curve_points(series: Any) -> list[EquityPoint]:
    """把 akquant 返回的 equity series 转成前端可绘制的 (date, equity, drawdown%)。"""
    if series is None or len(series) == 0:
        return []

    try:
        frame = series.to_frame(name="equity").reset_index()
    except Exception:  # noqa: BLE001
        return []

    timestamp_col = frame.columns[0]
    frame[timestamp_col] = pd.to_datetime(frame[timestamp_col], errors="coerce")
    frame = frame.dropna(subset=[timestamp_col, "equity"])
    if frame.empty:
        return []

    frame = frame.sort_values(timestamp_col)
    running_peak = frame["equity"].cummax()
    drawdown_pct = ((running_peak - frame["equity"]) / running_peak * 100).fillna(0.0)

    points: list[EquityPoint] = []
    for ts, equity, dd in zip(
        frame[timestamp_col].tolist(),
        frame["equity"].tolist(),
        drawdown_pct.tolist(),
    ):
        iso = _coerce_iso_date(ts)
        if iso is None or not math.isfinite(float(equity)):
            continue
        points.append(
            EquityPoint(
                date=iso,
                equity=float(equity),
                drawdown_pct=float(dd) if math.isfinite(float(dd)) else 0.0,
            )
        )
    return points


def _price_series_points(data: pd.DataFrame) -> list[PricePoint]:
    if data is None or data.empty or "date" not in data.columns:
        return []
    points: list[PricePoint] = []
    for _, row in data.iterrows():
        iso = _coerce_iso_date(row.get("date"))
        if iso is None:
            continue
        close = row.get("close")
        close_val = float(close) if close is not None and pd.notna(close) else None
        points.append(PricePoint(date=iso, close=close_val))
    return points


def _trade_markers(trades_df: pd.DataFrame) -> list[TradeMarker]:
    """把 akquant trades_df 展开成独立的买/卖点标记。"""
    if trades_df is None or trades_df.empty:
        return []

    markers: list[TradeMarker] = []
    for _, row in trades_df.iterrows():
        side_raw = str(row.get("side", "")).lower()
        is_short = side_raw == "short"
        entry_side = "sell" if is_short else "buy"
        exit_side = "buy" if is_short else "sell"

        entry_date = _coerce_iso_date(row.get("entry_time"))
        if entry_date is not None:
            entry_price = row.get("entry_price")
            markers.append(
                TradeMarker(
                    date=entry_date,
                    price=float(entry_price)
                    if entry_price is not None and pd.notna(entry_price)
                    else None,
                    side=entry_side,
                    quantity=float(row.get("quantity"))
                    if pd.notna(row.get("quantity"))
                    else None,
                )
            )

        exit_date = _coerce_iso_date(row.get("exit_time"))
        if exit_date is not None:
            exit_price = row.get("exit_price")
            pnl = row.get("net_pnl")
            markers.append(
                TradeMarker(
                    date=exit_date,
                    price=float(exit_price)
                    if exit_price is not None and pd.notna(exit_price)
                    else None,
                    side=exit_side,
                    quantity=float(row.get("quantity"))
                    if pd.notna(row.get("quantity"))
                    else None,
                    pnl=float(pnl) if pnl is not None and pd.notna(pnl) else None,
                )
            )

    markers.sort(key=lambda m: m.date)
    return markers


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

    spec = _resolve_trade_strategy(request.strategy_id)
    strategy_cls = spec.build_cls()
    LOGGER.info(
        "running backtest: symbol=%s strategy=%s range=[%s, %s] bars=%d cash=%.2f",
        symbol,
        spec.id,
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
    equity_series = getattr(result, "equity_curve", None)

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
        applied_strategy=TradeStrategyInfo(
            id=spec.id, name=spec.name, description=spec.description
        ),
        equity_curve=_equity_curve_points(equity_series),
        price_series=_price_series_points(data),
        trade_markers=_trade_markers(trades_df),
        recent_trades=_records(trades_df, MAX_DETAIL_ROWS),
        recent_positions=_records(positions_df, MAX_DETAIL_ROWS),
        daily_positions=_records_asc(positions_df, MAX_DAILY_POSITION_ROWS),
    )


def export_single_symbol_backtest_report(
    request: BacktestReportRequest,
    *,
    commission_rate: float = 0.0003,
) -> str:
    """执行回测并导出 HTML 报告内容。"""
    from akquant import run_backtest

    symbol = request.symbol.zfill(6)
    data, start_eff, end_eff = _resolve_symbol_window(
        symbol=symbol,
        start_req=request.start_date,
        end_req=request.end_date,
    )
    spec = _resolve_trade_strategy(request.strategy_id)
    strategy_cls = spec.build_cls()

    LOGGER.info(
        "export report: symbol=%s strategy=%s range=[%s, %s] bars=%d cash=%.2f curve_freq=%s",
        symbol,
        spec.id,
        start_eff,
        end_eff,
        len(data),
        request.initial_cash,
        request.curve_freq,
    )

    result = run_backtest(
        strategy=strategy_cls,
        data=data,
        symbols=symbol,
        initial_cash=request.initial_cash,
        commission_rate=commission_rate,
    )

    default_title = (
        f"{symbol} {spec.name} 回测报告 "
        f"({start_eff.isoformat()} ~ {end_eff.isoformat()})"
    )
    report_title = request.title or default_title

    with tempfile.TemporaryDirectory(prefix="ddtrading-report-") as tmpdir:
        out_path = Path(tmpdir) / "backtest_report.html"
        result.report(
            title=report_title,
            filename=str(out_path),
            show=False,
            compact_currency=True,
            curve_freq=request.curve_freq,
        )
        return out_path.read_text(encoding="utf-8")
