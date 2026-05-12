"use client";

import { AlertTriangle, Clock, Hash, TrendingDown, TrendingUp } from "lucide-react";

import {
  factorKeysInOrder,
  formatFactorCellDisplay,
  labelForFactor,
  percentileFromMeta,
  zscoreToPercentile,
} from "@/lib/score-factors";
import { useScoringStore } from "@/store/use-scoring-store";
import type { FactorFieldInfo } from "@/types/scoring";

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
  const selectedStrategyId = useScoringStore((state) => state.selectedStrategyId);
  const strategies = useScoringStore((state) => state.strategies);
  const strategy = strategies.find((s) => s.id === selectedStrategyId);

  const hasData = Boolean(quote || currentSymbol);
  const isUp = (quote?.change_pct ?? 0) > 0;
  const isDown = (quote?.change_pct ?? 0) < 0;

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
                ETF 暂不适用当前预设评分策略。下方行情与 K 线仍可用于参考或回测。
              </p>
            ) : analysis ? (
              <SingleScoreInsight
                score={analysis.total_score}
                zscores={analysis.factor_zscores}
                values={analysis.factor_values}
                universeSize={universeSize}
                factorFields={strategy?.factor_fields}
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
  zscores: Record<string, number> | null | undefined;
  values: Record<string, number> | null | undefined;
  universeSize: number | null;
  factorFields: FactorFieldInfo[] | undefined;
}) {
  const { score, zscores, values, universeSize, factorFields } = props;

  const scoreColor =
    score >= 75
      ? "text-emerald-300"
      : score >= 60
        ? "text-cyan-300"
        : score >= 40
          ? "text-purple-300"
          : "text-rose-300";

  const metaByKey = new Map(factorFields?.map((f) => [f.key, f]));

  const keysOrdered =
    factorFields?.length && values && typeof values === "object"
      ? factorFields
          .map((f) => f.key)
          .filter((k) => typeof values[k] === "number")
      : factorKeysInOrder(values);

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
          {universeSize
            ? `全市场 ${universeSize} 只（当前策略可评分样本）`
            : "由当前所选策略独立计算"}
        </span>
      </div>

      {keysOrdered.length === 0 ? (
        <p className="text-sm leading-relaxed text-slate-500">
          当前策略未返回分项指标，仅展示相对综合分。
        </p>
      ) : (
        <div
          className={
            keysOrdered.length >= 3
              ? "grid grid-cols-3 gap-2"
              : "grid grid-cols-1 gap-2 sm:grid-cols-2"
          }
        >
          {keysOrdered.map((key) => {
            const val = values![key];
            const meta = metaByKey.get(key);
            const display = formatFactorCellDisplay(meta, values, key);
            const { percentile, hint } = percentileFromMeta(
              meta,
              val,
              zscores?.[key],
              zscoreToPercentile,
            );
            return (
              <FactorCell
                key={key}
                label={labelForFactor(factorFields, key)}
                value={display}
                percentile={percentile}
                hint={hint}
              />
            );
          })}
        </div>
      )}
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
        <span className="font-mono text-slate-300">
          {props.percentile === "—" ? "—" : `${props.percentile}%`}
        </span>
      </div>
    </div>
  );
}
