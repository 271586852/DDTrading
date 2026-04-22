"use client";

import { History, Trash2 } from "lucide-react";

import { useScoringStore } from "@/store/use-scoring-store";
import type { HistoryEntry } from "@/types/scoring";

function formatTime(ts: number): string {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function scoreBadgeClass(entry: HistoryEntry): string {
  if (entry.kind === "etf" || entry.totalScore == null) {
    return "border-slate-600/40 bg-slate-700/20 text-slate-400";
  }
  const s = entry.totalScore;
  if (s >= 75) return "border-emerald-400/50 bg-emerald-500/15 text-emerald-200";
  if (s >= 60) return "border-cyan-400/50 bg-cyan-500/15 text-cyan-200";
  if (s >= 40) return "border-purple-400/50 bg-purple-500/15 text-purple-200";
  return "border-rose-400/50 bg-rose-500/15 text-rose-200";
}

function scoreLabel(entry: HistoryEntry): string {
  if (entry.kind === "etf") return "ETF";
  if (entry.totalScore == null) return "--";
  return entry.totalScore.toFixed(1);
}

export function HistoryList() {
  const history = useScoringStore((state) => state.history);
  const selected = useScoringStore((state) => state.selectedHistoryId);
  const restore = useScoringStore((state) => state.restoreHistory);
  const clear = useScoringStore((state) => state.clearHistory);

  return (
    <section className="glass-panel flex min-h-[280px] flex-1 flex-col rounded-[22px] p-5">
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/15 text-purple-300">
            <History className="h-4 w-4" strokeWidth={1.6} />
          </span>
          <h2 className="text-sm font-medium tracking-wide text-white">
            历史记录
          </h2>
        </div>
        {history.length > 0 && (
          <button
            type="button"
            onClick={clear}
            className="inline-flex items-center gap-1 rounded-full border border-white/5 px-2 py-1 text-[11px] text-slate-400 hover:border-rose-400/40 hover:text-rose-200"
          >
            <Trash2 className="h-3 w-3" strokeWidth={1.8} />
            清空
          </button>
        )}
      </header>

      {history.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-white/5 bg-slate-950/30 text-xs text-slate-500">
          暂无分析记录
        </div>
      ) : (
        <ul className="flex flex-col gap-2 overflow-y-auto pr-1">
          {history.map((entry) => {
            const isActive = entry.id === selected;
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => void restore(entry.id)}
                  className={
                    "flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition-all " +
                    (isActive
                      ? "border-cyan-400/60 bg-cyan-500/10 shadow-[0_0_18px_rgba(56,189,248,0.22)]"
                      : "border-white/5 bg-slate-950/40 hover:border-cyan-400/30 hover:bg-slate-900/50")
                  }
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-sm text-slate-100">
                      {entry.name ?? entry.symbol}
                    </span>
                    <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500">
                      <span className="font-mono text-slate-400">
                        {entry.symbol}
                      </span>
                      <span className="text-slate-600">·</span>
                      <span>{entry.strategyName}</span>
                      <span className="text-slate-600">·</span>
                      <span>{formatTime(entry.analyzedAt)}</span>
                    </span>
                  </div>
                  <span
                    className={
                      "shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-semibold " +
                      scoreBadgeClass(entry)
                    }
                  >
                    {scoreLabel(entry)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
