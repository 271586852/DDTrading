from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field, model_validator


class ScoreRequest(BaseModel):
    pe_weight: float = Field(default=0.3, description="Weight for PE ratio.")
    momentum_weight: float = Field(default=0.5, description="Weight for 20-day momentum.")
    volatility_weight: float = Field(default=-0.2, description="Weight for volatility.")

    @model_validator(mode="after")
    def validate_non_zero_weights(self) -> "ScoreRequest":
        total_abs_weight = (
            abs(self.pe_weight)
            + abs(self.momentum_weight)
            + abs(self.volatility_weight)
        )
        if total_abs_weight == 0:
            raise ValueError("At least one factor weight must be non-zero.")
        return self


class RankedStock(BaseModel):
    rank: int
    ticker: str
    name: str
    total_score: float
    factor_values: Dict[str, float]
    factor_zscores: Dict[str, float]


class ScoreResponse(BaseModel):
    normalized_weights: Dict[str, float]
    total_universe: int
    returned_count: int
    top_50: List[RankedStock]
