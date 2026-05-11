from __future__ import annotations

from types import SimpleNamespace

from app.backtest.backtest_strategies.spec import TradeStrategySpec


def initialize(context) -> None:  # noqa: ARG001
    pass


def handle_data(context, data) -> None:  # noqa: ARG001
    security = context.security
    position = get_position(security)
    if position.amount == 0:
        order(security, 100)
    else:
        order(security, -100)


g = SimpleNamespace()


SPEC = TradeStrategySpec(
    id="flip_100",
    name="翻转 100 股",
    description="最基础的联调策略：无仓即买 100 股，有仓即卖 100 股。",
    strategy_module=__name__,
)
