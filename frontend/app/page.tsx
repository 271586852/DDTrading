"use client";

import { AnalysisMainCard } from "@/components/dashboard/analysis-main-card";
import { FloatingNav } from "@/components/dashboard/floating-nav";
import { HistoryList } from "@/components/dashboard/history-list";
import { MarketAnalysisDialog } from "@/components/dashboard/market-analysis-dialog";
import { SearchBar } from "@/components/dashboard/search-bar";
import { SentimentCard } from "@/components/dashboard/sentiment-card";
import { StrategyPicker } from "@/components/dashboard/strategy-picker";
import { StrategyPointsCard } from "@/components/dashboard/strategy-points-card";
import { SuggestionCards } from "@/components/dashboard/suggestion-cards";
import { TaskPanel } from "@/components/dashboard/task-panel";

export default function Home() {
  return (
    <>
      <FloatingNav />
      <main className="relative mx-auto flex min-h-screen w-full max-w-[1440px] flex-col gap-6 px-4 py-6 md:px-6 lg:px-10 lg:pl-24">
        <header className="flex flex-col gap-2">
          <p className="text-[11px] uppercase tracking-[0.4em] text-cyan-300/70">
            DDTrading Quant Console
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-white md:text-3xl">
            量化交易分析终端
          </h1>
        </header>

        <SearchBar />

        <div className="grid flex-1 gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="flex flex-col gap-5">
            <StrategyPicker />
            <TaskPanel />
            <HistoryList />
          </aside>

          <section className="flex flex-col gap-5">
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
              <AnalysisMainCard />
              <SentimentCard />
            </div>
            <SuggestionCards />
            <StrategyPointsCard />
          </section>
        </div>
      </main>

      <MarketAnalysisDialog />
    </>
  );
}
