from __future__ import annotations

from types import SimpleNamespace

from app.backtest.backtest_strategies.spec import TradeStrategySpec


def initialize(context) -> None:  # noqa: ARG001
    g.step = 0


def handle_data(context, data) -> None:  # noqa: ARG001
    security = context.security
    if g.step == 0:
        order(security, 100)
    elif g.step == 1:
        order(security, -100)
    g.step += 1


g = SimpleNamespace()


SPEC = TradeStrategySpec(
    id="smoke_test",
    name="冒烟测试（买一卖一）",
    description="首根买入 100 股，次根卖出 100 股，后续不再交易；用于快速验证回测链路。",
    strategy_module=__name__,
)
