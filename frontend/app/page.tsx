"use client";

import { LeaderboardTable } from "@/components/leaderboard-table";
import { StrategyConsole } from "@/components/strategy-console";
import { useScoringStore } from "@/store/use-scoring-store";

export default function Home() {
  const results = useScoringStore((state) => state.results);
  const totalUniverse = useScoringStore((state) => state.totalUniverse);
  const returnedCount = useScoringStore((state) => state.returnedCount);
  const isLoading = useScoringStore((state) => state.isLoading);
  const error = useScoringStore((state) => state.error);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-4 py-6 md:px-6 lg:px-8">
      <section className="glass-panel neon-ring rounded-[28px] p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-sky-300/75">
              DDTrading MVP
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white md:text-5xl">
              多因子量化评分系统
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
              Step 4 已接入 TanStack Table 与 ECharts 微图表。现在左侧是赛博策略控制台，右侧是具备悬浮光效、迷你因子图和综合评分条的科技感排行榜。
            </p>
          </div>
          <div className="rounded-2xl border border-slate-800/70 bg-slate-950/60 px-4 py-3 text-sm text-slate-300">
            <div>Universe: {totalUniverse || "--"}</div>
            <div>Returned: {returnedCount || "--"}</div>
          </div>
        </div>
      </section>

      <section className="grid flex-1 gap-6 lg:grid-cols-[1fr_1.6fr]">
        <StrategyConsole />
        <LeaderboardTable data={results} isLoading={isLoading} error={error} />
      </section>
    </main>
  );
}
