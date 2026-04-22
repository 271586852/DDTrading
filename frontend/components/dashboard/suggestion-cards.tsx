"use client";

import { Compass, LineChart } from "lucide-react";

export function SuggestionCards() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <SuggestionCard
        icon={<Compass className="h-4 w-4" strokeWidth={1.6} />}
        accent="text-cyan-200"
        ring="border-cyan-400/25"
        glow="shadow-[0_0_24px_rgba(56,189,248,0.12)]"
        label="操作建议"
        conclusion="--"
        hint="暂未接入"
      />
      <SuggestionCard
        icon={<LineChart className="h-4 w-4" strokeWidth={1.6} />}
        accent="text-purple-200"
        ring="border-purple-400/25"
        glow="shadow-[0_0_24px_rgba(168,85,247,0.12)]"
        label="趋势预测"
        conclusion="--"
        hint="暂未接入"
      />
    </div>
  );
}

function SuggestionCard(props: {
  icon: React.ReactNode;
  accent: string;
  ring: string;
  glow: string;
  label: string;
  conclusion: string;
  hint: string;
}) {
  return (
    <article
      className={
        `glass-panel flex items-center justify-between gap-4 rounded-[20px] border ${props.ring} ${props.glow} p-5`
      }
    >
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span
            className={`flex h-7 w-7 items-center justify-center rounded-lg bg-white/5 ${props.accent}`}
          >
            {props.icon}
          </span>
          <span className="text-xs uppercase tracking-[0.28em] text-slate-500">
            {props.label}
          </span>
        </div>
        <span className="text-[11px] text-slate-500">{props.hint}</span>
      </div>
      <span className={`text-3xl font-semibold tabular-nums ${props.accent}`}>
        {props.conclusion}
      </span>
    </article>
  );
}
