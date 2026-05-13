from __future__ import annotations

from typing import Any, Callable, Dict, List

import polars as pl

from app.common.market_data import get_market_data_cache_revision
from app.schemas import ScoreRequest
from app.score.score_strategies import (
    ScoringStrategy,
    get_strategy,
    get_strategy_lookback_days,
)

ProgressFn = Callable[[int, str], None]


def _resolve_score_engine(strategy: ScoringStrategy) -> str:
    """由策略元数据解析评分引擎；未知引擎给出可操作的错误说明。"""
    eng = (strategy.score_engine or "").strip()
    if not eng:
        raise ValueError(
            f"策略 {strategy.id!r} 未配置 score_engine。"
            "请在 ScoringStrategy 中设置 score_engine，并在评分服务注册表中登记实现。"
        )
    if eng not in _MARKET_RUNNERS or eng not in _SINGLE_RUNNERS:
        known = sorted(set(_MARKET_RUNNERS) & set(_SINGLE_RUNNERS))
        raise ValueError(
            f"策略 {strategy.id!r} 的 score_engine={eng!r} 尚未在评分服务中实现。"
            f"当前已注册引擎: {', '.join(known)}。"
        )
    return eng


def _finalize_score_payload(d: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = dict(d)
    out["market_data_revision"] = get_market_data_cache_revision()
    return out


def _report_progress(cb: ProgressFn | None, pct: int, msg: str) -> None:
    if cb is None:
        return
    cb(max(0, min(100, int(pct))), msg)


def _required_fetch_days(lookback_days: int) -> int:
    return max(lookback_days * 3, 120)


def _applied_strategy_view(strategy: ScoringStrategy) -> dict[str, object]:
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "score_engine": strategy.score_engine,
        "factor_keys": list(strategy.factor_keys),
        "factor_fields": [
            {
                "key": f.key,
                "label": f.label,
                "value_format": f.value_format,
                "zscore_orientation": f.zscore_orientation,
            }
            for f in strategy.factor_fields
        ],
    }


def _normalize_ticker_input(symbol: str) -> str:
    from app.common.market_data import _normalize_symbol

    return _normalize_symbol(symbol)


def _display_name_for_symbol(symbol: str) -> str:
    from app.common.market_data import load_stock_names

    names = load_stock_names()
    m = names.filter(pl.col("symbol") == symbol)
    if m.height == 0:
        return symbol
    cell = m.select(pl.col("name").last()).item()
    return str(cell) if cell is not None else symbol


def _pattern_score_from_analysis(out: dict) -> tuple[float, Dict[str, float]]:
    n_sig = int(out["total_signals"])
    latest = out["latest_signal"]
    base = 35.0
    if latest is not None and getattr(latest, "action", "") == "BUY":
        total_score = min(100.0, base + float(latest.confidence) * 55.0)
    else:
        total_score = min(100.0, base + min(n_sig, 12) * 2.2)
    conf = (
        float(getattr(latest, "confidence", 0.0) or 0.0)
        if latest is not None
        else 0.0
    )
    breakdown = {
        "pattern_signal_count": float(n_sig),
        "latest_confidence": conf,
    }
    return round(total_score, 2), breakdown


def _score_zettaranc_composite_single(
    symbol: str, *, lookback_days: int
) -> dict[str, object]:
    from app.common.market_data import _to_ts_code
    from app.common.market_repository import load_daily_for_symbol
    from app.score.score_strategies.zettaranc_screener import (
        analyze_screener_stock,
        daily_data_list_from_polars,
    )

    df = load_daily_for_symbol(symbol).sort("date")
    if df.height < 30:
        raise ValueError(
            f"该评分引擎需要至少 30 根日线: '{symbol}'，当前 {df.height} 根。"
        )
    need = max(60, lookback_days)
    tail = df.tail(min(df.height, need))
    ts = _to_ts_code(symbol)
    dd = daily_data_list_from_polars(tail, ts_code=ts)
    stock = analyze_screener_stock(ts, dd, name=_display_name_for_symbol(symbol))
    breakdown = {
        "b1_opportunity": float(stock.b1_score),
        "trend": float(stock.trend_score),
        "volume_pattern": float(stock.volume_score),
        "risk": float(stock.risk_score),
    }
    row = {
        "rank": 1,
        "ticker": symbol,
        "name": stock.name,
        "total_score": float(stock.score),
        "factor_values": breakdown,
        "factor_zscores": breakdown,
    }
    return {
        "total_universe": 1,
        "returned_count": 1,
        "mode": "single",
        "top_50": [row],
    }


