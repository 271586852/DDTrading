from __future__ import annotations

from app.score.score_strategies.spec import ScoringStrategy

STRATEGY = ScoringStrategy(
    id="balanced",
    name="\u5e73\u8861\u578b",
    description=(
        "\u4ef7\u503c\u3001\u52a8\u91cf\u3001\u6ce2\u52a8\u7387\u5404\u5360\u4e09\u5206\u4e4b\u4e00\u7684\u5747\u8861\u914d\u7f6e\uff0c"
        "\u9002\u5408\u4f5c\u4e3a\u9ed8\u8ba4\u57fa\u51c6\u3002"
    ),
    pe_weight=-0.34,
    momentum_weight=0.33,
    volatility_weight=-0.33,
    lookback_days=20,
)
