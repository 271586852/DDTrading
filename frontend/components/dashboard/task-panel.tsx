"use client";

import { Activity, Loader2 } from "lucide-react";

import { useScoringStore } from "@/store/use-scoring-store";

export function TaskPanel() {
  const isAnalyzing = useScoringStore((state) => state.isAnalyzing);
  const currentSymbol = useScoringStore((state) => state.currentSymbol);
  const stage = useScoringStore((state) => state.taskStage);
  const quoteName = useScoringStore((state) => state.quote?.name ?? null);

  const activeCount = isAnalyzing ? 1 : 0;
  const stageText =
    stage === "quote"
      ? "拉取行情中..."
      : stage === "scoring"
        ? "应用策略评分..."
        : "正在分析中...";

  return (
    <section className="glass-panel rounded-[22px] p-5">
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-300">
            <Activity className="h-4 w-4" strokeWidth={1.6} />
          </span>
          <h2 className="text-sm font-medium tracking-wide text-white">
            分析任务
          </h2>
        </div>
        <span
          className={
            "rounded-full px-2 py-0.5 text-[11px] " +
            (activeCount > 0
              ? "border border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
              : "border border-white/5 bg-slate-900/50 text-slate-500")
          }
        >
          {activeCount}进行中
        </span>
      </header>

      {isAnalyzing && currentSymbol ? (
        <div className="flex items-center justify-between rounded-xl border border-cyan-400/30 bg-cyan-500/5 px-3 py-3">
          <div className="flex flex-col">
            <span className="font-mono text-sm text-cyan-100">
              {currentSymbol}
            </span>
            <span className="text-xs text-slate-400">
              {quoteName ?? "—"} · {stageText}
            </span>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-400/40 bg-cyan-500/15 px-2.5 py-1 text-[11px] text-cyan-200">
            <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.8} />
            分析中
          </span>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-white/5 bg-slate-950/40 px-3 py-4 text-center text-xs text-slate-500">
          当前没有进行中的任务
        </div>
      )}
    </section>
  );
}
