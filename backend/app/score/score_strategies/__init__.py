"""Preset scoring strategies (one module per strategy)."""
from __future__ import annotations

from app.score.score_strategies.balanced import STRATEGY as _balanced
from app.score.score_strategies.growth import STRATEGY as _growth
from app.score.score_strategies.low_volatility import STRATEGY as _low_volatility
from app.score.score_strategies.momentum import STRATEGY as _momentum
from app.score.score_strategies.single_stock_only import STRATEGY as _single_stock_only
from app.score.score_strategies.spec import ScoringStrategy
from app.score.score_strategies.value import STRATEGY as _value

_STRATEGY_LIST: tuple[ScoringStrategy, ...] = (
    _balanced,
    _value,
    _momentum,
    _low_volatility,
    _growth,
    _single_stock_only,
)

_STRATEGY_MAP: dict[str, ScoringStrategy] = {s.id: s for s in _STRATEGY_LIST}

DEFAULT_STRATEGY_ID = "balanced"


def list_strategies() -> list[ScoringStrategy]:
    """返回所有预设策略（保留注册顺序）。"""
    return list(_STRATEGY_LIST)


def get_strategy(strategy_id: str) -> ScoringStrategy:
    """按 id 取策略；id 不存在则抛 ``KeyError``。"""
    try:
        return _STRATEGY_MAP[strategy_id]
    except KeyError as exc:
        available = ", ".join(_STRATEGY_MAP.keys())
        raise KeyError(
            f"Unknown scoring strategy '{strategy_id}'. Available: {available}."
        ) from exc


def strategy_exists(strategy_id: str) -> bool:
    return strategy_id in _STRATEGY_MAP


def get_strategy_lookback_days(strategy_id: str | None) -> int:
    """返回策略建议的历史窗口天数（交易日）。"""
    if not strategy_id:
        return 20
    return get_strategy(strategy_id).lookback_days


__all__ = [
    "DEFAULT_STRATEGY_ID",
    "ScoringStrategy",
    "get_strategy",
    "get_strategy_lookback_days",
    "list_strategies",
    "strategy_exists",
]
