"use client";

import { create } from "zustand";

import {
  ApiError,
  classifySymbol,
  fetchQuote,
  getMarketDataRevision,
  getMarketScoreJob,
  listScoreStrategies,
  normalizeSymbol,
  scoreSingle,
  startMarketScoreJob,
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
const SCORE_CACHE_KEY = "ddt.score-cache.v1";
const SCORE_CACHE_LIMIT = 120;

/** 全市场评分结果（按策略），与单股 SCORE_CACHE 分开存储 */
const MARKET_SCORE_CACHE_KEY = "ddt.market-score.v1";
/** 最多保留多少个策略的缓存条目（LRU 按 cachedAt） */
const MARKET_SCORE_CACHE_MAX_STRATEGIES = 12;

type MarketScoreCached = {
  strategyId: string;
  /** 与后端 market_data_revision 一致；仅当与当前 GET /market-data-revision 相等时视为命中 */
  dataRevision: number;
  cachedAt: number;
  result: Pick<
    ScoreResponse,
    "top_50" | "total_universe" | "returned_count" | "mode"
  > & { applied_strategy?: StrategyInfo | null };
};

type MarketScoreCacheRoot = {
  v: 1;
  byStrategy: Record<string, MarketScoreCached>;
};

function loadMarketScoreCacheRoot(): MarketScoreCacheRoot {
  if (typeof window === "undefined") return { v: 1, byStrategy: {} };
  try {
    const raw = window.localStorage.getItem(MARKET_SCORE_CACHE_KEY);
    if (!raw) return { v: 1, byStrategy: {} };
    const parsed = JSON.parse(raw) as MarketScoreCacheRoot;
    if (parsed?.v !== 1 || typeof parsed.byStrategy !== "object") {
      return { v: 1, byStrategy: {} };
    }
    return parsed;
  } catch {
    return { v: 1, byStrategy: {} };
  }
}

function loadMarketScoreCache(strategyId: string): MarketScoreCached | null {
  const root = loadMarketScoreCacheRoot();
  const c = root.byStrategy[strategyId];
  if (!c || c.strategyId !== strategyId) return null;
  if (typeof c.dataRevision !== "number" || Number.isNaN(c.dataRevision)) {
    return null;
  }
  if (!Array.isArray(c.result?.top_50) || c.result.top_50.length === 0) {
    return null;
  }
  return c;
}

function persistMarketScoreCache(strategyId: string, result: ScoreResponse): void {
  if (typeof window === "undefined") return;
  try {
    const root = loadMarketScoreCacheRoot();
    root.byStrategy[strategyId] = {
      strategyId,
      dataRevision: Number(result.market_data_revision ?? 0),
      cachedAt: Date.now(),
      result: {
        top_50: result.top_50,
        total_universe: result.total_universe,
        returned_count: result.returned_count,
        mode: result.mode,
        applied_strategy: result.applied_strategy ?? null,
      },
    };
    const sorted = Object.entries(root.byStrategy).sort(
      (a, b) => b[1].cachedAt - a[1].cachedAt,
    );
    root.byStrategy = Object.fromEntries(
      sorted.slice(0, MARKET_SCORE_CACHE_MAX_STRATEGIES),
    );
    window.localStorage.setItem(
      MARKET_SCORE_CACHE_KEY,
      JSON.stringify(root),
    );
  } catch {
    // ignore quota / private mode
  }
}

type ScoreCacheMode = "single" | "etf-skip";

type ScoreCacheEntry = {
  key: string;
  symbol: string;
  strategyId: string;
  asOfDate: string;
  quote: QuoteResponse;
  analysis: RankedStock | null;
  analysisMode: ScoreCacheMode;
  scoreUniverseSize: number | null;
  cachedAt: number;
};

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

function loadScoreCache(): ScoreCacheEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SCORE_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ScoreCacheEntry[];
    return Array.isArray(parsed) ? parsed.slice(0, SCORE_CACHE_LIMIT) : [];
  } catch {
    return [];
  }
}

function persistScoreCache(entries: ScoreCacheEntry[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      SCORE_CACHE_KEY,
      JSON.stringify(entries.slice(0, SCORE_CACHE_LIMIT)),
    );
  } catch {
    // ignore quota errors
  }
}

