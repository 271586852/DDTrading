"use client";

import { LineChart } from "lucide-react";

import { BacktestChart } from "@/components/backtest/backtest-chart";
import { BacktestForm } from "@/components/backtest/backtest-form";
import { BacktestMetrics } from "@/components/backtest/backtest-metrics";
import { BacktestPositionsTable } from "@/components/backtest/backtest-positions-table";
import { BacktestTradesTable } from "@/components/backtest/backtest-trades-table";
import { FloatingNav } from "@/components/dashboard/floating-nav";
import { useBacktestStore } from "@/store/use-backtest-store";

export default function BacktestPage() {
  const result = useBacktestStore((s) => s.result);
  const isRunning = useBacktestStore((s) => s.isRunning);

  return (
    <>
      <FloatingNav />
      <main className="relative mx-auto flex min-h-screen w-full max-w-[1440px] flex-col gap-6 px-4 py-6 md:px-6 lg:px-10 lg:pl-24">
        <header className="flex flex-col gap-2">
          <p className="text-[11px] uppercase tracking-[0.4em] text-cyan-300/70">
            DDTrading Backtest Studio
          </p>
          <h1 className="flex items-center gap-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-300">
              <LineChart className="h-5 w-5" strokeWidth={1.6} />
            </span>
            策略回测工作台
          </h1>
          <p className="text-sm text-slate-400">
            选择交易策略与时间窗口，在本地日线缓存上运行 AKQuant
            回测，实时查看权益曲线、回撤与成交点位。
          </p>
        </header>

        <div className="grid flex-1 gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-5">
            <BacktestForm />
          </aside>

          <section className="flex flex-col gap-5">
            {!result && !isRunning && <EmptyState />}
            {isRunning && !result && <LoadingState />}
            {result && (
              <>
                <BacktestMetrics result={result} />
                <BacktestChart result={result} />
                <BacktestTradesTable result={result} />
                <BacktestPositionsTable result={result} />
              </>
            )}
          </section>
        </div>
      </main>
    </>
  );
}

function EmptyState() {
  return (
    <section className="glass-panel flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-[24px] border border-white/5 p-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/15 text-cyan-200">
        <LineChart className="h-6 w-6" strokeWidth={1.5} />
      </span>
      <h3 className="text-lg font-medium text-slate-100">
        还没有回测结果
      </h3>
      <p className="max-w-md text-sm text-slate-500">
        在左侧输入股票代码、起止日期与初始资金，选择一条交易策略，点击
        <span className="mx-1 text-cyan-300">运行回测</span>
        即可查看权益曲线与成交点位。
      </p>
    </section>
  );
}

function LoadingState() {
  return (
    <section className="glass-panel flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-[24px] border border-cyan-400/20 p-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full border border-cyan-400/40 bg-cyan-500/10">
        <span className="h-3 w-3 animate-ping rounded-full bg-cyan-300" />
      </div>
      <h3 className="text-lg font-medium text-slate-100">正在运行回测…</h3>
      <p className="text-sm text-slate-500">AKQuant 正在撮合订单并汇总绩效指标。</p>
    </section>
  );
}
