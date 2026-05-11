"""Preset scoring strategy metadata (PE / momentum / volatility weights)."""
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
    lookback_days: int = 20

    def weights(self) -> dict[str, float]:
        return {
            "pe_weight": self.pe_weight,
            "momentum_weight": self.momentum_weight,
            "volatility_weight": self.volatility_weight,
        }
