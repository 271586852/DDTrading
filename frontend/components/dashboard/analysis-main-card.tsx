"use client";

import { AlertTriangle, Clock, Hash, TrendingDown, TrendingUp } from "lucide-react";

import { useScoringStore } from "@/store/use-scoring-store";

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function AnalysisMainCard() {
  const quote = useScoringStore((state) => state.quote);
  const currentSymbol = useScoringStore((state) => state.currentSymbol);
  const analysis = useScoringStore((state) => state.analysis);
  const analysisMode = useScoringStore((state) => state.analysisMode);
  const scoreError = useScoringStore((state) => state.error);
  const isAnalyzing = useScoringStore((state) => state.isAnalyzing);
  const universeSize = useScoringStore((state) => state.scoreUniverseSize);

  const hasData = Boolean(quote || currentSymbol);
  const isUp = (quote?.change_pct ?? 0) > 0;
  const isDown = (quote?.change_pct ?? 0) < 0;

  // A 股涨跌色：涨红跌绿（与国内交易软件一致）
  const priceColor = isUp
    ? "text-rose-300"
    : isDown
      ? "text-emerald-300"
      : "text-slate-200";

  return (
    <article
      className="glass-panel relative overflow-hidden rounded-[24px] border border-cyan-500/20 p-6 shadow-[0_0_40px_rgba(34,211,238,0.12)]"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -right-24 h-64 w-64 rounded-full bg-cyan-500/15 blur-3xl"
      />

      {!hasData ? (
        <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-center">
          <h3 className="text-lg font-medium text-slate-200">
            选择策略 + 搜索代码，开始量化分析
          </h3>
          <p className="max-w-md text-sm text-slate-500">
            在顶部搜索框输入股票或 ETF 代码，或点击右侧「全市场分析」触发全市场评分。
          </p>
        </div>
      ) : (
        <div className="relative flex flex-col gap-4">
          <header className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <h2 className="text-2xl font-semibold tracking-wide text-white">
                {quote?.name ?? "--"}
              </h2>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <Hash className="h-3 w-3" strokeWidth={1.8} />
                  <span className="font-mono text-slate-400">
                    {quote?.symbol ?? currentSymbol ?? "--"}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1">
                  <Clock className="h-3 w-3" strokeWidth={1.8} />
                  {quote?.as_of_date ?? "--"}
                </span>
                {quote?.kind === "etf" && (
                  <span className="rounded-full border border-amber-400/40 bg-amber-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-200">
                    ETF
                  </span>
                )}
              </div>
            </div>

            <div className="flex flex-col items-end">
              <span className={`text-3xl font-semibold tabular-nums ${priceColor}`}>
                {formatNumber(quote?.latest_close ?? null)}
              </span>
              <span
                className={
                  "mt-1 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs tabular-nums " +
                  (isUp
                    ? "border-rose-400/40 bg-rose-500/10 text-rose-200"
                    : isDown
                      ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
                      : "border-white/10 bg-slate-800/40 text-slate-300")
                }
              >
                {isUp ? (
                  <TrendingUp className="h-3 w-3" strokeWidth={2} />
                ) : isDown ? (
                  <TrendingDown className="h-3 w-3" strokeWidth={2} />
                ) : null}
                {formatPct(quote?.change_pct ?? null)}
              </span>
            </div>
          </header>

          <div className="h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent" />

          <section className="flex flex-col gap-2">
            <span className="text-[11px] font-medium uppercase tracking-[0.35em] text-cyan-300/80">
              Key Insights
            </span>
            {scoreError ? (
              <p className="inline-flex items-start gap-2 rounded-xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.8} />
                {scoreError}
              </p>
            ) : analysisMode === "etf-skip" ? (
              <p className="text-sm leading-relaxed text-slate-400">
                ETF 标的暂不适用多因子评分（缺少 PE 估值因子）。下方的行情与 K 线仍然可用，可用于回测或趋势参考。
              </p>
            ) : analysis ? (
              <SingleScoreInsight
                score={analysis.total_score}
                zscores={analysis.factor_zscores}
                values={analysis.factor_values}
                universeSize={universeSize}
              />
            ) : isAnalyzing ? (
              <p className="text-sm text-slate-500">正在计算评分…</p>
            ) : (
              <p className="text-sm leading-relaxed text-slate-500">
                —— 暂无分析摘要 ——
              </p>
            )}
          </section>
        </div>
      )}
    </article>
  );
}

function SingleScoreInsight(props: {
  score: number;
  zscores: { pe_ratio: number; momentum_20d: number; volatility: number };
  values: { pe_ratio: number; momentum_20d: number; volatility: number };
  universeSize: number | null;
}) {
  const { score, zscores, values, universeSize } = props;

  const scoreColor =
    score >= 75
      ? "text-emerald-300"
      : score >= 60
        ? "text-cyan-300"
        : score >= 40
          ? "text-purple-300"
          : "text-rose-300";

  const pct = (zs: number) => {
    // 近似把 z-score 映射到百分位（便于直观比较）
    const p = 0.5 * (1 + erf(zs / Math.SQRT2));
    return (p * 100).toFixed(0);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-4">
        <div className="flex flex-col">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            综合评分
          </span>
          <span className={`text-5xl font-bold tabular-nums ${scoreColor}`}>
            {score.toFixed(1)}
          </span>
        </div>
        <span className="pb-1 text-xs text-slate-500">
          {universeSize ? `全市场 ${universeSize} 只同口径样本` : "基于全市场 z-score"}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <FactorCell
          label="PE"
          value={values.pe_ratio.toFixed(2)}
          percentile={pct(-zscores.pe_ratio) /* 低 PE 分位高 */}
          hint="低估值"
        />
        <FactorCell
          label="Momentum 20d"
          value={`${(values.momentum_20d * 100).toFixed(2)}%`}
          percentile={pct(zscores.momentum_20d)}
          hint="近 20 日强势"
        />
        <FactorCell
          label="Volatility"
          value={`${(values.volatility * 100).toFixed(2)}%`}
          percentile={pct(-zscores.volatility) /* 低波动分位高 */}
          hint="低波动"
        />
      </div>
    </div>
  );
}

function FactorCell(props: {
  label: string;
  value: string;
  percentile: string;
  hint: string;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-white/5 bg-slate-950/40 px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
          {props.label}
        </span>
        <span className="text-[10px] text-slate-500">{props.hint}</span>
      </div>
      <span className="tabular-nums text-sm text-slate-100">{props.value}</span>
      <div className="flex items-center justify-between text-[11px] text-slate-500">
        <span>分位</span>
        <span className="font-mono text-slate-300">{props.percentile}%</span>
      </div>
    </div>
  );
}

// 误差函数近似，供 z-score -> 百分位可视化使用
function erf(x: number): number {
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1.0 / (1.0 + p * ax);
  const y =
    1.0 -
    ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return sign * y;
}
