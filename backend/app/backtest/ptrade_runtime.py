"""在本地 K 线 DataFrame 上执行 PTrade 风格 ``initialize`` / ``handle_data`` 的最小运行时。"""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, Callable

import pandas as pd

from app.backtest.backtest_strategies.spec import TradeStrategySpec


class PTradeBarRuntime:
    """单标的、逐根 bar：注入 ``g`` / ``order`` / ``get_position`` / ``get_history`` 到策略模块。"""

    __slots__ = (
        "_frame",
        "_symbol",
        "_commission_rate",
        "cash",
        "position",
        "avg_entry_price",
        "avg_entry_time",
        "avg_entry_bar",
        "bar_index",
        "current_ts",
        "current_close",
        "trades",
        "positions",
        "equities",
    )

    def __init__(
        self,
        *,
        frame: pd.DataFrame,
        symbol: str,
        initial_cash: float,
        commission_rate: float,
    ) -> None:
        self._frame = frame
        self._symbol = symbol
        self._commission_rate = float(commission_rate)
        self.cash = float(initial_cash)
        self.position = 0.0
        self.avg_entry_price: float | None = None
        self.avg_entry_time: pd.Timestamp | None = None
        self.avg_entry_bar: int | None = None
        self.bar_index = 0
        self.current_ts = pd.Timestamp(frame.iloc[0]["date"])
        self.current_close = float(frame.iloc[0]["close"])
        self.trades: list[dict[str, Any]] = []
        self.positions: list[dict[str, Any]] = []
        self.equities: list[tuple[pd.Timestamp, float]] = []

    def _record_equity(self) -> None:
        close = self.current_close
        ts = self.current_ts
        market_value = self.position * close
        equity = self.cash + market_value
        self.equities.append((ts, equity))
        self.positions.append(
            {
                "date": ts,
                "equity": equity,
                "market_value": market_value,
                "cash": self.cash,
                "margin": 0.0,
                "positions": int(self.position > 0),
                "net_exposure": market_value,
                "gross_exposure": abs(market_value),
                "leverage": abs(market_value) / equity if equity else 0.0,
                "quantity": self.position,
            }
        )

    def order(self, security: str, qty: float) -> None:
        if security != self._symbol:
            return
        close = self.current_close
        ts = self.current_ts
        idx = self.bar_index
        cr = self._commission_rate
        if qty > 0:
            cost = close * qty
            comm = cost * cr
            if self.cash >= cost + comm:
                self.cash -= cost + comm
                self.position += qty
                self.avg_entry_price = close
                self.avg_entry_time = ts
                self.avg_entry_bar = idx
        elif qty < 0 and self.position > 0:
            sell_qty = min(self.position, -qty)
            proceeds = close * sell_qty
            comm = proceeds * cr
            self.cash += proceeds - comm
            entry_price = float(self.avg_entry_price or close)
            entry_time = self.avg_entry_time or ts
            entry_bar = self.avg_entry_bar if self.avg_entry_bar is not None else idx
            gross_pnl = (close - entry_price) * sell_qty
            net_pnl = gross_pnl - (entry_price * sell_qty * cr) - comm
            self.trades.append(
                {
                    "symbol": self._symbol,
                    "side": "long",
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": close,
                    "quantity": sell_qty,
                    "pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "return_pct": (close / entry_price - 1.0) * 100.0 if entry_price else None,
                    "commission": (entry_price * sell_qty * cr) + comm,
                    "duration_bars": idx - entry_bar,
                }
            )
            self.position -= sell_qty
            if self.position <= 0:
                self.position = 0.0
                self.avg_entry_price = None
                self.avg_entry_time = None
                self.avg_entry_bar = None

    def get_position(self, security: str) -> SimpleNamespace:
        if security != self._symbol:
            return SimpleNamespace(amount=0.0)
        return SimpleNamespace(amount=float(self.position))

    def get_history(self, n: int, _freq: str, field: str, security: str) -> pd.DataFrame:
        del _freq, security
        end = self.bar_index + 1
        start = max(0, end - int(n))
        series = self._frame.iloc[start:end][field].reset_index(drop=True)
        return pd.DataFrame({field: series})


def _bind_ptrade_api(mod: Any, rt: PTradeBarRuntime) -> None:
    mod.order = rt.order
    mod.get_position = rt.get_position
    mod.get_history = rt.get_history


def run_ptrade_on_frame(
    *,
    spec: TradeStrategySpec,
    frame: pd.DataFrame,
    symbol: str,
    initial_cash: float,
    commission_rate: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[tuple[pd.Timestamp, float]]]:
    mod = importlib.import_module(spec.strategy_module)
    initialize: Callable[[Any], None] = mod.initialize
    handle_data: Callable[[Any, Any], None] = mod.handle_data

    mod.g = SimpleNamespace()
    rt = PTradeBarRuntime(
        frame=frame,
        symbol=symbol,
        initial_cash=initial_cash,
        commission_rate=commission_rate,
    )
    _bind_ptrade_api(mod, rt)

    context = SimpleNamespace(security=symbol)
    data = SimpleNamespace()
    initialize(context)

    for bar_i in range(len(frame)):
        row = frame.iloc[bar_i]
        rt.bar_index = bar_i
        rt.current_ts = pd.Timestamp(row["date"])
        rt.current_close = float(row["close"])
        handle_data(context, data)
        rt._record_equity()

    return rt.trades, rt.positions, rt.equities
