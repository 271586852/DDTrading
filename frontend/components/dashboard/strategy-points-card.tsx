"use client";

import { Crosshair, ShieldAlert, Target, TrendingUp } from "lucide-react";

type Point = {
  label: string;
  icon: React.ReactNode;
  tone: string;
  ring: string;
};

const POINTS: Point[] = [
  {
    label: "理想买入",
    icon: <Crosshair className="h-4 w-4" strokeWidth={1.6} />,
    tone: "text-emerald-300",
    ring: "border-emerald-400/30",
  },
  {
    label: "二次买入",
    icon: <Target className="h-4 w-4" strokeWidth={1.6} />,
    tone: "text-cyan-300",
    ring: "border-cyan-400/30",
  },
  {
    label: "止损价位",
    icon: <ShieldAlert className="h-4 w-4" strokeWidth={1.6} />,
    tone: "text-rose-300",
    ring: "border-rose-400/30",
  },
  {
    label: "止盈目标",
    icon: <TrendingUp className="h-4 w-4" strokeWidth={1.6} />,
    tone: "text-amber-300",
    ring: "border-amber-400/30",
  },
];

export function StrategyPointsCard() {
  return (
    <article className="glass-panel rounded-[24px] p-5">
      <header className="mb-4 flex items-baseline justify-between">
        <div className="flex flex-col">
          <span className="text-[11px] uppercase tracking-[0.35em] text-slate-500">
            Strategy Points
          </span>
          <h3 className="mt-1 text-sm font-medium tracking-wide text-white">
            狙击点位
          </h3>
        </div>
        <span className="text-[11px] text-slate-500">待模型接入</span>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {POINTS.map((p) => (
          <div
            key={p.label}
            className={
              `group flex flex-col gap-2 rounded-xl border ${p.ring} bg-slate-950/40 px-4 py-3 transition-all hover:bg-slate-900/50`
            }
          >
            <div className="flex items-center gap-2 text-slate-400">
              <span className={`${p.tone}`}>{p.icon}</span>
              <span className="text-[11px] uppercase tracking-[0.2em]">
                {p.label}
              </span>
            </div>
            <span className={`text-2xl font-semibold tabular-nums ${p.tone}`}>
              --
            </span>
          </div>
        ))}
      </div>
    </article>
  );
}
