"use client";

import { Sparkles } from "lucide-react";
import { useEffect } from "react";

import { useScoringStore } from "@/store/use-scoring-store";

export function StrategyPicker() {
  const strategies = useScoringStore((state) => state.strategies);
  const loadStrategies = useScoringStore((state) => state.loadStrategies);
  const selected = useScoringStore((state) => state.selectedStrategyId);
  const selectStrategy = useScoringStore((state) => state.selectStrategy);
  const error = useScoringStore((state) => state.strategiesError);

  useEffect(() => {
    if (strategies.length === 0) {
      void loadStrategies();
    }
  }, [strategies.length, loadStrategies]);

  return (
    <section className="glass-panel rounded-[22px] p-5">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500/15 text-cyan-300">
            <Sparkles className="h-4 w-4" strokeWidth={1.6} />
          </span>
          <h2 className="text-sm font-medium tracking-wide text-white">
            策略列表
          </h2>
        </div>
        <span className="text-[11px] uppercase tracking-[0.3em] text-slate-500">
          {strategies.length ? `${strategies.length} presets` : "loading..."}
        </span>
      </header>

      {error && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {strategies.map((s) => {
          const isActive = s.id === selected;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => selectStrategy(s.id)}
              className={
                "group relative flex flex-col gap-1 rounded-xl border px-3 py-2.5 text-left transition-all " +
                (isActive
                  ? "border-cyan-400/70 bg-cyan-500/10 shadow-[0_0_22px_rgba(56,189,248,0.25)]"
                  : "border-white/5 bg-slate-950/40 hover:border-cyan-400/40 hover:bg-slate-900/50")
              }
            >
              <div className="flex items-center justify-between">
                <span
                  className={
                    "text-sm font-medium " +
                    (isActive ? "text-cyan-100" : "text-slate-200")
                  }
                >
                  {s.name}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  {s.id}
                </span>
              </div>
              <p className="text-xs leading-relaxed text-slate-400 line-clamp-2">
                {s.description}
              </p>
            </button>
          );
        })}
      </div>
    </section>
  );
}
