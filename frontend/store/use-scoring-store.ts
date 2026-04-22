"use client";

import { create } from "zustand";

import {
  ApiError,
  classifySymbol,
  fetchQuote,
  listStrategies,
  normalizeSymbol,
  scoreMarket,
  scoreSingle,
} from "@/lib/api";
import type {
  HistoryEntry,
  QuoteResponse,
  RankedStock,
  ScoreResponse,
  StrategyInfo,
  SymbolKind,
} from "@/types/scoring";

const HISTORY_KEY = "ddt.history.v1";
const HISTORY_LIMIT = 30;

function loadHistory(): HistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistoryEntry[];
    return Array.isArray(parsed) ? parsed.slice(0, HISTORY_LIMIT) : [];
  } catch {
    return [];
  }
}

function persistHistory(entries: HistoryEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(entries));
  } catch {
    // ignore quota errors
  }
}

function makeHistoryEntry(params: {
  symbol: string;
  name: string | null;
  strategy: StrategyInfo;
  totalScore: number | null;
  kind: SymbolKind;
}): HistoryEntry {
  return {
    id: `${params.symbol}-${params.strategy.id}-${Date.now()}`,
    symbol: params.symbol,
    name: params.name,
    strategyId: params.strategy.id,
    strategyName: params.strategy.name,
    totalScore: params.totalScore,
    kind: params.kind,
    analyzedAt: Date.now(),
  };
}

type TaskStage = "quote" | "scoring" | null;

type AnalyzeOptions = {
  suppressScore?: boolean; // ETF: skip /score
};

type ScoringStore = {
  strategies: StrategyInfo[];
  strategiesError: string | null;
  selectedStrategyId: string | null;

  isAnalyzing: boolean;
  taskStage: TaskStage;
  currentSymbol: string | null;
  error: string | null;

  quote: QuoteResponse | null;
  analysis: RankedStock | null;
  analysisMode: "single" | "etf-skip" | null;
  scoreUniverseSize: number | null;

  marketRanking: RankedStock[] | null;
  marketLoading: boolean;
  marketError: string | null;

  history: HistoryEntry[];
  selectedHistoryId: string | null;

  loadStrategies: () => Promise<void>;
  selectStrategy: (id: string) => void;

  analyzeSymbol: (input: string, options?: AnalyzeOptions) => Promise<void>;
  runMarketAnalysis: () => Promise<void>;
  closeMarketRanking: () => void;

  restoreHistory: (entryId: string) => Promise<void>;
  clearHistory: () => void;
};

function applyScoreRow(
  payload: ScoreResponse,
): { row: RankedStock | null; universe: number } {
  return {
    row: payload.top_50[0] ?? null,
    universe: payload.total_universe,
  };
}

