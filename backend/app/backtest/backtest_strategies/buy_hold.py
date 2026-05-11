from __future__ import annotations

from types import SimpleNamespace

from app.backtest.backtest_strategies.spec import TradeStrategySpec


def initialize(context) -> None:  # noqa: ARG001
    g.bought = False


def handle_data(context, data) -> None:  # noqa: ARG001
    if not g.bought:
        order(context.security, 100)
        g.bought = True


g = SimpleNamespace()


SPEC = TradeStrategySpec(
    id="buy_hold",
    name="买入持有",
    description="首根 bar 满仓买入 100 股后长期持有，作为基准。",
    strategy_module=__name__,
)
