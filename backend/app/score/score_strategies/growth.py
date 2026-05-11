from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="growth",
    name="\u6210\u957f\u578b",
    description=(
        "\u504f\u6210\u957f\uff1a\u4ef7\u503c\u6743\u91cd\u8f83\u5c0f\uff0c\u4ee5\u52a8\u91cf + \u4f4e\u6ce2\u52a8\u7ec4\u5408\u7b5b\u9009\u3002"
    ),
    pe_weight=-0.10,
    momentum_weight=0.55,
    volatility_weight=-0.35,
    lookback_days=60,
)
