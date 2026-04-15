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

export type ScoreResponse = {
  normalized_weights: FactorWeights;
  total_universe: number;
  returned_count: number;
  top_50: RankedStock[];
};
