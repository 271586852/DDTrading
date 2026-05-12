from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """评分请求体。

    必须传 ``strategy_id``（见 GET /score-strategies）；评分逻辑由对应 ``score_engine`` 实现。
    可选 ``symbol``：
    - 不传：对本地 DuckDB 全市场日线逐只跑该策略，返回 top 50（或更少）。
    - 传：只返回该标的的单股评分；会先按需补齐该标的缓存。
    """

    strategy_id: str = Field(
        ...,
        min_length=1,
        description="必选预设策略 id（见 GET /score-strategies）；计算逻辑由该策略的 score_engine 决定。",
    )
    symbol: Optional[str] = Field(
        default=None,
        description="可选单只代码；不传则全市场排行。",
    )


class RankedStock(BaseModel):
    rank: int
    ticker: str
    name: str
    total_score: float
    factor_values: Optional[Dict[str, float]] = Field(
        default=None,
        description="分项原始值；由评分策略决定是否返回及包含哪些键。",
    )
    factor_zscores: Optional[Dict[str, float]] = Field(
        default=None,
        description="分项 z-score 或策略自定义的标准化分；无分项时为空。",
    )


class FactorFieldInfo(BaseModel):
    """分项展示元数据（与 ``factor_values`` 键对齐，供前端渲染）。"""

    key: str
    label: str
    value_format: str = Field(
        description="数值格式提示，如 decimal_2 / percent_2 / integer 等。",
    )
    zscore_orientation: str = Field(
        description="分位或 z 分解释：higher_better / lower_better / value_as_percentile_0_100 / none。",
    )


class StrategyInfo(BaseModel):
    """单条预设评分策略的对外展示结构。"""

    id: str
    name: str
    description: str
    score_engine: str = Field(description="评分算法管线标识，与后端注册表一致。")
    factor_keys: List[str] = Field(
        description="分项键列表（与 factor_fields.key 一致，便于兼容旧客户端）。",
    )
    factor_fields: List[FactorFieldInfo] = Field(
        description="分项完整元数据（标签与格式），优先供前端展示。",
    )


class ScoreResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
    market_data_revision: float = Field(
        default=0.0,
        description="本地全市场数据版本号；客户端据此判断缓存是否仍有效。",
    )


class MarketScoreJobStarted(BaseModel):
    job_id: str = Field(description="用于轮询 GET /score/market-job/{job_id} 的任务 id。")


class MarketScoreJobStatus(BaseModel):
    status: Literal["pending", "running", "completed", "failed"] = Field(
        description="pending=已创建；running=执行中；completed=成功；failed=异常结束。"
    )
    progress: int = Field(ge=0, le=100, description="粗略进度百分比。")
    stage: str = Field(default="", description="当前阶段说明。")
    result: Optional[ScoreResponse] = Field(
        default=None,
        description="仅当 status=completed 时返回评分结果。",
    )
    error: Optional[str] = Field(default=None, description="仅当 status=failed 时返回错误信息。")


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
        description="实际用于回测的区间（已根据可用 DuckDB 数据 clamp）。"
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
        description="全部成交明细（时间倒序，最新在前）；前端可本地分页展示。",
    )
    recent_positions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="兼容字段，当前为空列表；持仓请使用 daily_positions。",
    )
    daily_positions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="全部每日持仓（按时间升序，来自 positions_df）；前端可本地分页展示。",
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
