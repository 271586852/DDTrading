"""Z 哥风格 B1 触发：出现 B1 信号时买入，止损 / 止盈后平仓。"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import polars as pl

from app.backtest.backtest_strategies.spec import TradeStrategySpec
from app.common.market_data import _to_ts_code
from app.contrib.zettaranc.adapter import bar_dict_rows_from_daily_data, daily_data_list_from_polars
from app.contrib.zettaranc.strategies import detect_b1

_OHLCV_COLS = ("date", "open", "high", "low", "close", "volume")


def _ohlcv_window(n: int, freq: str, security: str) -> pd.DataFrame:
    """用多次 ``get_history`` 拼出与单表 OHLCV 等价的窗口（列名与 DuckDB 日线一致）。"""
    cols: dict[str, pd.Series] = {c: get_history(n, freq, c, security)[c] for c in _OHLCV_COLS}
    if cols["date"].empty:
        return pd.DataFrame(columns=list(_OHLCV_COLS))
    return pd.DataFrame(cols)


def initialize(context) -> None:  # noqa: ARG001
    g.entry_price = None


def handle_data(context, data) -> None:  # noqa: ARG001
    security = context.security
    hist = _ohlcv_window(130, "1d", security)
    if len(hist) < 15:
        return

    df = pl.from_pandas(hist)
    ts = _to_ts_code(security.zfill(6))
    dd = daily_data_list_from_polars(df, ts_code=ts)
    rows = bar_dict_rows_from_daily_data(dd)
    for r in rows:
        r["ts_code"] = ts

    i = len(rows) - 1
    position = float(get_position(security).amount)

    if position > 0 and g.entry_price is not None:
        close = float(hist.iloc[-1]["close"])
        entry = float(g.entry_price)
        if close <= entry * 0.96 or close >= entry * 1.12:
            order(security, -position)
            g.entry_price = None
        return

    sig = detect_b1(rows, i)
    if sig is not None and position == 0:
        order(security, 100)
        g.entry_price = float(hist.iloc[-1]["close"])


g = SimpleNamespace(entry_price=None)


SPEC = TradeStrategySpec(
    id="zettaranc_b1",
    name="Z 哥 B1 触发",
    description=(
        "日线窗口内识别 B1 买点信号后建仓；跌破买入价约 4% 止损，"
        "涨超约 12% 止盈。需足够历史 K 线（建议回测区间 ≥120 交易日）。"
    ),
    strategy_module=__name__,
)
