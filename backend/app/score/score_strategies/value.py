from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="value",
    name="\u4ef7\u503c\u578b",
    description=(
        "\u7ecf\u5178\u4ef7\u503c\uff1a\u4ee5\u4f4e PE \u4e3a\u4e3b\u8981\u9a71\u52a8\uff0c\u52a8\u91cf\u4f5c\u4e3a\u8f85\u52a9\uff0c"
        "\u5bb9\u5fcd\u8f83\u9ad8\u6ce2\u52a8\u3002"
    ),
    pe_weight=-0.70,
    momentum_weight=0.20,
    volatility_weight=-0.10,
    lookback_days=20,
)
