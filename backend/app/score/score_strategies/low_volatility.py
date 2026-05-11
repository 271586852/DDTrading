from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="low_volatility",
    name="\u4f4e\u6ce2\u52a8",
    description=(
        "\u9632\u5b88\u578b\uff1a\u4ee5\u4f4e\u6ce2\u52a8\u4e3a\u4e3b\u8981\u8d23\u6760\uff0c"
        "\u5144\u987e\u4f30\u503c\u548c\u52a8\u91cf\u3002"
    ),
    pe_weight=-0.25,
    momentum_weight=0.15,
    volatility_weight=-0.60,
    lookback_days=40,
)
