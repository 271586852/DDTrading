"""回测交易策略注册表。

与 ``app.strategies`` 中的“评分策略”不同，这里登记的是真正用于
SimTradeLab/PTrade 风格回测的策略。策略 id 维持稳定，便于前端和历史
请求继续复用。

- ``flip_100``: 最简单的翻转策略——无仓买 100 股，有仓平仓 100 股。
- ``sma_cross``: 5/20 SMA 金叉死叉，全仓买入/清仓卖出。
- ``buy_hold``: 首根 bar 满仓买入后长持。
- ``smoke_test``: 首根买入、次根卖出，之后不再交易（用于链路冒烟测试）。
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
    source_factory: Callable[[], str]


def _ptrade_smoke_test() -> str:
    return """
def initialize(context):
    g.step = 0

def handle_data(context, data):
    security = context.security
    if g.step == 0:
        order(security, 100)
    elif g.step == 1:
        order(security, -100)
    g.step += 1
""".strip()


def _ptrade_flip_100() -> str:
    return """
def initialize(context):
    pass

def handle_data(context, data):
    security = context.security
    position = get_position(security)
    if position.amount == 0:
        order(security, 100)
    else:
        order(security, -100)
""".strip()


def _ptrade_sma_cross() -> str:
    return """
def initialize(context):
    g.prev_fast = None
    g.prev_slow = None

def handle_data(context, data):
    security = context.security
    hist = get_history(20, '1d', 'close', security)
    if len(hist) < 20:
        return
    closes = list(hist['close'])
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
""".strip()


def _ptrade_buy_hold() -> str:
    return """
def initialize(context):
    g.bought = False

def handle_data(context, data):
    if not g.bought:
        order(context.security, 100)
        g.bought = True
""".strip()


_TRADE_STRATEGIES: tuple[TradeStrategySpec, ...] = (
    TradeStrategySpec(
        id="smoke_test",
        name="冒烟测试（买一卖一）",
        description="首根买入 100 股，次根卖出 100 股，后续不再交易；用于快速验证回测链路。",
        source_factory=_ptrade_smoke_test,
    ),
    TradeStrategySpec(
        id="flip_100",
        name="翻转 100 股",
        description="最基础的联调策略：无仓即买 100 股，有仓即卖 100 股。",
        source_factory=_ptrade_flip_100,
    ),
    TradeStrategySpec(
        id="sma_cross",
        name="SMA 金叉/死叉",
        description="SMA(5) 上穿 SMA(20) 买入，下穿卖出，典型的均线趋势跟随。",
        source_factory=_ptrade_sma_cross,
    ),
    TradeStrategySpec(
        id="buy_hold",
        name="买入持有",
        description="首根 bar 满仓买入 100 股后长期持有，作为基准。",
        source_factory=_ptrade_buy_hold,
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
