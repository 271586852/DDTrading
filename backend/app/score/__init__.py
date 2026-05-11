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
    DEFAULT_STRATEGY_ID,
    ScoringStrategy,
    get_strategy,
    get_strategy_lookback_days,
    list_strategies,
    strategy_exists,
)
from app.score.service import SINGLE_STOCK_ONLY_STRATEGY_ID, load_dataset, score_stocks

__all__ = [
    "DEFAULT_STRATEGY_ID",
    "SINGLE_STOCK_ONLY_STRATEGY_ID",
    "ScoringStrategy",
    "ScoreMarketJob",
    "complete_job",
    "create_job",
    "fail_job",
    "get_job",
    "get_strategy",
    "get_strategy_lookback_days",
    "list_strategies",
    "load_dataset",
    "score_stocks",
    "strategy_exists",
    "update_job",
]
