from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """评分请求体。

    调用方有两种用法：
    1. 传 ``strategy_id`` 套用预设策略（此时三个 weight 会被该策略覆盖）。
    2. 不传 ``strategy_id``，直接传三个 weight 手动配比。

    另外可选传 ``symbol``：
    - 不传：全市场排行榜（默认 top 50）。
    - 传：只返回该 symbol 在全市场 z-score 体系下的评分；若不在 parquet
      缓存则后端抛 KeyError → 404；若为 ETF（无 PE）则抛 ValueError → 400。
    """

    strategy_id: Optional[str] = Field(
        default=None,
        description="可选的预设策略 id；若提供，会覆盖下面三个 weight。",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="可选的单只代码；提供后只返回该 symbol 的评分（全市场 z-score 口径）。",
    )
    pe_weight: float = Field(default=0.3, description="Weight for PE ratio.")
    momentum_weight: float = Field(default=0.5, description="Weight for 20-day momentum.")
    volatility_weight: float = Field(default=-0.2, description="Weight for volatility.")

    @model_validator(mode="after")
    def validate_non_zero_weights(self) -> "ScoreRequest":
        if self.strategy_id:
            # 策略模式：权重由策略决定，这里不做非零校验
            return self
        total_abs_weight = (
            abs(self.pe_weight)
            + abs(self.momentum_weight)
            + abs(self.volatility_weight)
        )
        if total_abs_weight == 0:
            raise ValueError("At least one factor weight must be non-zero.")
        return self


class RankedStock(BaseModel):
    rank: int
    ticker: str
    name: str
    total_score: float
    factor_values: Dict[str, float]
    factor_zscores: Dict[str, float]


class StrategyInfo(BaseModel):
    """单条预设策略的对外展示结构。"""

    id: str
    name: str
    description: str
    weights: Dict[str, float]


class ScoreResponse(BaseModel):
    normalized_weights: Dict[str, float]
    total_universe: int
    returned_count: int
    mode: str = Field(
        default="market",
        description="'market' 表示全市场排行；'single' 表示单股评分（top_50 最多 1 条）。",
    )
    top_50: List[RankedStock]
    applied_strategy: Optional[StrategyInfo] = Field(
        default=None,
        description="当通过 strategy_id 选中预设时回显的策略元信息。",
    )


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    """单只股票回测请求体。"""

    symbol: str = Field(description="6 位 A 股代码，如 '600000'。")
    start_date: date = Field(description="回测起始日期（含），服务端会 clamp 到可用区间。")
    end_date: date = Field(description="回测结束日期（含），服务端会 clamp 到可用区间。")
    initial_cash: float = Field(default=100_000.0, gt=0, description="初始资金。")
    strategy_id: Optional[str] = Field(
        default=None,
        description="可选的交易策略 id；未指定时使用默认策略。",
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date.")
        return self


class BacktestReportRequest(BacktestRequest):
    """回测 HTML 报告导出请求体。"""

    title: Optional[str] = Field(
        default=None,
        description="可选的报告标题；不传则由服务端自动生成。",
    )
    curve_freq: Literal["raw", "D"] = Field(
        default="D",
        description="报告曲线频率：raw 原始频率，D 为日频末值。",
    )


class BacktestDateRange(BaseModel):
    start: date
    end: date


class BacktestMetrics(BaseModel):
    """回测关键指标（字段缺失时为 None）。"""

    total_return: Optional[float] = None
    annualized_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    final_equity: Optional[float] = None


class TradeStrategyInfo(BaseModel):
    """可用交易策略的对外展示结构。"""

    id: str
    name: str
    description: str


class EquityPoint(BaseModel):
    """权益曲线上的一个点（带回撤百分比，前端可直接叠色）。"""

    date: str
    equity: float
    drawdown_pct: float = Field(
        description="相对历史峰值的回撤百分比，正数（如 3.5 表示 -3.5%）。",
    )


class PricePoint(BaseModel):
    """价格/资金/持仓联动图所需的一根 K 线摘要。"""

    date: str
    close: Optional[float] = None


class TradeMarker(BaseModel):
    """单条成交的可视化标记。"""

    date: str
    price: Optional[float] = None
    side: str = Field(description="'buy' | 'sell'，用于前端决定箭头方向与颜色。")
    quantity: Optional[float] = None
    pnl: Optional[float] = None


class BacktestResponse(BaseModel):
    symbol: str
    requested_range: BacktestDateRange
    effective_range: BacktestDateRange = Field(
        description="实际用于回测的区间（已根据可用 parquet 数据 clamp）。"
    )
    initial_cash: float
    metrics: BacktestMetrics
    applied_strategy: Optional[TradeStrategyInfo] = Field(
        default=None,
        description="实际使用的交易策略元信息。",
    )
    equity_curve: List[EquityPoint] = Field(
        default_factory=list,
        description="按时间升序的权益曲线 + 回撤，用于主图。",
    )
    price_series: List[PricePoint] = Field(
        default_factory=list,
        description="与权益曲线同区间的收盘价序列，用于叠加 K 线或副图。",
    )
    trade_markers: List[TradeMarker] = Field(
        default_factory=list,
        description="成交点位标记，前端在价格线上打买/卖箭头。",
    )
    recent_trades: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="最近 100 条交易明细（时间倒序）。",
    )
    recent_positions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="最近 100 条持仓快照（时间倒序）。",
    )
    daily_positions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="每日持仓详情（按时间升序，来自 BacktestResult.positions_df）。",
    )


# ---------------------------------------------------------------------------
# Quote (single-symbol price snapshot + recent candles)
# ---------------------------------------------------------------------------


class QuoteCandle(BaseModel):
    date: Optional[str] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None


class QuoteResponse(BaseModel):
    """单只标的报价快照。"""

    symbol: str
    name: Optional[str] = None
    kind: str = Field(
        description="'stock' | 'etf' | 'unknown'，用于前端判断是否禁用评分按钮。",
    )
    latest_close: Optional[float] = None
    prev_close: Optional[float] = None
    change_pct: Optional[float] = Field(
        default=None,
        description="最近一日涨跌幅（百分比数值，如 -1.42 表示跌 1.42%）。",
    )
    as_of_date: Optional[str] = None
    bars: int = 0
    history: List[QuoteCandle] = Field(
        default_factory=list,
        description="按日期升序的最近若干根 K 线。",
    )
