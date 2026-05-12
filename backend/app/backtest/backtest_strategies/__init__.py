"""回测 / 交易策略：扫描本子包中带 ``SPEC`` 的模块并注册。"""
from __future__ import annotations

import importlib
import pkgutil

import app.backtest.backtest_strategies as _pkg
from app.backtest.backtest_strategies.spec import TradeStrategySpec

_SKIP_MODULES = frozenset({"spec", "__init__"})


def _discover_trade_strategies() -> tuple[TradeStrategySpec, ...]:
    found: list[TradeStrategySpec] = []
    for info in pkgutil.iter_modules(_pkg.__path__, _pkg.__name__ + "."):
        short = info.name.rsplit(".", 1)[-1]
        if short in _SKIP_MODULES:
            continue
        mod = importlib.import_module(info.name)
        spec = getattr(mod, "SPEC", None)
        if isinstance(spec, TradeStrategySpec):
            found.append(spec)
    return tuple(sorted(found, key=lambda x: x.id))


_TRADE_STRATEGIES: tuple[TradeStrategySpec, ...] = _discover_trade_strategies()
_TRADE_STRATEGY_MAP: dict[str, TradeStrategySpec] = {spec.id: spec for spec in _TRADE_STRATEGIES}

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
