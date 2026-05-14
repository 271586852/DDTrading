"""评分域的包级导出。

对外统一暴露评分服务、策略元数据与全市场异步任务接口，避免调用方分别深入子模块取对象。
"""
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

# 这里集中定义包级公共 API，供 ``from app.score import ...`` 直接使用。
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
