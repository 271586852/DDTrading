"""Backtest / trade strategies (one module per strategy; PTrade-style source)."""
from __future__ import annotations

from app.backtest.backtest_strategies.buy_hold import SPEC as _buy_hold
from app.backtest.backtest_strategies.flip_100 import SPEC as _flip_100
from app.backtest.backtest_strategies.smoke_test import SPEC as _smoke_test
from app.backtest.backtest_strategies.sma_cross import SPEC as _sma_cross
from app.backtest.backtest_strategies.spec import TradeStrategySpec

_TRADE_STRATEGIES: tuple[TradeStrategySpec, ...] = (
    _smoke_test,
    _flip_100,
    _sma_cross,
    _buy_hold,
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


__all__ = [
    "DEFAULT_TRADE_STRATEGY_ID",
    "TradeStrategySpec",
    "get_trade_strategy",
    "list_trade_strategies",
]
