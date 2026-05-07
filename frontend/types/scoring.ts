export type FactorWeights = {
  pe_weight: number;
  momentum_weight: number;
  volatility_weight: number;
};

export type RankedStock = {
  rank: number;
  ticker: string;
  name: string;
  total_score: number;
  factor_values: {
    pe_ratio: number;
    momentum_20d: number;
    volatility: number;
  };
  factor_zscores: {
    pe_ratio: number;
    momentum_20d: number;
    volatility: number;
  };
};

export type StrategyInfo = {
  id: string;
  name: string;
  description: string;
  weights: FactorWeights;
};

export type ScoreMode = "market" | "single";

export type ScoreResponse = {
  normalized_weights: FactorWeights;
  total_universe: number;
  returned_count: number;
  mode: ScoreMode;
  top_50: RankedStock[];
  applied_strategy?: StrategyInfo | null;
  /** 与 GET /market-data-revision 一致；本地数据更新后变大，用于全市场结果缓存失效 */
  market_data_revision: number;
};

export type MarketDataRevisionResponse = {
  market_data_revision: number;
};

export type MarketScoreJobStarted = {
  job_id: string;
};

export type MarketScoreJobStatus = {
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  stage: string;
  result?: ScoreResponse | null;
  error?: string | null;
};

export type QuoteCandle = {
  date: string | null;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type SymbolKind = "stock" | "etf" | "unknown";

export type QuoteResponse = {
  symbol: string;
  name: string | null;
  kind: SymbolKind;
  latest_close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  as_of_date: string | null;
  bars: number;
  history: QuoteCandle[];
};

export type HistoryEntry = {
  id: string;
  symbol: string;
  name: string | null;
  strategyId: string;
  strategyName: string;
  totalScore: number | null;
  kind: SymbolKind;
  analyzedAt: number;
};

export type RefreshMode = "incremental" | "full";

export type RefreshSectionSummary = {
  path: string;
  rows?: number;
  rows_before?: number;
  rows_after?: number;
  rows_added?: number;
  symbols?: number;
  updated_symbols?: number;
  failed_symbols?: number;
  upserted_symbols?: number;
  warning?: string;
};

export type RefreshSummary = {
  mode: RefreshMode;
  daily: RefreshSectionSummary;
  names: RefreshSectionSummary;
  pe: RefreshSectionSummary;
};

/** POST /refresh 在冷却窗口内跳过执行时返回的 summary */
export type RefreshSkippedSummary = {
  skipped: true;
  reason: string;
  cooldown_hours: number;
  last_refresh_unix?: number | null;
  message?: string;
};

export type RefreshResponse = {
  status: "ok" | "skipped";
  mode: RefreshMode;
  summary: RefreshSummary | RefreshSkippedSummary;
};
