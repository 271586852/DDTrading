"""单只股票回测封装。

基于 :mod:`akquant` 运行策略；数据取自本地日线 parquet。主要职责：

- 将 ``[start_date, end_date]`` clamp 到可用数据区间。
- 返回指标、权益曲线、**全量**成交明细（时间倒序）与**全量**每日持仓（升序），
  供前端与导出报告内分页展示。
"""
from __future__ import annotations

import html
import logging
import math
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

from app.market_data import load_tushare_daily, refresh_market_data
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
    # 持仓/成交里常见 duration 列，json.dumps 无法序列化 Timedelta
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, pd.Timedelta):
        if pd.isna(value):
            return None
        try:
            return float(value.total_seconds())
        except (ValueError, OverflowError):
            return str(value)
    if isinstance(value, np.timedelta64):
        td = pd.to_timedelta(value, errors="coerce")
        if pd.isna(td):
            return None
        try:
            return float(td.total_seconds())
        except (ValueError, OverflowError, TypeError):
            return str(value)
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        # numpy scalar
        try:
            out = value.item()
        except Exception:  # noqa: BLE001
            return str(value)
        if isinstance(out, (np.timedelta64, pd.Timedelta, timedelta)):
            return _sanitize_value(out)
        if isinstance(out, (datetime, date, pd.Timestamp)):
            return _sanitize_value(out)
        return out
    return value


