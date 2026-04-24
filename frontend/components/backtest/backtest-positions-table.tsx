"use client";

import type { BacktestResponse } from "@/types/backtest";

type PositionRow = Record<string, unknown>;

function fmt(value: unknown, digits = 2): string {
  if (value == null) return "--";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "--";
    return value.toFixed(digits);
  }
  return String(value);
}

function pick(row: PositionRow, keys: string[]): unknown {
  for (const key of keys) {
    if (key in row) return row[key];
  }
  return null;
}

function fmtDate(value: unknown): string {
  if (typeof value !== "string") return "--";
  const idx = value.indexOf("T");
  return idx > 0 ? value.slice(0, idx) : value.slice(0, 10);
}

export function BacktestPositionsTable({ result }: { result: BacktestResponse }) {
  const rows = result.daily_positions ?? [];
  if (!rows.length) {
    return (
      <section className="glass-panel rounded-[24px] border border-white/5 p-6">
        <p className="text-sm text-slate-400">暂无每日持仓详情数据。</p>
      </section>
    );
  }

  return (
    <section className="glass-panel rounded-[24px] border border-cyan-400/15 p-6">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-[11px] uppercase tracking-[0.3em] text-cyan-300/80">
            Daily Positions
          </p>
          <h2 className="text-lg font-semibold tracking-tight text-white">
            每日持仓详情（最近 {rows.length} 天）
          </h2>
        </div>
      </header>

      <div className="overflow-x-auto rounded-2xl border border-white/5 bg-slate-950/40">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-white/5 text-[11px] uppercase tracking-widest text-slate-500">
            <tr>
              <th className="px-3 py-2.5 font-medium">日期</th>
              <th className="px-3 py-2.5 text-right font-medium">权益</th>
              <th className="px-3 py-2.5 text-right font-medium">现金</th>
              <th className="px-3 py-2.5 text-right font-medium">保证金</th>
              <th className="px-3 py-2.5 text-right font-medium">持仓数</th>
              <th className="px-3 py-2.5 text-right font-medium">净暴露</th>
              <th className="px-3 py-2.5 text-right font-medium">总暴露</th>
              <th className="px-3 py-2.5 text-right font-medium">杠杆</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={`${pick(row, ["date", "timestamp"]) ?? idx}-${idx}`}
                className="border-b border-white/5 last:border-none hover:bg-slate-900/40"
              >
                <td className="px-3 py-2.5 font-mono text-xs text-slate-300">
                  {fmtDate(pick(row, ["date", "timestamp", "time"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-200">
                  {fmt(pick(row, ["equity", "market_value"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-300">
                  {fmt(pick(row, ["cash"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-300">
                  {fmt(pick(row, ["margin"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-400">
                  {fmt(pick(row, ["positions", "position_count", "n_positions"]), 0)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-cyan-200">
                  {fmt(pick(row, ["net_exposure"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-cyan-200">
                  {fmt(pick(row, ["gross_exposure"]))}
                </td>
                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-amber-200">
                  {fmt(pick(row, ["leverage"]))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
