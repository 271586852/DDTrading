from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="single_stock_only",
    name="\u5355\u80a1\u72ec\u7acb\u8bc4\u5206",
    description=(
        "\u4ec5\u7528\u4e8e\u5355\u53ea\u80a1\u7968\u8bc4\u5206\uff0c\u4e0d\u518d\u53c2\u4e0e\u5168\u5e02\u573a\u6392\u540d\u6216 z-score \u6bd4\u8f83\u3002"
    ),
    pe_weight=-0.34,
    momentum_weight=0.33,
    volatility_weight=-0.33,
    lookback_days=60,
)
