"""PTrade 风格策略注册：每条策略为独立模块，实现 initialize / handle_data。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TradeStrategySpec:
    """单条交易策略元信息。"""

    id: str
    name: str
    description: str
    #: 实现 ``initialize`` / ``handle_data`` 的包内模块名，如 ``app.backtest.backtest_strategies.flip_100``。
    strategy_module: str
