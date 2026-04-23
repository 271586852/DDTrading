export type TradeStrategyInfo = {
  id: string;
  name: string;
  description: string;
};

export type BacktestMetrics = {
  total_return: number | null;
  annualized_return: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  win_rate: number | null;
  trade_count: number | null;
  final_equity: number | null;
};

export type BacktestDateRange = {
  start: string;
  end: string;
};

export type EquityPoint = {
  date: string;
  equity: number;
  drawdown_pct: number;
};

export type PricePoint = {
  date: string;
  close: number | null;
};

export type TradeMarker = {
  date: string;
  price: number | null;
  side: "buy" | "sell";
  quantity: number | null;
  pnl?: number | null;
};

export type BacktestRequest = {
  symbol: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  strategy_id?: string | null;
};

export type BacktestResponse = {
  symbol: string;
  requested_range: BacktestDateRange;
  effective_range: BacktestDateRange;
  initial_cash: number;
  metrics: BacktestMetrics;
  applied_strategy: TradeStrategyInfo | null;
  equity_curve: EquityPoint[];
  price_series: PricePoint[];
  trade_markers: TradeMarker[];
  recent_trades: Record<string, unknown>[];
  recent_positions: Record<string, unknown>[];
};