def _dataframe_records_sanitized(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    records = frame.to_dict(orient="records")
    return [{k: _sanitize_value(v) for k, v in row.items()} for row in records]


def _trades_records_desc(trades_df: pd.DataFrame) -> list[dict[str, Any]]:
    """全部成交，时间倒序（最新在前）。"""
    if trades_df is None or trades_df.empty:
        return []
    return _dataframe_records_sanitized(trades_df.iloc[::-1])


def _positions_records_asc_full(positions_df: pd.DataFrame) -> list[dict[str, Any]]:
    """全部持仓行，按日期/时间列升序。"""
    if positions_df is None or positions_df.empty:
        return []
    sorted_frame = positions_df
    for col in ("date", "timestamp", "time"):
        if col in positions_df.columns:
            sorted_frame = positions_df.sort_values(col)
            break
    return _dataframe_records_sanitized(sorted_frame)


def _deep_scrub_for_json(obj: Any) -> Any:
    """递归清洗，使输出符合 RFC 8259，便于浏览器 ``JSON.parse``（拒绝 NaN/Infinity）。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _deep_scrub_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_deep_scrub_for_json(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (np.integer, np.floating)):
        x = obj.item()
        if isinstance(x, float) and not math.isfinite(x):
            return None
        return x
    if isinstance(obj, (datetime, date, pd.Timestamp, pd.Timedelta, timedelta, np.timedelta64)):
        return _sanitize_value(obj)
    try:
        if obj is pd.NA:
            return None
    except (AttributeError, TypeError):
        pass
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)


REPORT_APPENDIX_PAGE_SIZE = 25


def _html_text(value: Any) -> str:
    if value is None:
        return "--"
    return html.escape(str(value), quote=True)


def _report_fmt_date(value: Any) -> str:
    if value is None:
        return "--"
    text = str(value)
    idx = text.find("T")
    return _html_text(text[:idx] if idx > 0 else text[:10])


def _report_fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "--"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return "--"
        return f"{float(value):.{digits}f}"
    return _html_text(value)


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if not rows:
        return [[]]
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def _report_pager_html(table_id: str, total: int, pages: int) -> str:
    return f"""
  <div class="ddt-pager" data-ddt-pager="{table_id}" style="margin:.75rem 0;display:flex;flex-wrap:wrap;gap:.75rem;align-items:center;font-size:.85rem;">
    <span>共 {total} 条 · 第 <span data-ddt-current="{table_id}">1</span> / {pages} 页</span>
    <button type="button" data-ddt-prev="{table_id}" disabled style="padding:.2rem .6rem;border:1px solid #94a3b8;border-radius:6px;background:#fff;cursor:pointer;">上一页</button>
    <button type="button" data-ddt-next="{table_id}" {'disabled' if pages <= 1 else ''} style="padding:.2rem .6rem;border:1px solid #94a3b8;border-radius:6px;background:#fff;cursor:pointer;">下一页</button>
  </div>"""


def _trades_table_html(trades: list[dict[str, Any]]) -> str:
    pages = _chunked(trades, REPORT_APPENDIX_PAGE_SIZE)
    bodies: list[str] = []
    for page_idx, page_rows in enumerate(pages, start=1):
        body_rows: list[str] = []
        for row in page_rows:
            pnl = row.get("net_pnl", row.get("pnl"))
            return_pct = row.get("return_pct")
            ret = (
                f"{_report_fmt_num(return_pct, 2)}%"
                if return_pct is not None
                else "--"
            )
            body_rows.append(
                "<tr style='border-top:1px solid #e2e8f0;'>"
                f"<td>{_html_text(row.get('side'))}</td>"
                f"<td>{_report_fmt_date(row.get('entry_time'))}</td>"
                f"<td>{_report_fmt_date(row.get('exit_time'))}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('entry_price'), 4)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('exit_price'), 4)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('quantity'), 0)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(pnl, 2)}</td>"
                f"<td style='text-align:right'>{ret}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('duration_bars'), 0)}</td>"
                "</tr>"
            )
        if not body_rows:
            body_rows.append("<tr><td colspan='9' style='padding:1rem;'>无数据</td></tr>")
        display = "" if page_idx == 1 else "display:none;"
        bodies.append(
            f"<tbody data-ddt-table='ddt-trades-table' data-ddt-page='{page_idx}' style='{display}'>"
            + "".join(body_rows)
            + "</tbody>"
        )
    return (
        _report_pager_html("ddt-trades-table", len(trades), len(pages))
        + """
  <div style="overflow:auto;border:1px solid #e2e8f0;border-radius:8px;">
    <table id="ddt-trades-table" style="width:100%;border-collapse:collapse;font-size:.8rem;">
      <thead><tr style="background:#f1f5f9;"><th>方向</th><th>开仓</th><th>平仓</th><th style="text-align:right">开仓价</th><th style="text-align:right">平仓价</th><th style="text-align:right">数量</th><th style="text-align:right">净损益</th><th style="text-align:right">收益率</th><th style="text-align:right">bars</th></tr></thead>
"""
        + "".join(bodies)
        + """
    </table>
  </div>"""
    )


def _positions_table_html(positions: list[dict[str, Any]]) -> str:
    pages = _chunked(positions, REPORT_APPENDIX_PAGE_SIZE)
    bodies: list[str] = []
    for page_idx, page_rows in enumerate(pages, start=1):
        body_rows: list[str] = []
        for row in page_rows:
            date_val = _pick(row, ("date", "timestamp", "time"))
            body_rows.append(
                "<tr style='border-top:1px solid #e2e8f0;'>"
                f"<td>{_report_fmt_date(date_val)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(_pick(row, ('equity', 'market_value')), 2)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('cash'), 2)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('margin'), 2)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(_pick(row, ('positions', 'position_count', 'n_positions')), 0)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('net_exposure'), 2)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('gross_exposure'), 2)}</td>"
                f"<td style='text-align:right'>{_report_fmt_num(row.get('leverage'), 2)}</td>"
                "</tr>"
            )
        if not body_rows:
            body_rows.append("<tr><td colspan='8' style='padding:1rem;'>无数据</td></tr>")
        display = "" if page_idx == 1 else "display:none;"
        bodies.append(
            f"<tbody data-ddt-table='ddt-positions-table' data-ddt-page='{page_idx}' style='{display}'>"
            + "".join(body_rows)
            + "</tbody>"
        )
    return (
        _report_pager_html("ddt-positions-table", len(positions), len(pages))
        + """
  <div style="overflow:auto;border:1px solid #e2e8f0;border-radius:8px;">
    <table id="ddt-positions-table" style="width:100%;border-collapse:collapse;font-size:.8rem;">
      <thead><tr style="background:#f1f5f9;"><th>日期</th><th style="text-align:right">权益</th><th style="text-align:right">现金</th><th style="text-align:right">保证金</th><th style="text-align:right">持仓数</th><th style="text-align:right">净暴露</th><th style="text-align:right">总暴露</th><th style="text-align:right">杠杆</th></tr></thead>
"""
        + "".join(bodies)
        + """
    </table>
  </div>"""
    )


def _report_appendix_html(
    trades: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> str:
    """在 akquant 报告 HTML 末尾追加：成交与持仓分页表（纯 JS + JSON）。"""
    return f"""
<section id="ddt-report-appendix" style="margin:2rem 1rem 4rem;font-family:system-ui,sans-serif;color:#1e293b;">
  <h2 style="font-size:1.1rem;border-bottom:1px solid #cbd5e1;padding-bottom:.5rem;margin-top:2rem;">成交明细（分页）</h2>
  {_trades_table_html(trades)}
  <h2 style="font-size:1.1rem;border-bottom:1px solid #cbd5e1;padding-bottom:.5rem;margin-top:2rem;">每日持仓（分页）</h2>
  {_positions_table_html(positions)}
</section>
<script>
(function () {{
  function initPager(tableId) {{
    var bodies = Array.prototype.slice.call(document.querySelectorAll('tbody[data-ddt-table="' + tableId + '"]'));
    var currentEl = document.querySelector('[data-ddt-current="' + tableId + '"]');
    var prev = document.querySelector('[data-ddt-prev="' + tableId + '"]');
    var next = document.querySelector('[data-ddt-next="' + tableId + '"]');
    if (!bodies.length || !currentEl || !prev || !next) return;
    var page = 1;
    function show(nextPage) {{
      page = Math.min(Math.max(1, nextPage), bodies.length);
      bodies.forEach(function (body, idx) {{ body.style.display = idx + 1 === page ? "" : "none"; }});
      currentEl.textContent = String(page);
      prev.disabled = page <= 1;
      next.disabled = page >= bodies.length;
    }}
    prev.addEventListener("click", function () {{ show(page - 1); }});
    next.addEventListener("click", function () {{ show(page + 1); }});
    show(1);
  }}
  initPager("ddt-trades-table");
  initPager("ddt-positions-table");
}})();
</script>
</div>
"""


def _inject_before_body_close(html: str, fragment: str) -> str:
    lower = html.lower()
    idx = lower.rfind("</body>")
    if idx == -1:
        return html + fragment
    return html[:idx] + fragment + html[idx:]


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
    daily = load_tushare_daily()
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


def _ensure_backtest_window_cached(symbol: str, start_req: date, end_req: date) -> None:
    """本地优先；若区间不完整则先做增量更新再回测。"""
    t_load = time.perf_counter()
    daily = load_tushare_daily()
    load_ms = (time.perf_counter() - t_load) * 1000
    sub = daily.filter(pl.col("symbol") == symbol).sort("date")
    if sub.height == 0:
        LOGGER.info(
            "backtest ensure_cache: symbol=%s absent in parquet load_ms=%.1f -> incremental refresh",
            symbol,
            load_ms,
        )
        t_ref = time.perf_counter()
        refresh_market_data(mode="incremental", force=True)
        LOGGER.info(
            "backtest ensure_cache: refresh_market_data done refresh_ms=%.1f",
            (time.perf_counter() - t_ref) * 1000,
        )
        return

    data_min = _to_date(sub.select(pl.col("date").min()).item())
    data_max = _to_date(sub.select(pl.col("date").max()).item())
    if data_min > start_req or data_max < end_req:
        LOGGER.info(
            "backtest ensure_cache: symbol=%s req=[%s,%s] parquet=[%s,%s] load_ms=%.1f -> incremental refresh",
            symbol,
            start_req,
            end_req,
            data_min,
            data_max,
            load_ms,
        )
        t_ref = time.perf_counter()
        refresh_market_data(mode="incremental", force=True)
        LOGGER.info(
            "backtest ensure_cache: refresh_market_data done refresh_ms=%.1f",
            (time.perf_counter() - t_ref) * 1000,
        )


def run_single_symbol_backtest(
    request: BacktestRequest,
    *,
    commission_rate: float = 0.0003,
) -> BacktestResponse:
    """执行一次单只股票回测并打包为 ``BacktestResponse``。"""
    from akquant import run_backtest

    t_total = time.perf_counter()
    symbol = request.symbol.zfill(6)

    t0 = time.perf_counter()
    _ensure_backtest_window_cached(symbol, request.start_date, request.end_date)
    ensure_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    data, start_eff, end_eff = _resolve_symbol_window(
        symbol=symbol,
        start_req=request.start_date,
        end_req=request.end_date,
    )
    resolve_ms = (time.perf_counter() - t0) * 1000

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

    t0 = time.perf_counter()
    result = run_backtest(
        strategy=strategy_cls,
        data=data,
        symbols=symbol,
        initial_cash=request.initial_cash,
        commission_rate=commission_rate,
    )
    akquant_ms = (time.perf_counter() - t0) * 1000

    metrics_df = getattr(result, "metrics_df", pd.DataFrame())
    trades_df = getattr(result, "trades_df", pd.DataFrame())
    positions_df = getattr(result, "positions_df", pd.DataFrame())
    equity_series = getattr(result, "equity_curve", None)

    t0 = time.perf_counter()
    metrics = BacktestMetrics(
        total_return=_metric(metrics_df, "total_return_pct"),
        annualized_return=_metric(metrics_df, "annualized_return"),
        max_drawdown=_metric(metrics_df, "max_drawdown_pct"),
        sharpe_ratio=_metric(metrics_df, "sharpe_ratio"),
        win_rate=_metric(metrics_df, "win_rate"),
        trade_count=_metric(metrics_df, "trade_count", int),
        final_equity=_metric(metrics_df, "end_market_value"),
    )

    response = BacktestResponse(
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
        recent_trades=_trades_records_desc(trades_df),
        recent_positions=[],
        daily_positions=_positions_records_asc_full(positions_df),
    )
    pack_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - t_total) * 1000

    LOGGER.info(
        "backtest timing: symbol=%s strategy=%s bars=%d trades=%d positions=%d "
        "ensure_ms=%.1f resolve_ms=%.1f akquant_ms=%.1f pack_ms=%.1f total_ms=%.1f",
        symbol,
        spec.id,
        len(data),
        len(trades_df),
        len(positions_df),
        ensure_ms,
        resolve_ms,
        akquant_ms,
        pack_ms,
        total_ms,
    )

    return response


def export_single_symbol_backtest_report(
    request: BacktestReportRequest,
    *,
    commission_rate: float = 0.0003,
) -> str:
    """执行回测并导出 HTML 报告内容。"""
    from akquant import run_backtest

    t_total = time.perf_counter()
    symbol = request.symbol.zfill(6)

    t0 = time.perf_counter()
    _ensure_backtest_window_cached(symbol, request.start_date, request.end_date)
    data, start_eff, end_eff = _resolve_symbol_window(
        symbol=symbol,
        start_req=request.start_date,
        end_req=request.end_date,
    )
    prepare_ms = (time.perf_counter() - t0) * 1000

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

    t0 = time.perf_counter()
    result = run_backtest(
        strategy=strategy_cls,
        data=data,
        symbols=symbol,
        initial_cash=request.initial_cash,
        commission_rate=commission_rate,
    )
    akquant_ms = (time.perf_counter() - t0) * 1000

    default_title = (
        f"{symbol} {spec.name} 回测报告 "
        f"({start_eff.isoformat()} ~ {end_eff.isoformat()})"
    )
    report_title = request.title or default_title

    # 须在 result.report() 之前取明细：部分版本在出图后可能释放/变更底层缓存。
    t0 = time.perf_counter()
    trades_df = getattr(result, "trades_df", pd.DataFrame())
    positions_df = getattr(result, "positions_df", pd.DataFrame())
    trade_records = _trades_records_desc(trades_df)
    position_records = _positions_records_asc_full(positions_df)
    records_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ddtrading-report-") as tmpdir:
        out_path = Path(tmpdir) / "backtest_report.html"
        result.report(
            title=report_title,
            filename=str(out_path),
            show=False,
            compact_currency=True,
            curve_freq=request.curve_freq,
        )
        html = out_path.read_text(encoding="utf-8")
        appendix = _report_appendix_html(trade_records, position_records)
        merged = _inject_before_body_close(html, appendix)
    report_html_ms = (time.perf_counter() - t0) * 1000
    total_ms = (time.perf_counter() - t_total) * 1000

    LOGGER.info(
        "backtest report timing: symbol=%s strategy=%s bars=%d trades=%d positions=%d "
        "prepare_ms=%.1f akquant_ms=%.1f records_ms=%.1f report_html_ms=%.1f total_ms=%.1f",
        symbol,
        spec.id,
        len(data),
        len(trades_df),
        len(positions_df),
        prepare_ms,
        akquant_ms,
        records_ms,
        report_html_ms,
        total_ms,
    )

    return merged