def _score_zettaranc_patterns_single(
    symbol: str, *, lookback_days: int
) -> dict[str, object]:
    from app.common.market_data import _to_ts_code
    from app.common.market_repository import load_daily_for_symbol
    from app.common.indicators import analyze_with_strategies_from_klines
    from app.score.score_strategies.zettaranc_screener import daily_data_list_from_polars

    df = load_daily_for_symbol(symbol).sort("date")
    if df.height < 30:
        raise ValueError(
            f"该评分引擎需要至少 30 根日线: '{symbol}'，当前 {df.height} 根。"
        )
    need = max(60, lookback_days)
    tail = df.tail(min(df.height, need))
    ts = _to_ts_code(symbol)
    dd = daily_data_list_from_polars(tail, ts_code=ts)
    out = analyze_with_strategies_from_klines(ts, dd)
    total_score, breakdown = _pattern_score_from_analysis(out)
    name = _display_name_for_symbol(symbol)
    row = {
        "rank": 1,
        "ticker": symbol,
        "name": name,
        "total_score": total_score,
        "factor_values": breakdown,
        "factor_zscores": breakdown,
    }
    return {
        "total_universe": 1,
        "returned_count": 1,
        "mode": "single",
        "top_50": [row],
    }


def _name_map_from_repository() -> dict[str, str]:
    from app.common.market_repository import load_names

    n = load_names()
    if n.height == 0:
        return {}
    syms = n.get_column("symbol").to_list()
    names = n.get_column("name").to_list()
    return {str(s): str(nm) if nm is not None else str(s) for s, nm in zip(syms, names)}


def _score_market_zettaranc_composite(
    *,
    top_n: int,
    lookback_days: int,
    progress: ProgressFn | None,
) -> dict[str, object]:
    from app.common.market_data import _to_ts_code
    from app.common.market_repository import load_daily
    from app.score.score_strategies.zettaranc_screener import (
        analyze_screener_stock,
        daily_data_list_from_polars,
    )

    daily = load_daily()
    if daily.height == 0:
        raise ValueError("本地 DuckDB 无日线数据，请先执行行情同步。")

    name_map = _name_map_from_repository()
    need = max(60, lookback_days)
    rows: List[dict[str, object]] = []
    chunks = daily.sort(["symbol", "date"]).partition_by("symbol", as_dict=True)
    symbols_seq = sorted(chunks.keys(), key=lambda t: str(t[0]) if t else "")
    total = len(symbols_seq)

    for i, sym_tuple in enumerate(symbols_seq):
        one = chunks[sym_tuple]
        sym = str(sym_tuple[0]) if sym_tuple else ""
        if (i & 0x3F) == 0 and total:
            pct = 10 + int(85 * i / total)
            _report_progress(progress, pct, f"四维评分 {i + 1}/{total}…")

        if one.height < 30:
            continue
        tail = one.tail(min(one.height, need))
        ts = _to_ts_code(sym)
        dd = daily_data_list_from_polars(tail, ts_code=ts)
        display = name_map.get(sym, sym)
        stock = analyze_screener_stock(ts, dd, name=display)
        breakdown = {
            "b1_opportunity": float(stock.b1_score),
            "trend": float(stock.trend_score),
            "volume_pattern": float(stock.volume_score),
            "risk": float(stock.risk_score),
        }
        rows.append(
            {
                "ticker": sym,
                "name": stock.name,
                "total_score": float(stock.score),
                "factor_values": breakdown,
                "factor_zscores": breakdown,
            }
        )

    rows.sort(key=lambda r: float(r["total_score"]), reverse=True)
    top = rows[: max(1, top_n)]
    for idx, r in enumerate(top, start=1):
        r["rank"] = idx

    _report_progress(progress, 98, "汇总全市场排名…")
    return {
        "total_universe": len(rows),
        "returned_count": len(top),
        "mode": "market",
        "top_50": top,
    }


