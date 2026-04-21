"""预设评分策略目录。

每条策略描述了一组应用于三因子（pe_ratio / momentum_20d / volatility）的原始
权重，``/score`` 接口在 ``normalize_weights`` 里会按绝对值和归一化。

权重语义：
- ``pe_weight``       : 负号偏向低估值（低 PE 得分高）
- ``momentum_weight`` : 正号偏向强动量（近 20 交易日上行得分高）
- ``volatility_weight``: 负号偏向低波动（近 20 交易日波动小得分高）

调用方可以通过 ``strategy_id`` 套用预设，或继续直接传三个 weight 值手动指定。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringStrategy:
    """单条评分策略的元数据。"""

    id: str
    name: str
    description: str
    pe_weight: float
    momentum_weight: float
    volatility_weight: float

    def weights(self) -> dict[str, float]:
        return {
            "pe_weight": self.pe_weight,
            "momentum_weight": self.momentum_weight,
            "volatility_weight": self.volatility_weight,
        }


_STRATEGY_LIST: tuple[ScoringStrategy, ...] = (
    ScoringStrategy(
        id="balanced",
        name="\u5e73\u8861\u578b",
        description=(
            "\u4ef7\u503c\u3001\u52a8\u91cf\u3001\u6ce2\u52a8\u7387\u5404\u5360\u4e09\u5206\u4e4b\u4e00\u7684\u5747\u8861\u914d\u7f6e\uff0c"
            "\u9002\u5408\u4f5c\u4e3a\u9ed8\u8ba4\u57fa\u51c6\u3002"
        ),
        pe_weight=-0.34,
        momentum_weight=0.33,
        volatility_weight=-0.33,
    ),
    ScoringStrategy(
        id="value",
        name="\u4ef7\u503c\u578b",
        description=(
            "\u6697\u4f70\u4f30\u503c\uff1a\u4ee5\u4f4e PE \u4e3a\u4e3b\u8981\u9a71\u52a8\uff0c\u52a8\u91cf\u4f5c\u4e3a\u8f85\u52a9\uff0c"
            "\u5bb9\u5fcd\u8f83\u9ad8\u6ce2\u52a8\u3002"
        ),
        pe_weight=-0.70,
        momentum_weight=0.20,
        volatility_weight=-0.10,
    ),
    ScoringStrategy(
        id="momentum",
        name="\u52a8\u91cf\u578b",
        description=(
            "\u8ffd\u9010\u8d8b\u52bf\uff1a\u4ee5\u8fd1 20 \u4ea4\u6613\u65e5\u52a8\u91cf\u4e3a\u4e3b\uff0c"
            "\u9002\u5ea6\u5bb9\u5fcd\u9ad8\u4f30\u503c\u548c\u6ce2\u52a8\u3002"
        ),
        pe_weight=-0.15,
        momentum_weight=0.70,
        volatility_weight=-0.15,
    ),
    ScoringStrategy(
        id="low_volatility",
        name="\u4f4e\u6ce2\u52a8",
        description=(
            "\u9632\u5b88\u578b\uff1a\u4ee5\u4f4e\u6ce2\u52a8\u4e3a\u4e3b\u8981\u8d23\u6760\uff0c"
            "\u5144\u987e\u4f30\u503c\u548c\u52a8\u91cf\u3002"
        ),
        pe_weight=-0.25,
        momentum_weight=0.15,
        volatility_weight=-0.60,
    ),
    ScoringStrategy(
        id="growth",
        name="\u6210\u957f\u578b",
        description=(
            "\u504f\u6210\u957f\uff1a\u4ef7\u503c\u6743\u91cd\u8f83\u5c0f\uff0c\u4ee5\u52a8\u91cf + \u4f4e\u6ce2\u52a8\u7ec4\u5408\u7b5b\u9009\u3002"
        ),
        pe_weight=-0.10,
        momentum_weight=0.55,
        volatility_weight=-0.35,
    ),
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
