"use client";

import {
  Calendar,
  Coins,
  Download,
  Hash,
  Loader2,
  Play,
  Sparkles,
} from "lucide-react";
import { useEffect } from "react";

import { useBacktestStore } from "@/store/use-backtest-store";

export function BacktestForm() {
  const form = useBacktestStore((s) => s.form);
  const setForm = useBacktestStore((s) => s.setForm);
  const strategies = useBacktestStore((s) => s.strategies);
  const strategiesError = useBacktestStore((s) => s.strategiesError);
  const loadStrategies = useBacktestStore((s) => s.loadStrategies);
  const run = useBacktestStore((s) => s.runBacktest);
  const exportReport = useBacktestStore((s) => s.exportReport);
  const isRunning = useBacktestStore((s) => s.isRunning);
  const error = useBacktestStore((s) => s.error);

  useEffect(() => {
    if (strategies.length === 0) {
      void loadStrategies();
    }
  }, [strategies.length, loadStrategies]);

  return (
    <section className="glass-panel neon-ring flex flex-col gap-5 rounded-[24px] p-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/15 text-cyan-300">
            <Sparkles className="h-4 w-4" strokeWidth={1.6} />
          </span>
          <div className="flex flex-col">
            <h2 className="text-sm font-medium tracking-wide text-white">
              回测配置
            </h2>
            <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">
              Backtest Config
            </p>
          </div>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
          {strategies.length} strategies
        </span>
      </header>

      {strategiesError && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {strategiesError}
        </p>
      )}

      <div className="grid gap-3">
        <Field icon={<Hash className="h-4 w-4" strokeWidth={1.6} />} label="代码">
          <input
            value={form.symbol}
            onChange={(e) => setForm({ symbol: e.target.value })}
            placeholder="如 600000 / 000001 / 510300"
            className="flex-1 bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
          />
        </Field>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field icon={<Calendar className="h-4 w-4" strokeWidth={1.6} />} label="开始">
            <input
              type="date"
              value={form.startDate}
              onChange={(e) => setForm({ startDate: e.target.value })}
              className="flex-1 bg-transparent text-sm text-white outline-none [color-scheme:dark]"
            />
          </Field>
          <Field icon={<Calendar className="h-4 w-4" strokeWidth={1.6} />} label="结束">
            <input
              type="date"
              value={form.endDate}
              onChange={(e) => setForm({ endDate: e.target.value })}
              className="flex-1 bg-transparent text-sm text-white outline-none [color-scheme:dark]"
            />
          </Field>
        </div>

        <Field icon={<Coins className="h-4 w-4" strokeWidth={1.6} />} label="初始资金">
          <input
            type="number"
            min={1000}
            step={1000}
            value={form.initialCash}
            onChange={(e) =>
              setForm({ initialCash: Number.parseFloat(e.target.value || "0") })
            }
            className="flex-1 bg-transparent text-sm tabular-nums text-white outline-none"
          />
          <span className="text-xs text-slate-500">CNY</span>
        </Field>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.3em] text-cyan-300/80">
          交易策略
        </span>
        <div className="grid gap-2">
          {strategies.map((s) => {
            const isActive = s.id === form.strategyId;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => setForm({ strategyId: s.id })}
                className={
                  "group flex flex-col gap-1 rounded-xl border px-3 py-2.5 text-left transition-all " +
                  (isActive
                    ? "border-cyan-400/70 bg-cyan-500/10 shadow-[0_0_18px_rgba(56,189,248,0.25)]"
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
      </div>

      {error && (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          {error}
        </p>
      )}

      <div className="grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          onClick={() => void run()}
          disabled={isRunning}
          className={
            "inline-flex h-12 items-center justify-center gap-2 rounded-2xl px-6 text-sm font-medium tracking-wide transition-all " +
            "bg-gradient-to-r from-cyan-500/90 via-cyan-400/90 to-sky-400/90 text-slate-950 shadow-[0_0_28px_rgba(56,189,248,0.35)] " +
            "hover:shadow-[0_0_34px_rgba(56,189,248,0.55)] " +
            "disabled:opacity-50 disabled:shadow-none disabled:cursor-not-allowed"
          }
        >
          {isRunning ? (
            <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
          ) : (
            <Play className="h-4 w-4" strokeWidth={1.8} />
          )}
          {isRunning ? "回测中…" : "运行回测"}
        </button>
        <button
          type="button"
          onClick={() => void exportReport("D")}
          disabled={isRunning}
          className="inline-flex h-12 items-center justify-center gap-2 rounded-2xl border border-cyan-400/35 bg-cyan-500/10 px-6 text-sm font-medium tracking-wide text-cyan-100 transition-all hover:border-cyan-300/55 hover:bg-cyan-400/15 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Download className="h-4 w-4" strokeWidth={1.8} />
          导出 HTML 报告
        </button>
      </div>
    </section>
  );
}

function Field({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-[0.3em] text-slate-500">
        {label}
      </span>
      <div className="flex items-center gap-2 rounded-2xl border border-white/5 bg-slate-950/60 px-4 py-2.5 transition-all focus-within:border-cyan-400/60 focus-within:shadow-[0_0_18px_rgba(56,189,248,0.25)]">
        <span className="text-slate-400">{icon}</span>
        {children}
      </div>
    </label>
  );
}
