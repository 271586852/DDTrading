"""将 DuckDB / Polars 日线转换为 ``app.common.indicators.DailyData`` 列表（择时/战法链路）。"""

from __future__ import annotations

from typing import Any, Dict, List

import polars as pl

from app.common.market_data import _to_ts_code
from app.common.indicators import DailyData


def _trade_date_str(v: Any) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y%m%d")
    return str(v)[:10].replace("-", "")


def daily_data_list_from_polars(
    df: pl.DataFrame,
    *,
    ts_code: str | None = None,
) -> List[DailyData]:
    """把 ``load_daily_for_symbol`` 等返回的日线 Polars 表转为 ``List[DailyData]``（升序）。

    期望列：``date, open, high, low, close, volume``；可选 ``amount``、``pct_chg``。
    """
    if df.height == 0:
        return []
    work = df.with_columns(
        pl.col("date").cast(pl.Datetime(time_unit="ns"), strict=False)
    ).sort("date")
    if ts_code is None:
        if "symbol" not in work.columns:
            raise ValueError("缺少 symbol 列时请显式传入 ts_code=")
        ts_code = _to_ts_code(str(work.get_column("symbol")[0]))

    dates = [_trade_date_str(x) for x in work.get_column("date").to_list()]
    opens = work.get_column("open").cast(pl.Float64).fill_null(0.0).to_list()
    highs = work.get_column("high").cast(pl.Float64).fill_null(0.0).to_list()
    lows = work.get_column("low").cast(pl.Float64).fill_null(0.0).to_list()
    closes = work.get_column("close").cast(pl.Float64).fill_null(0.0).to_list()
    vols = work.get_column("volume").cast(pl.Float64).fill_null(0.0).to_list()

    has_amount = "amount" in work.columns
    amounts = (
        work.get_column("amount").cast(pl.Float64).fill_null(0.0).to_list()
        if has_amount
        else None
    )
    has_pct = "pct_chg" in work.columns
    pcts_in = (
        work.get_column("pct_chg").cast(pl.Float64).fill_null(0.0).to_list()
        if has_pct
        else None
    )

    out: List[DailyData] = []
    for i in range(work.height):
        c = float(closes[i])
        v = float(vols[i])
        prev_close = float(closes[i - 1]) if i > 0 else c
        if has_pct and pcts_in is not None:
            pct = float(pcts_in[i])
        elif prev_close:
            pct = (c - prev_close) / prev_close * 100.0
        else:
            pct = 0.0
        if amounts is not None:
            amt = float(amounts[i])
        else:
            amt = v * c
        out.append(
            DailyData(
                ts_code=ts_code,
                trade_date=str(dates[i]),
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=c,
                vol=v,
                amount=amt,
                pct_chg=pct,
                prev_close=prev_close,
            )
        )
    return out


def bar_dict_rows_from_daily_data(klines: List[DailyData]) -> List[Dict[str, Any]]:
    """战法模块使用的 ``List[Dict]``（含 ``is_rise`` / ``is_beidou`` 等派生字段）。"""
    rows: List[Dict[str, Any]] = []
    for i, k in enumerate(klines):
        prev_close = klines[i - 1].close if i > 0 else k.close
        prev_vol = klines[i - 1].vol if i > 0 else k.vol
        rows.append(
            {
                "ts_code": k.ts_code,
                "trade_date": k.trade_date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "vol": k.vol,
                "amount": k.amount,
                "pct_chg": k.pct_chg,
                "prev_close": prev_close,
                "prev_vol": prev_vol,
                "is_rise": k.close > prev_close,
                "is_beidou": k.vol >= prev_vol * 2 if prev_vol else False,
                "is_suoliang": k.vol <= prev_vol * 0.5 if prev_vol else False,
                "is_jiayin": k.close < k.open and k.close > prev_close,
                "is_yinxian": k.close < prev_close,
                "is_fangliang_yinxian": k.close < prev_close
                and (k.vol > prev_vol * 1.5 if prev_vol else False),
            }
        )
    return rows
