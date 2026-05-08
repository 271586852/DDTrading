"use client";

import { ArrowDown, ArrowUp } from "lucide-react";

import {
  BacktestTablePager,
  useClientPagination,
} from "@/components/backtest/backtest-table-pager";
import type { BacktestResponse } from "@/types/backtest";

type TradeRow = {
  entry_time?: string;
  exit_time?: string;
  entry_price?: number;
  exit_price?: number;
  quantity?: number;
  side?: string;
  pnl?: number;
  net_pnl?: number;
  return_pct?: number;
  commission?: number;
  duration_bars?: number;
};

function fmt(v: unknown, digits = 2): string {
  if (v == null) return "--";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "--";
    return v.toFixed(digits);
  }
  return String(v);
}

function fmtDate(value: unknown): string {
  if (typeof value !== "string") return "--";
  const idx = value.indexOf("T");
  return idx > 0 ? value.slice(0, idx) : value.slice(0, 10);
}

export function BacktestTradesTable({ result }: { result: BacktestResponse }) {
  const allRows = (result.recent_trades as TradeRow[]) ?? [];
  const {
    page,
    setPage,
    pageSize,
    setPageSize,
    pageItems,
    total,
    totalPages,
    offset,
  } = useClientPagination(allRows, 25);

  if (!allRows.length) {
    return (
      <section className="glass-panel rounded-[24px] border border-white/5 p-6">
        <p className="text-sm text-slate-400">该策略在此区间内没有产生交易。</p>
      </section>
    );
  }

  return (
    <section className="glass-panel rounded-[24px] border border-cyan-400/15 p-6">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-[11px] uppercase tracking-[0.3em] text-cyan-300/80">
            Recent Trades
          </p>
          <h2 className="text-lg font-semibold tracking-tight text-white">
            全部 {total} 笔成交
          </h2>
        </div>
        <span className="text-[11px] text-slate-500">时间倒序</span>
      </header>

      <div className="overflow-x-auto rounded-2xl border border-white/5 bg-slate-950/40">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-white/5 text-[11px] uppercase tracking-widest text-slate-500">
            <tr>
              <Th>方向</Th>
              <Th>开仓</Th>
              <Th>平仓</Th>
              <Th className="text-right">开仓价</Th>
              <Th className="text-right">平仓价</Th>
              <Th className="text-right">数量</Th>
              <Th className="text-right">净损益</Th>
              <Th className="text-right">收益率</Th>
              <Th className="text-right">持仓 bars</Th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((row, idx) => {
              const pnl = row.net_pnl ?? row.pnl ?? 0;
              const isWin = pnl > 0;
              const isLoss = pnl < 0;
              return (
                <tr
                  key={`${row.entry_time ?? "row"}-${offset + idx}`}
                  className="border-b border-white/5 last:border-none hover:bg-slate-900/40"
                >
                  <Td>
                    <span
                      className={
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium " +
                        (row.side === "short"
                          ? "border border-emerald-400/30 bg-emerald-500/10 text-emerald-200"
                          : "border border-rose-400/30 bg-rose-500/10 text-rose-200")
                      }
                    >
                      {row.side === "short" ? (
                        <ArrowDown className="h-3 w-3" strokeWidth={2} />
                      ) : (
                        <ArrowUp className="h-3 w-3" strokeWidth={2} />
                      )}
                      {row.side ?? "--"}
                    </span>
                  </Td>
                  <Td className="font-mono text-xs text-slate-300">
                    {fmtDate(row.entry_time)}
                  </Td>
                  <Td className="font-mono text-xs text-slate-300">
                    {fmtDate(row.exit_time)}
                  </Td>
                  <Td className="text-right font-mono tabular-nums text-slate-200">
                    {fmt(row.entry_price)}
                  </Td>
                  <Td className="text-right font-mono tabular-nums text-slate-200">
                    {fmt(row.exit_price)}
                  </Td>
                  <Td className="text-right font-mono tabular-nums text-slate-400">
                    {fmt(row.quantity, 0)}
                  </Td>
                  <Td
                    className={
                      "text-right font-mono tabular-nums " +
                      (isWin
                        ? "text-rose-300"
                        : isLoss
                          ? "text-emerald-300"
                          : "text-slate-300")
                    }
                  >
                    {fmt(pnl)}
                  </Td>
                  <Td
                    className={
                      "text-right font-mono tabular-nums " +
                      (isWin
                        ? "text-rose-300"
                        : isLoss
                          ? "text-emerald-300"
                          : "text-slate-300")
                    }
                  >
                    {row.return_pct != null ? `${fmt(row.return_pct)}%` : "--"}
                  </Td>
                  <Td className="text-right font-mono tabular-nums text-slate-400">
                    {fmt(row.duration_bars, 0)}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <BacktestTablePager
        page={page}
        totalPages={totalPages}
        total={total}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
      />
    </section>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th className={`px-3 py-2.5 font-medium ${className}`}>{children}</th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-3 py-2.5 ${className}`}>{children}</td>;
}