function makeScoreCacheKey(
  symbol: string,
  strategyId: string,
  asOfDate: string | null | undefined,
): string {
  return `${symbol}::${strategyId}::${asOfDate ?? ""}`;
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
  /** 用于在用户关闭弹窗时作废正在轮询的全市场任务 */
  marketGeneration: number;
  marketProgress: number;
  marketStage: string | null;

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
  marketGeneration: 0,
  marketProgress: 0,
  marketStage: null,

  history: typeof window === "undefined" ? [] : loadHistory(),
  selectedHistoryId: null,

  loadStrategies: async () => {
    try {
      const strategies = await listScoreStrategies();
      set((state) => {
        const ids = new Set(strategies.map((s) => s.id));
        const prev = state.selectedStrategyId;
        const next =
          prev && ids.has(prev) ? prev : null;
        return {
          ...state,
          strategies,
          strategiesError: null,
          selectedStrategyId: next,
        };
      });
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
            ? `代码 ${normalized} 暂无可用行情（后端已尝试按需补单股）。请稍后重试或手动执行 /refresh。`
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
    const cacheKey = makeScoreCacheKey(
      normalized,
      strategyId,
      quote?.as_of_date ?? "",
    );

    if (suppressScore) {
      analysisMode = "etf-skip";
    } else {
      const cached = loadScoreCache().find((entry) => entry.key === cacheKey);
      if (cached) {
        analysis = cached.analysis;
        universe = cached.scoreUniverseSize;
        analysisMode = cached.analysisMode;
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
            scoreError = `代码 ${normalized} 评分失败（可能本地日线不足 30 根或缓存未就绪）。`;
          } else {
            scoreError = err instanceof Error ? err.message : "评分失败";
          }
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
      if (!scoreError) {
        const nextCache = [
          {
            key: cacheKey,
            symbol: normalized,
            strategyId,
            asOfDate: quote?.as_of_date ?? "",
            quote: quote as QuoteResponse,
            analysis,
            analysisMode,
            scoreUniverseSize: universe,
            cachedAt: Date.now(),
          },
          ...loadScoreCache().filter((item) => item.key !== cacheKey),
        ];
        persistScoreCache(nextCache);
      }
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

    let currentRevision: number;
    try {
      const rev = await getMarketDataRevision();
      currentRevision = Number(rev.market_data_revision);
      if (Number.isNaN(currentRevision)) {
        currentRevision = Number.NaN;
      }
    } catch {
      currentRevision = Number.NaN;
    }

    const cached = loadMarketScoreCache(strategyId);
    const cacheFresh =
      cached !== null &&
      !Number.isNaN(currentRevision) &&
      cached.dataRevision === currentRevision;

    let session = 0;
    set((state) => {
      session = state.marketGeneration + 1;
      if (cacheFresh) {
        const t = new Date(cached!.cachedAt).toLocaleString();
        return {
          ...state,
          marketGeneration: session,
          marketLoading: false,
          marketError: null,
          marketRanking: cached!.result.top_50,
          marketProgress: 100,
          marketStage: `来自本地缓存（${t}，全市场数据版本未变）`,
        };
      }
      return {
        ...state,
        marketGeneration: session,
        marketLoading: true,
        marketError: null,
        marketRanking: [],
        marketProgress: 0,
        marketStage: "正在创建任务…",
      };
    });

    if (cacheFresh) {
      return;
    }

    const stale = () => get().marketGeneration !== session;

    const fail = (message: string) => {
      if (stale()) return;
      set((state) => ({
        ...state,
        marketLoading: false,
        marketError: message,
        marketRanking: null,
        marketStage: null,
      }));
    };

    let jobId: string;
    try {
      const started = await startMarketScoreJob(strategyId);
      jobId = started.job_id;
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 500
          ? `后端无法启动评分任务，请确认 /refresh 已成功执行。(${err.message})`
          : err instanceof Error
            ? err.message
            : "全市场分析失败";
      fail(message);
      return;
    }

    const deadline = Date.now() + 30 * 60 * 1000;
    const pollMs = 400;

    try {
      while (Date.now() < deadline) {
        if (stale()) return;
        let status;
        try {
          status = await getMarketScoreJob(jobId);
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            fail("任务不存在或已过期，请重试。");
            return;
          }
          throw err;
        }
        if (stale()) return;
        set((state) => ({
          ...state,
          marketProgress: status.progress,
          marketStage: status.stage || null,
        }));
        if (status.status === "completed") {
          if (!status.result?.top_50) {
            fail("任务已完成但未返回评分结果。");
            return;
          }
          persistMarketScoreCache(strategyId, status.result);
          set((state) => ({
            ...state,
            marketLoading: false,
            marketRanking: status.result!.top_50,
            marketProgress: 100,
            marketStage: "完成",
          }));
          return;
        }
        if (status.status === "failed") {
          const detail = status.error ?? "全市场分析失败";
          fail(
            detail.includes("dataset") || detail.includes("parquet")
              ? `后端无法加载评分数据集，请确认 /refresh 已成功执行。（${detail}）`
              : detail,
          );
          return;
        }
        await new Promise((r) => setTimeout(r, pollMs));
      }
      fail("全市场分析超时（超过 30 分钟），请检查后端日志或缩小股票池后重试。");
    } catch (err) {
      const message = err instanceof Error ? err.message : "全市场分析失败";
      fail(message);
    }
  },

  closeMarketRanking: () =>
    set((state) => ({
      ...state,
      marketGeneration: state.marketGeneration + 1,
      marketRanking: null,
      marketError: null,
      marketLoading: false,
      marketProgress: 0,
      marketStage: null,
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
