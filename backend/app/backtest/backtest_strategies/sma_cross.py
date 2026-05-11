from __future__ import annotations

from types import SimpleNamespace

from app.backtest.backtest_strategies.spec import TradeStrategySpec


def initialize(context) -> None:  # noqa: ARG001
    g.prev_fast = None
    g.prev_slow = None


def handle_data(context, data) -> None:  # noqa: ARG001
    security = context.security
    hist = get_history(20, "1d", "close", security)
    if len(hist) < 20:
        return
    closes = list(hist["close"])
    fast_now = sum(closes[-5:]) / 5
    slow_now = sum(closes[-20:]) / 20
    if g.prev_fast is None or g.prev_slow is None:
        g.prev_fast = fast_now
        g.prev_slow = slow_now
        return
    position = get_position(security)
    if g.prev_fast <= g.prev_slow and fast_now > slow_now and position.amount == 0:
        order(security, 100)
    elif g.prev_fast >= g.prev_slow and fast_now < slow_now and position.amount > 0:
        order(security, -position.amount)
    g.prev_fast = fast_now
    g.prev_slow = slow_now


g = SimpleNamespace()


SPEC = TradeStrategySpec(
    id="sma_cross",
    name="SMA 金叉/死叉",
    description="SMA(5) 上穿 SMA(20) 买入，下穿卖出，典型的均线趋势跟随。",
    strategy_module=__name__,
)
