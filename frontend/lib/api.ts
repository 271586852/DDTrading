import type {
  BacktestRequest,
  BacktestReportRequest,
  BacktestResponse,
  TradeStrategyInfo,
} from "@/types/backtest";
import type {
  MarketScoreJobStarted,
  MarketScoreJobStatus,
  QuoteResponse,
  RefreshMode,
  RefreshResponse,
  ScoreResponse,
  StrategyInfo,
} from "@/types/scoring";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: string | unknown };
    if (typeof body.detail === "string") return body.detail;
    return fallback;
  } catch {
    return fallback;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    const message = await parseError(response);
    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export function listScoreStrategies(): Promise<StrategyInfo[]> {
  return request<StrategyInfo[]>("/score-strategies");
}

export function scoreMarket(strategyId: string): Promise<ScoreResponse> {
  return request<ScoreResponse>("/score", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId }),
  });
}

export function startMarketScoreJob(
  strategyId: string,
): Promise<MarketScoreJobStarted> {
  return request<MarketScoreJobStarted>("/score/market-job", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId }),
  });
}

export function getMarketScoreJob(
  jobId: string,
): Promise<MarketScoreJobStatus> {
  return request<MarketScoreJobStatus>(
    `/score/market-job/${encodeURIComponent(jobId)}`,
  );
}

export function scoreSingle(
  strategyId: string,
  symbol: string,
): Promise<ScoreResponse> {
  return request<ScoreResponse>("/score", {
    method: "POST",
    body: JSON.stringify({ strategy_id: strategyId, symbol }),
  });
}

export function fetchQuote(symbol: string, bars = 120): Promise<QuoteResponse> {
  const qs = new URLSearchParams({ bars: String(bars) }).toString();
  return request<QuoteResponse>(`/quote/${encodeURIComponent(symbol)}?${qs}`);
}

export function refreshMarketData(
  mode: RefreshMode = "incremental",
  options?: { force?: boolean },
): Promise<RefreshResponse> {
  const qs = new URLSearchParams({ mode });
  if (options?.force) {
    qs.set("force", "true");
  }
  return request<RefreshResponse>(`/refresh?${qs.toString()}`, {
    method: "POST",
  });
}

export function listTradeStrategies(): Promise<TradeStrategyInfo[]> {
  return request<TradeStrategyInfo[]>("/trade-strategies");
}

export function runBacktest(
  payload: BacktestRequest,
): Promise<BacktestResponse> {
  return request<BacktestResponse>("/backtest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function exportBacktestReport(
  payload: BacktestReportRequest,
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/backtest/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const message = await parseError(response);
    throw new ApiError(message, response.status);
  }
  return response.blob();
}

const STOCK_PREFIXES = [
  "60",
  "688",
  "000",
  "001",
  "002",
  "003",
  "300",
  "301",
];
const ETF_PREFIXES = ["15", "16", "50", "51", "52", "56", "58"];

export function normalizeSymbol(raw: string): string {
  const trimmed = raw.trim().toLowerCase().replace(/^(sh|sz|bj)/, "");
  const digits = trimmed.replace(/\D/g, "");
  if (!digits) throw new Error("请输入有效的股票/ETF 代码");
  return digits.slice(-6).padStart(6, "0");
}

export function classifySymbol(symbol: string): "stock" | "etf" | "unknown" {
  const code = symbol.padStart(6, "0");
  if (STOCK_PREFIXES.some((p) => code.startsWith(p))) return "stock";
  if (ETF_PREFIXES.some((p) => code.startsWith(p))) return "etf";
  return "unknown";
}
