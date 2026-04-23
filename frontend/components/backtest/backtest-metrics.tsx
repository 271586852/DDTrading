"use client";

import {
  Activity,
  ArrowDown,
  ArrowUp,
  Gauge,
  PiggyBank,
  Repeat,
  Target,
  TrendingUp,
} from "lucide-react";

import type { BacktestResponse } from "@/types/backtest";

function formatPct(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

function formatInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "--";
  return Math.round(value).toString();
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

export function BacktestMetrics({ result }: { result: BacktestResponse }) {
  const { metrics, initial_cash } = result;

  const isProfit = (metrics.total_return ?? 0) > 0;
  const isLoss = (metrics.total_return ?? 0) < 0;
  const returnColor = isProfit
    ? "text-rose-300"
    : isLoss
      ? "text-emerald-300"
      : "text-slate-200";

  const pnl =
    metrics.final_equity != null
      ? metrics.final_equity - initial_cash
      : null;

  return (
    <section className="glass-panel rounded-[24px] border border-cyan-400/15 p-6 shadow-[0_0_40px_rgba(34,211,238,0.08)]">
      <header className="mb-5 flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-[11px] uppercase tracking-[0.3em] text-cyan-300/80">
            Performance Metrics
          </p>
          <h2 className="text-lg font-semibold tracking-tight text-white">
            关键指标
          </h2>
        </div>
        {result.applied_strategy && (
          <div className="flex flex-col items-end">
            <span className="text-xs text-slate-400">当前策略</span>
            <span className="text-sm font-medium text-cyan-100">
              {result.applied_strategy.name}
            </span>
          </div>
        )}
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCell
          icon={
            isLoss ? (
              <ArrowDown className="h-3.5 w-3.5" strokeWidth={1.8} />
            ) : (
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={1.8} />
            )
          }
          label="总收益率"
          value={formatPct(metrics.total_return)}
          valueClassName={`text-2xl font-semibold tabular-nums ${returnColor}`}
        />
        <MetricCell
          icon={<TrendingUp className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="年化收益"
          value={formatPct(
            metrics.annualized_return != null
              ? metrics.annualized_return * 100
              : null,
          )}
        />
        <MetricCell
          icon={<Activity className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="最大回撤"
          value={formatPct(
            metrics.max_drawdown != null ? -Math.abs(metrics.max_drawdown) : null,
          )}
          valueClassName="text-2xl font-semibold tabular-nums text-amber-200"
        />
        <MetricCell
          icon={<Gauge className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="夏普比率"
          value={formatNumber(metrics.sharpe_ratio, 2)}
        />
        <MetricCell
          icon={<Target className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="胜率"
          value={formatPct(metrics.win_rate, 1)}
        />
        <MetricCell
          icon={<Repeat className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="交易次数"
          value={formatInt(metrics.trade_count)}
        />
        <MetricCell
          icon={<PiggyBank className="h-3.5 w-3.5" strokeWidth={1.8} />}
          label="期末权益"
          value={formatCurrency(metrics.final_equity)}
        />
        <MetricCell
          icon={
            pnl != null && pnl > 0 ? (
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={1.8} />
            ) : (
              <ArrowDown className="h-3.5 w-3.5" strokeWidth={1.8} />
            )
          }
          label="净损益"
          value={pnl != null ? formatCurrency(pnl) : "--"}
          valueClassName={
            pnl != null && pnl !== 0
              ? pnl > 0
                ? "text-2xl font-semibold tabular-nums text-rose-300"
                : "text-2xl font-semibold tabular-nums text-emerald-300"
              : "text-2xl font-semibold tabular-nums text-slate-200"
          }
        />
      </div>

      <footer className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] text-slate-500">
        <span>
          实际区间:
          <span className="ml-2 font-mono text-slate-300">
            {result.effective_range.start} ~ {result.effective_range.end}
          </span>
        </span>
        <span>
          初始资金:
          <span className="ml-2 font-mono text-slate-300">
            {formatCurrency(result.initial_cash)} 元
          </span>
        </span>
        <span>
          代码:
          <span className="ml-2 font-mono text-slate-300">{result.symbol}</span>
        </span>
      </footer>
    </section>
  );
}

function MetricCell(props: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded-2xl border border-white/5 bg-slate-950/40 px-4 py-3">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.25em] text-slate-500">
        <span>{props.label}</span>
        <span className="text-slate-400">{props.icon}</span>
      </div>
      <span
        className={
          props.valueClassName ??
          "text-2xl font-semibold tabular-nums text-slate-100"
        }
      >
        {props.value}
      </span>
    </div>
  );
}
