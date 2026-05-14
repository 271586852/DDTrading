"""预设评分策略：扫描本子包中带 ``STRATEGY`` 的模块并注册。"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Tuple

import app.score.score_strategies as _pkg
from app.score.score_strategies.spec import FactorFieldMeta, ScoringStrategy

_SKIP_MODULES = frozenset(
    {
        "spec",
        "__init__",
        # screener 是算法实现与工具集合，不是带 STRATEGY 的可注册元数据模块。
        "zettaranc_screener",
    }
)


def _discover_strategies() -> tuple[ScoringStrategy, ...]:
    found: list[ScoringStrategy] = []
    # 约定优于配置：扫描子模块，凡是导出 STRATEGY 的都自动纳入预设策略列表。
    for info in pkgutil.iter_modules(_pkg.__path__, _pkg.__name__ + "."):
        short = info.name.rsplit(".", 1)[-1]
        if short in _SKIP_MODULES:
            continue
        mod = importlib.import_module(info.name)
        s = getattr(mod, "STRATEGY", None)
        if isinstance(s, ScoringStrategy):
            found.append(s)
    return tuple(sorted(found, key=lambda x: x.id))


_STRATEGY_LIST: tuple[ScoringStrategy, ...] = _discover_strategies()
_STRATEGY_MAP: dict[str, ScoringStrategy] = {s.id: s for s in _STRATEGY_LIST}


def list_strategies() -> list[ScoringStrategy]:
    """返回所有预设策略（按 ``id`` 排序）。"""
    return list(_STRATEGY_LIST)


def get_strategy(strategy_id: str) -> ScoringStrategy:
    """按 id 取策略；id 不存在则抛 ``KeyError``。"""
    try:
        return _STRATEGY_MAP[str(strategy_id)]
    except KeyError as exc:
        available = ", ".join(_STRATEGY_MAP.keys())
        # 直接把可用策略名带回去，方便 API 层原样透传给调用方排查。
        raise KeyError(
            f"Unknown scoring strategy '{strategy_id}'. Available: {available}."
        ) from exc


def strategy_exists(strategy_id: str) -> bool:
    """判断策略 id 是否已注册。"""
    return strategy_id in _STRATEGY_MAP


def get_strategy_lookback_days(strategy_id: str | None) -> int:
    """返回策略建议的历史窗口天数（交易日）。"""
    if not strategy_id:
        return 120
    return get_strategy(strategy_id).lookback_days


__all__ = [
    "FactorFieldMeta",
    "ScoringStrategy",
    "get_strategy",
    "get_strategy_lookback_days",
    "list_strategies",
    "strategy_exists",
]
