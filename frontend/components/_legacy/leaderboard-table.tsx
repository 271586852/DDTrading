"use client";

import { useMemo } from "react";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import { FactorMiniChart } from "@/components/factor-mini-chart";
import { cn } from "@/lib/utils";
import type { RankedStock } from "@/types/scoring";

type LeaderboardTableProps = {
  data: RankedStock[];
  isLoading: boolean;
  error: string | null;
};

function formatPercentile(score: number) {
  return `${Math.round(score)}%`;
}

function scoreTone(score: number) {
  if (score >= 85) {
    return "text-emerald-300";
  }
  if (score >= 70) {
    return "text-cyan-300";
  }
  if (score >= 55) {
    return "text-amber-300";
  }
  return "text-slate-300";
}

function rankTone(rank: number) {
  if (rank === 1) {
    return "border-emerald-400/35 bg-emerald-500/12 text-emerald-200";
  }
  if (rank === 2) {
    return "border-sky-400/35 bg-sky-500/12 text-sky-200";
  }
  if (rank === 3) {
    return "border-orange-400/35 bg-orange-500/12 text-orange-200";
  }
  return "border-slate-700/80 bg-slate-900/75 text-slate-300";
}

export function LeaderboardTable({
  data,
  isLoading,
  error,
}: LeaderboardTableProps) {
  const columns = useMemo<ColumnDef<RankedStock>[]>(
    () => [
      {
        accessorKey: "rank",
        header: "Rank",
        cell: ({ row }) => (
          <div className="flex items-center">
            <div
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-semibold tracking-[0.25em]",
                rankTone(row.original.rank),
              )}
            >
              #{row.original.rank}
            </div>
          </div>
        ),
        size: 88,
      },
      {
        id: "stock",
        header: "Stock",
        cell: ({ row }) => {
          const stock = row.original;
          return (
            <div className="space-y-2">
              <div className="font-medium text-white">{stock.name}</div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs uppercase tracking-[0.3em] text-slate-500">
                  {stock.ticker}
                </span>
                <span className="rounded-full border border-slate-800 bg-slate-950/80 px-2 py-1 text-[10px] uppercase tracking-[0.28em] text-slate-400">
                  PE {stock.factor_values.pe_ratio.toFixed(1)}
                </span>
                <span className="rounded-full border border-slate-800 bg-slate-950/80 px-2 py-1 text-[10px] uppercase tracking-[0.28em] text-slate-400">
                  MOM {stock.factor_values.momentum_20d.toFixed(3)}
                </span>
              </div>
            </div>
          );
        },
      },
      {
        id: "detail",
        header: "Detail",
        cell: ({ row }) => {
          const stock = row.original;

          return (
            <div className="grid gap-3 2xl:grid-cols-[minmax(0,1fr)_160px] 2xl:items-center">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <div className="rounded-2xl border border-slate-800/70 bg-slate-950/70 p-3">
                  <div className="text-[10px] uppercase tracking-[0.28em] text-slate-500">
                    PE Z
                  </div>
                  <div className="mt-2 text-sm font-semibold text-sky-300">
                    {stock.factor_zscores.pe_ratio.toFixed(2)}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-800/70 bg-slate-950/70 p-3">
                  <div className="text-[10px] uppercase tracking-[0.28em] text-slate-500">
                    MOM Z
                  </div>
                  <div className="mt-2 text-sm font-semibold text-emerald-300">
                    {stock.factor_zscores.momentum_20d.toFixed(2)}
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-800/70 bg-slate-950/70 p-3">
                  <div className="text-[10px] uppercase tracking-[0.28em] text-slate-500">
                    VOL Z
                  </div>
                  <div className="mt-2 text-sm font-semibold text-orange-300">
                    {stock.factor_zscores.volatility.toFixed(2)}
                  </div>
                </div>
              </div>
              <FactorMiniChart stock={stock} />
            </div>
          );
        },
      },
      {
        accessorKey: "total_score",
        header: "Score",
        cell: ({ row }) => {
          const score = row.original.total_score;
          return (
            <div className="space-y-3 text-right">
              <div className={cn("score-glow text-2xl font-semibold", scoreTone(score))}>
                {score.toFixed(2)}
              </div>
              <div className="flex items-center justify-end gap-3">
                <div className="h-2 w-28 overflow-hidden rounded-full bg-slate-900">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-sky-400 via-cyan-300 to-emerald-400 shadow-[0_0_22px_rgba(56,189,248,0.25)]"
                    style={{ width: `${score}%` }}
                  />
                </div>
                <span className="text-xs tracking-[0.28em] text-slate-500">
                  {formatPercentile(score)}
                </span>
              </div>
            </div>
          );
        },
        size: 150,
      },
    ],
    [],
  );

  // TanStack Table intentionally returns instance methods for rendering.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="glass-panel rounded-[28px] p-5">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">评分结果</h2>
          <p className="mt-1 text-sm text-slate-400">
            TanStack Table 已接入，排行榜行支持微位移动效与因子迷你图。
          </p>
        </div>
        {error ? (
          <div className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {error}
          </div>
        ) : (
          <div className="rounded-full border border-slate-800/70 bg-slate-950/70 px-3 py-2 text-xs uppercase tracking-[0.32em] text-slate-500">
            Top 50
          </div>
        )}
      </div>

      <div className="overflow-hidden rounded-[28px] border border-slate-800/70 bg-slate-950/60">
        <div className="overflow-x-auto">
          <div className="min-w-[980px]">
            <div className="grid grid-cols-[88px_minmax(180px,1.05fr)_minmax(360px,1.5fr)_150px] gap-4 border-b border-slate-800/70 px-4 py-3 text-[10px] uppercase tracking-[0.35em] text-slate-500">
              {table.getFlatHeaders().map((header) => (
                <div key={header.id} className={header.id === "total_score" ? "text-right" : ""}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </div>
              ))}
            </div>

            <div className="max-h-[960px] overflow-y-auto">
          {isLoading && data.length === 0 ? (
            <div className="space-y-3 px-4 py-4">
              {Array.from({ length: 6 }).map((_, index) => (
                <div
                  key={index}
                  className="grid grid-cols-[88px_minmax(180px,1.05fr)_minmax(360px,1.5fr)_150px] gap-4 rounded-[24px] border border-slate-800/50 bg-slate-900/35 px-4 py-4"
                >
                  <div className="h-10 animate-pulse rounded-full bg-slate-800/80" />
                  <div className="h-14 animate-pulse rounded-2xl bg-slate-800/80" />
                  <div className="h-24 animate-pulse rounded-2xl bg-slate-800/80" />
                  <div className="h-14 animate-pulse rounded-2xl bg-slate-800/80" />
                </div>
              ))}
            </div>
          ) : null}

          {!data.length && !isLoading ? (
            <div className="px-4 py-12 text-center text-sm text-slate-500">
              暂无结果，请确认后端已启动并调整策略参数。
            </div>
          ) : null}

          <div className="space-y-3 p-3">
            {table.getRowModel().rows.map((row) => (
              <div
                key={row.id}
                className="grid grid-cols-[88px_minmax(180px,1.05fr)_minmax(360px,1.5fr)_150px] gap-4 rounded-[24px] border border-slate-800/70 bg-slate-900/35 px-4 py-4 transition duration-200 hover:-translate-y-0.5 hover:translate-x-1 hover:border-cyan-400/20 hover:bg-slate-900/70 hover:shadow-[0_12px_40px_rgba(2,132,199,0.08)]"
              >
                {row.getVisibleCells().map((cell) => (
                  <div
                    key={cell.id}
                    className={cell.column.id === "total_score" ? "flex items-center justify-end" : "flex items-center"}
                  >
                    <div className="w-full">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
          </div>
        </div>
      </div>
    </div>
  );
}