export const useScoringStore = create<ScoringStore>((set, get) => ({
  strategies: [],
  strategiesError: null,
  selectedStrategyId: null,

  isAnalyzing: false,
  taskStage: null,
  currentSymbol: null,
  error: null,

  quote: null,
  analysis: null,
  analysisMode: null,
  scoreUniverseSize: null,

  marketRanking: null,
  marketLoading: false,
  marketError: null,

  history: typeof window === "undefined" ? [] : loadHistory(),
  selectedHistoryId: null,

  loadStrategies: async () => {
    try {
      const strategies = await listStrategies();
      set((state) => ({
        ...state,
        strategies,
        strategiesError: null,
        selectedStrategyId:
          state.selectedStrategyId ?? strategies[0]?.id ?? null,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载策略失败";
      set((state) => ({ ...state, strategiesError: message }));
    }
  },

  selectStrategy: (id) =>
    set((state) => ({ ...state, selectedStrategyId: id })),

  analyzeSymbol: async (input, options) => {
    const raw = input.trim();
    if (!raw) {
      set((state) => ({ ...state, error: "请输入股票或 ETF 代码" }));
      return;
    }

    let normalized: string;
    try {
      normalized = normalizeSymbol(raw);
    } catch (err) {
      const message = err instanceof Error ? err.message : "代码格式不正确";
      set((state) => ({ ...state, error: message }));
      return;
    }

    const strategyId = get().selectedStrategyId;
    if (!strategyId) {
      set((state) => ({ ...state, error: "请先选择一个评分策略" }));
      return;
    }
    const strategy = get().strategies.find((s) => s.id === strategyId);
    if (!strategy) {
      set((state) => ({ ...state, error: "策略列表未就绪" }));
      return;
    }

    const kind = classifySymbol(normalized);
    const suppressScore = options?.suppressScore ?? kind === "etf";

    set((state) => ({
      ...state,
      isAnalyzing: true,
      taskStage: "quote",
      currentSymbol: normalized,
      error: null,
      analysis: null,
      analysisMode: null,
      selectedHistoryId: null,
    }));

    let quote: QuoteResponse | null = null;
    try {
      quote = await fetchQuote(normalized);
      set((state) => ({ ...state, quote }));
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 404
            ? `代码 ${normalized} 不在本地缓存中，请先在后端执行 /refresh 刷新。`
            : err.message
          : err instanceof Error
            ? err.message
            : "报价获取失败";
      set((state) => ({
        ...state,
        isAnalyzing: false,
        taskStage: null,
        quote: null,
        error: message,
      }));
      return;
    }

    let analysis: RankedStock | null = null;
    let universe: number | null = null;
    let scoreError: string | null = null;
    let analysisMode: "single" | "etf-skip" = "single";

    if (suppressScore) {
      analysisMode = "etf-skip";
    } else {
      set((state) => ({ ...state, taskStage: "scoring" }));
      try {
        const payload = await scoreSingle(strategyId, normalized);
        const res = applyScoreRow(payload);
        analysis = res.row;
        universe = res.universe;
      } catch (err) {
        if (err instanceof ApiError && err.status === 400) {
          // ETF detected server-side → degrade to etf-skip
          analysisMode = "etf-skip";
        } else if (err instanceof ApiError && err.status === 404) {
          scoreError = `代码 ${normalized} 尚未在评分数据集中，可能还没刷 PE 或因子快照。`;
        } else {
          scoreError = err instanceof Error ? err.message : "评分失败";
        }
      }
    }

    const entry = makeHistoryEntry({
      symbol: normalized,
      name: quote?.name ?? null,
      strategy,
      totalScore: analysis?.total_score ?? null,
      kind,
    });

    set((state) => {
      const filtered = state.history.filter(
        (h) => !(h.symbol === entry.symbol && h.strategyId === entry.strategyId),
      );
      const nextHistory = [entry, ...filtered].slice(0, HISTORY_LIMIT);
      persistHistory(nextHistory);
      return {
        ...state,
        isAnalyzing: false,
        taskStage: null,
        analysis,
        analysisMode,
        scoreUniverseSize: universe,
        error: scoreError,
        history: nextHistory,
        selectedHistoryId: entry.id,
      };
    });
  },

  runMarketAnalysis: async () => {
    const strategyId = get().selectedStrategyId;
    if (!strategyId) {
      set((state) => ({ ...state, marketError: "请先选择一个评分策略" }));
      return;
    }
    set((state) => ({
      ...state,
      marketLoading: true,
      marketError: null,
      marketRanking: [],
    }));
    try {
      const payload = await scoreMarket(strategyId);
      set((state) => ({
        ...state,
        marketLoading: false,
        marketRanking: payload.top_50,
      }));
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 500
          ? `后端无法加载评分数据集，请确认 /refresh 已成功执行。(${err.message})`
          : err instanceof Error
            ? err.message
            : "全市场分析失败";
      set((state) => ({
        ...state,
        marketLoading: false,
        marketError: message,
        marketRanking: null,
      }));
    }
  },

  closeMarketRanking: () =>
    set((state) => ({
      ...state,
      marketRanking: null,
      marketError: null,
    })),

  restoreHistory: async (entryId) => {
    const entry = get().history.find((h) => h.id === entryId);
    if (!entry) return;
    set((state) => ({
      ...state,
      selectedHistoryId: entryId,
      selectedStrategyId: entry.strategyId,
    }));
    await get().analyzeSymbol(entry.symbol, {
      suppressScore: entry.kind === "etf",
    });
  },

  clearHistory: () => {
    persistHistory([]);
    set((state) => ({ ...state, history: [], selectedHistoryId: null }));
  },
}));
