from __future__ import annotations

from app.score.score_strategies.spec import FactorFieldMeta, ScoringStrategy

# 这里只声明策略元数据；实际打分实现位于 score.service / zettaranc_screener。
STRATEGY = ScoringStrategy(
    id="zettaranc_composite",
    name="Z 哥四维选股",
    description=(
        "基于 screener 的 B1/趋势/量价/风险四维加权综合分（0~100）。"
        "不传 symbol 时对全市场本地日线逐只评分并排行；传 symbol 则仅评该标的。"
    ),
    score_engine="zettaranc_composite",
    factor_fields=(
        FactorFieldMeta("b1_opportunity", "B1 机会", "decimal_1", "value_as_percentile_0_100"),
        FactorFieldMeta("trend", "趋势", "decimal_1", "value_as_percentile_0_100"),
        FactorFieldMeta("volume_pattern", "量价形态", "decimal_1", "value_as_percentile_0_100"),
        FactorFieldMeta("risk", "风险", "decimal_1", "value_as_percentile_0_100"),
    ),
    lookback_days=120,
)
