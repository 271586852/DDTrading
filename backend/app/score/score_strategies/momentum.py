from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="momentum",
    name="\u52a8\u91cf\u578b",
    description=(
        "\u8ffd\u9010\u8d8b\u52bf\uff1a\u4ee5\u8fd1 20 \u4ea4\u6613\u65e5\u52a8\u91cf\u4e3a\u4e3b\uff0c"
        "\u9002\u5ea6\u5bb9\u5fcd\u9ad8\u4f30\u503c\u548c\u6ce2\u52a8\u3002"
    ),
    pe_weight=-0.15,
    momentum_weight=0.70,
    volatility_weight=-0.15,
    lookback_days=60,
)
