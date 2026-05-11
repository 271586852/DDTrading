"""Technical / cross-sectional indicator helpers shared by scoring and backtest.

Populate this module with pure functions as you extract them from ``app.common.market_data``
or other layers. Keeping calculations here avoids circular imports between
``score`` and ``backtest``.
"""

from __future__ import annotations

__all__: list[str] = []
