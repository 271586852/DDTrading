"""回测交易策略注册表。

与 ``app.strategies`` 中的“评分策略”不同，这里登记的是真正用于 akquant
回测的可执行策略，每个策略在 :class:`TradeStrategySpec` 中描述元信息，
并通过 ``build_cls`` 工厂在运行期构造 :class:`akquant.Strategy` 子类。

- ``flip_100``: 最简单的翻转策略——无仓买 100 股，有仓平仓 100 股。
- ``sma_cross``: 5/20 SMA 金叉死叉，全仓买入/清仓卖出。
- ``buy_hold``: 首根 bar 满仓买入后长持。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class TradeStrategySpec:
    """单条交易策略元信息。"""

    id: str
    name: str
    description: str
    build_cls: Callable[[], type]


def _build_flip_100_cls() -> type:
    from akquant import Strategy

    class _Flip100(Strategy):
        """无仓买 100 股，有仓平 100 股（用于快速联调）。"""

        def on_bar(self, bar):  # type: ignore[no-untyped-def]
            position = self.get_position(bar.symbol)
            if position == 0:
                self.buy(symbol=bar.symbol, quantity=100)
            elif position > 0:
                self.sell(symbol=bar.symbol, quantity=100)

    return _Flip100


def _build_sma_cross_cls() -> type:
    from collections import deque

    from akquant import Strategy

    class _SmaCross(Strategy):
        """SMA(5) 上穿 SMA(20) 买入，下穿卖出。

        为规避 akquant Indicator API 的版本差异，这里直接在策略内部
        维护收盘价滚动队列，手工计算两条 SMA。
        """

        fast_period = 5
        slow_period = 20

        def on_start(self):  # type: ignore[no-untyped-def]
            self._closes: deque[float] = deque(maxlen=self.slow_period + 2)
            self._prev_fast: float | None = None
            self._prev_slow: float | None = None

        def on_bar(self, bar):  # type: ignore[no-untyped-def]
            if not hasattr(self, "_closes"):
                self._closes = deque(maxlen=self.slow_period + 2)
                self._prev_fast = None
                self._prev_slow = None

            close = float(getattr(bar, "close", 0.0) or 0.0)
            self._closes.append(close)

            if len(self._closes) < self.slow_period:
                self._prev_fast = None
                self._prev_slow = None
                return

            closes_list = list(self._closes)
            fast_now = sum(closes_list[-self.fast_period:]) / self.fast_period
            slow_now = sum(closes_list[-self.slow_period:]) / self.slow_period

            if self._prev_fast is None or self._prev_slow is None:
                self._prev_fast = fast_now
                self._prev_slow = slow_now
                return

            position = self.get_position(bar.symbol)
            cross_up = self._prev_fast <= self._prev_slow and fast_now > slow_now
            cross_down = self._prev_fast >= self._prev_slow and fast_now < slow_now

            if cross_up and position == 0:
                self.buy(symbol=bar.symbol, quantity=100)
            elif cross_down and position > 0:
                self.sell(symbol=bar.symbol, quantity=position)

            self._prev_fast = fast_now
            self._prev_slow = slow_now

    return _SmaCross


def _build_buy_hold_cls() -> type:
    from akquant import Strategy

    class _BuyHold(Strategy):
        """首根 bar 满仓买入 100 股，随后持有。"""

        def on_bar(self, bar):  # type: ignore[no-untyped-def]
            if self.get_position(bar.symbol) == 0:
                self.buy(symbol=bar.symbol, quantity=100)

    return _BuyHold


_TRADE_STRATEGIES: tuple[TradeStrategySpec, ...] = (
    TradeStrategySpec(
        id="flip_100",
        name="翻转 100 股",
        description="最基础的联调策略：无仓即买 100 股，有仓即卖 100 股。",
        build_cls=_build_flip_100_cls,
    ),
    TradeStrategySpec(
        id="sma_cross",
        name="SMA 金叉/死叉",
        description="SMA(5) 上穿 SMA(20) 买入，下穿卖出，典型的均线趋势跟随。",
        build_cls=_build_sma_cross_cls,
    ),
    TradeStrategySpec(
        id="buy_hold",
        name="买入持有",
        description="首根 bar 满仓买入 100 股后长期持有，作为基准。",
        build_cls=_build_buy_hold_cls,
    ),
)

_TRADE_STRATEGY_MAP: dict[str, TradeStrategySpec] = {
    spec.id: spec for spec in _TRADE_STRATEGIES
}

DEFAULT_TRADE_STRATEGY_ID = "flip_100"


def list_trade_strategies() -> list[TradeStrategySpec]:
    return list(_TRADE_STRATEGIES)


def get_trade_strategy(strategy_id: str) -> TradeStrategySpec:
    try:
        return _TRADE_STRATEGY_MAP[strategy_id]
    except KeyError as exc:
        available = ", ".join(_TRADE_STRATEGY_MAP.keys())
        raise KeyError(
            f"Unknown trade strategy '{strategy_id}'. Available: {available}."
        ) from exc