def _score_market_zettaranc_patterns(
    *,
    top_n: int,
    lookback_days: int,
    progress: ProgressFn | None,
) -> dict[str, object]:
    from app.common.market_data import _to_ts_code
    from app.common.market_repository import load_daily
    from app.common.indicators import analyze_with_strategies_from_klines
    from app.score.score_strategies.zettaranc_screener import daily_data_list_from_polars

    daily = load_daily()
    if daily.height == 0:
        raise ValueError("本地 DuckDB 无日线数据，请先执行行情同步。")

    name_map = _name_map_from_repository()
    need = max(60, lookback_days)
    rows: List[dict[str, object]] = []
    chunks = daily.sort(["symbol", "date"]).partition_by("symbol", as_dict=True)
    symbols_seq = sorted(chunks.keys(), key=lambda t: str(t[0]) if t else "")
    total = len(symbols_seq)

    for i, sym_tuple in enumerate(symbols_seq):
        one = chunks[sym_tuple]
        sym = str(sym_tuple[0]) if sym_tuple else ""
        if (i & 0x3F) == 0 and total:
            pct = 10 + int(85 * i / total)
            _report_progress(progress, pct, f"战法信号评分 {i + 1}/{total}…")

        if one.height < 30:
            continue
        tail = one.tail(min(one.height, need))
        ts = _to_ts_code(sym)
        dd = daily_data_list_from_polars(tail, ts_code=ts)
        out = analyze_with_strategies_from_klines(ts, dd)
        total_score, breakdown = _pattern_score_from_analysis(out)
        display = name_map.get(sym, sym)
        rows.append(
            {
                "ticker": sym,
                "name": display,
                "total_score": total_score,
                "factor_values": breakdown,
                "factor_zscores": breakdown,
            }
        )

    rows.sort(key=lambda r: float(r["total_score"]), reverse=True)
    top = rows[: max(1, top_n)]
    for idx, r in enumerate(top, start=1):
        r["rank"] = idx

    _report_progress(progress, 98, "汇总全市场排名…")
    return {
        "total_universe": len(rows),
        "returned_count": len(top),
        "mode": "market",
        "top_50": top,
    }


def score_stocks(
    payload: ScoreRequest,
    top_n: int = 50,
    *,
    progress: ProgressFn | None = None,
) -> Dict[str, object]:
    strategy_id = (payload.strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("strategy_id 为必选，请从 GET /score-strategies 选择策略。")

    applied_strategy = get_strategy(strategy_id)
    engine = _resolve_score_engine(applied_strategy)

    target_symbol = (payload.symbol or "").strip()
    lookback_days = get_strategy_lookback_days(payload.strategy_id)

    _report_progress(progress, 1, "准备评分…")

    if not target_symbol:
        _report_progress(progress, 5, "全市场扫描（仅本地 DuckDB）…")
        result = _MARKET_RUNNERS[engine](
            top_n=top_n,
            lookback_days=lookback_days,
            progress=progress,
        )
        result["applied_strategy"] = _applied_strategy_view(applied_strategy)
        _report_progress(progress, 100, "完成")
        return _finalize_score_payload(result)

    _report_progress(progress, 8, "单股评分…")
    normalized = _normalize_ticker_input(target_symbol)
    from app.common.market_data import ensure_symbol_cached

    ensure_symbol_cached(
        normalized,
        days=_required_fetch_days(lookback_days),
    )
    _report_progress(progress, 40, "策略计算…")
    result = _SINGLE_RUNNERS[engine](
        normalized,
        lookback_days=lookback_days,
    )
    result["applied_strategy"] = _applied_strategy_view(applied_strategy)
    _report_progress(progress, 100, "完成")
    return _finalize_score_payload(result)


_MARKET_RUNNERS: Dict[str, Callable[..., Dict[str, object]]] = {
    "zettaranc_composite": _score_market_zettaranc_composite,
    "zettaranc_patterns": _score_market_zettaranc_patterns,
}
_SINGLE_RUNNERS: Dict[str, Callable[..., Dict[str, object]]] = {
    "zettaranc_composite": _score_zettaranc_composite_single,
    "zettaranc_patterns": _score_zettaranc_patterns_single,
}
