"use client";

import { Loader2, Radar, Search } from "lucide-react";
import { useState } from "react";

import { useScoringStore } from "@/store/use-scoring-store";

export function SearchBar() {
  const [value, setValue] = useState("");
  const isAnalyzing = useScoringStore((state) => state.isAnalyzing);
  const marketLoading = useScoringStore((state) => state.marketLoading);
  const analyzeSymbol = useScoringStore((state) => state.analyzeSymbol);
  const runMarketAnalysis = useScoringStore((state) => state.runMarketAnalysis);

  const handleSubmit = async () => {
    if (!value.trim() || isAnalyzing) return;
    await analyzeSymbol(value);
  };

  return (
    <section className="glass-panel neon-ring rounded-[24px] px-5 py-4 md:px-7 md:py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
        <div className="group relative flex-1">
          <div
            className={
              "flex items-center gap-3 rounded-2xl border border-white/5 bg-slate-950/60 px-4 py-3 transition-all " +
              "focus-within:border-cyan-400/60 focus-within:shadow-[0_0_22px_rgba(56,189,248,0.35)]"
            }
          >
            <Search
              className="h-5 w-5 text-slate-400 group-focus-within:text-cyan-300"
              strokeWidth={1.6}
            />
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleSubmit();
                }
              }}
              placeholder="输入股票代码，如 600519、00700、AAPL"
              className="flex-1 bg-transparent text-base text-white outline-none placeholder:text-slate-500"
              aria-label="股票代码搜索"
            />
            {value && (
              <button
                type="button"
                onClick={() => setValue("")}
                className="text-xs text-slate-500 hover:text-slate-300"
              >
                清除
              </button>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={isAnalyzing || !value.trim()}
            className={
              "inline-flex h-12 items-center gap-2 rounded-2xl px-6 text-sm font-medium tracking-wide transition-all " +
              "bg-gradient-to-r from-cyan-500/90 via-cyan-400/90 to-sky-400/90 text-slate-950 shadow-[0_0_28px_rgba(56,189,248,0.35)] " +
              "hover:shadow-[0_0_34px_rgba(56,189,248,0.55)] " +
              "disabled:opacity-50 disabled:shadow-none disabled:cursor-not-allowed"
            }
          >
            {isAnalyzing ? (
              <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
            ) : (
              <Search className="h-4 w-4" strokeWidth={1.8} />
            )}
            分析
          </button>
          <button
            type="button"
            onClick={() => void runMarketAnalysis()}
            disabled={marketLoading}
            className={
              "inline-flex h-12 items-center gap-2 rounded-2xl border border-purple-400/50 bg-purple-500/10 px-5 text-sm font-medium tracking-wide text-purple-100 transition-all " +
              "hover:border-purple-300/80 hover:bg-purple-500/20 hover:shadow-[0_0_24px_rgba(168,85,247,0.35)] " +
              "disabled:opacity-50 disabled:cursor-not-allowed"
            }
          >
            {marketLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
            ) : (
              <Radar className="h-4 w-4" strokeWidth={1.8} />
            )}
            全市场分析
          </button>
        </div>
      </div>
    </section>
  );
}
