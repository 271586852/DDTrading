"use client";

import { Loader2, X } from "lucide-react";
import { useEffect } from "react";

import { useScoringStore } from "@/store/use-scoring-store";
import type { RankedStock } from "@/types/scoring";

export function MarketAnalysisDialog() {
  const ranking = useScoringStore((state) => state.marketRanking);
  const loading = useScoringStore((state) => state.marketLoading);
  const error = useScoringStore((state) => state.marketError);
  const close = useScoringStore((state) => state.closeMarketRanking);
  const selectedStrategyId = useScoringStore((state) => state.selectedStrategyId);
  const strategies = useScoringStore((state) => state.strategies);

  const strategy = strategies.find((s) => s.id === selectedStrategyId);
  const open = ranking !== null || loading || Boolean(error);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal
      className="fixed inset-0 z-40 flex items-center justify-center p-4"
    >
      <div
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
        onClick={close}
      />
      <div
        className="glass-panel relative z-10 flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-[24px] border border-purple-400/30 shadow-[0_0_60px_rgba(168,85,247,0.2)]"
      >
        <header className="flex items-start justify-between gap-4 border-b border-white/5 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold tracking-wide text-white">
              全市场分析
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              策略：
              <span className="ml-1 text-purple-200">
                {strategy?.name ?? "--"}
              </span>
              <span className="ml-2 font-mono text-slate-600">
                {strategy?.id}
              </span>
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            className="rounded-full border border-white/5 bg-slate-900/40 p-2 text-slate-400 hover:border-rose-400/40 hover:text-rose-200"
            aria-label="关闭"
          >
            <X className="h-4 w-4" strokeWidth={1.8} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center gap-2 px-6 py-16 text-sm text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
              后端正在基于本地 parquet 计算全市场评分…
            </div>
          )}
          {error && (
            <div className="mx-6 my-10 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {error}
            </div>
          )}
          {ranking && !loading && !error && (
            <RankingTable rows={ranking} />
          )}
        </div>
      </div>
    </div>
  );
}

function RankingTable({ rows }: { rows: RankedStock[] }) {
  if (rows.length === 0) {
    return (
      <div className="px-6 py-10 text-center text-sm text-slate-500">
        没有命中的标的
      </div>
    );
  }

  return (
    <table className="w-full table-fixed text-sm">
      <thead className="sticky top-0 bg-slate-950/90 backdrop-blur">
        <tr className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
          <th className="w-14 px-4 py-3 text-left">#</th>
          <th className="w-24 px-3 py-3 text-left">代码</th>
          <th className="px-3 py-3 text-left">名称</th>
          <th className="w-28 px-3 py-3 text-right">综合评分</th>
          <th className="w-24 px-3 py-3 text-right">PE</th>
          <th className="w-32 px-3 py-3 text-right">Momentum 20d</th>
          <th className="w-28 px-3 py-3 text-right">Volatility</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={`${row.rank}-${row.ticker}`}
            className="border-t border-white/5 hover:bg-white/[0.02]"
          >
            <td className="px-4 py-2.5 text-slate-500">#{row.rank}</td>
            <td className="px-3 py-2.5 font-mono text-slate-300">{row.ticker}</td>
            <td className="px-3 py-2.5 text-slate-100">{row.name}</td>
            <td
              className={
                "px-3 py-2.5 text-right font-semibold tabular-nums " +
                scoreToneClass(row.total_score)
              }
            >
              {row.total_score.toFixed(1)}
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">
              {row.factor_values.pe_ratio.toFixed(2)}
            </td>
            <td
              className={
                "px-3 py-2.5 text-right tabular-nums " +
                (row.factor_values.momentum_20d >= 0
                  ? "text-rose-300"
                  : "text-emerald-300")
              }
            >
              {(row.factor_values.momentum_20d * 100).toFixed(2)}%
            </td>
            <td className="px-3 py-2.5 text-right tabular-nums text-slate-300">
              {(row.factor_values.volatility * 100).toFixed(2)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function scoreToneClass(score: number): string {
  if (score >= 75) return "text-emerald-300";
  if (score >= 60) return "text-cyan-300";
  if (score >= 40) return "text-purple-300";
  return "text-rose-300";
}
