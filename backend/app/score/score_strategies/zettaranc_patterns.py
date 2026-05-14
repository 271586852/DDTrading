from __future__ import annotations

from app.score.score_strategies.spec import FactorFieldMeta, ScoringStrategy

# 这里只声明策略元数据；实际信号统计与评分实现位于 score.service。
STRATEGY = ScoringStrategy(
    id="zettaranc_patterns",
    name="Z 哥战法信号",
    description=(
        "根据近期战法信号数量与最新 BUY 信号置信度给出 0~100 参考分。"
        "不传 symbol 时对全市场本地日线逐只统计后排行；传 symbol 则仅评该标的。"
    ),
    score_engine="zettaranc_patterns",
    factor_fields=(
        FactorFieldMeta("pattern_signal_count", "战法信号数", "integer", "none"),
        FactorFieldMeta("latest_confidence", "最新信号置信度", "decimal_3", "none"),
    ),
    lookback_days=120,
)
