"""Multi-factor stock scoring domain."""
from __future__ import annotations

from app.score.market_job import (
    ScoreMarketJob,
    complete_job,
    create_job,
    fail_job,
    get_job,
    update_job,
)
from app.score.score_strategies import (
    FactorFieldMeta,
    ScoringStrategy,
    get_strategy,
    get_strategy_lookback_days,
    list_strategies,
    strategy_exists,
)
from app.score.service import score_stocks

__all__ = [
    "FactorFieldMeta",
    "ScoringStrategy",
    "ScoreMarketJob",
    "complete_job",
    "create_job",
    "fail_job",
    "get_job",
    "get_strategy",
    "get_strategy_lookback_days",
    "list_strategies",
    "score_stocks",
    "strategy_exists",
    "update_job",
]
