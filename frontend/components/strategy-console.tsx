"use client";

import { useEffect, useMemo, useState } from "react";

import { Slider } from "@/components/ui/slider";
import { DEFAULT_WEIGHTS, useScoringStore } from "@/store/use-scoring-store";
import type { FactorWeights } from "@/types/scoring";

const AUTO_SYNC_DELAY_MS = 450;

const FACTOR_CONFIG: Array<{
  key: keyof FactorWeights;
  label: string;
  helper: string;
  tone: string;
}> = [
  {
    key: "pe_weight",
    label: "PE 因子",
    helper: "低估值偏好。使用负权重时可主动追逐高估值成长。",
    tone: "Value",
  },
  {
    key: "momentum_weight",
    label: "20 日动量",
    helper: "提高正权重可放大近期价格强势股票的排名影响。",
    tone: "Trend",
  },
  {
    key: "volatility_weight",
    label: "波动率",
    helper: "负权重代表偏好更稳健标的，正权重代表拥抱弹性。",
    tone: "Risk",
  },
];

const PRESETS: Array<{ label: string; weights: FactorWeights }> = [
  {
    label: "Balanced",
    weights: DEFAULT_WEIGHTS,
  },
  {
    label: "Momentum+",
    weights: {
      pe_weight: 0.1,
      momentum_weight: 0.75,
      volatility_weight: -0.15,
    },
  },
  {
    label: "Value LowVol",
    weights: {
      pe_weight: -0.55,
      momentum_weight: 0.2,
      volatility_weight: -0.25,
    },
  },
];

function formatSignedWeight(value: number) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(0)}%`;
}

function formatSyncTime(lastUpdatedAt: number | null) {
  if (!lastUpdatedAt) {
    return "尚未同步";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(lastUpdatedAt);
}

function getNormalizedPreview(weights: FactorWeights): FactorWeights {
  const gross = Object.values(weights).reduce(
    (sum, current) => sum + Math.abs(current),
    0,
  );

  if (!gross) {
    return {
      pe_weight: 0,
      momentum_weight: 0,
      volatility_weight: 0,
    };
  }

  return {
    pe_weight: weights.pe_weight / gross,
    momentum_weight: weights.momentum_weight / gross,
    volatility_weight: weights.volatility_weight / gross,
  };
}

export function StrategyConsole() {
  const weights = useScoringStore((state) => state.weights);
  const normalizedWeights = useScoringStore((state) => state.normalizedWeights);
  const isLoading = useScoringStore((state) => state.isLoading);
  const error = useScoringStore((state) => state.error);
  const lastUpdatedAt = useScoringStore((state) => state.lastUpdatedAt);
  const setWeight = useScoringStore((state) => state.setWeight);
  const setWeights = useScoringStore((state) => state.setWeights);
  const resetWeights = useScoringStore((state) => state.resetWeights);
  const loadScores = useScoringStore((state) => state.loadScores);

  const [syncVersion, setSyncVersion] = useState(1);
  const [settledVersion, setSettledVersion] = useState(0);

  const isPendingSync = syncVersion !== settledVersion;

  const queueSync = () => {
    setSyncVersion((current) => current + 1);
  };

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      void loadScores().finally(() => {
        if (active) {
          setSettledVersion(syncVersion);
        }
      });
    }, AUTO_SYNC_DELAY_MS);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [syncVersion, loadScores]);

  const previewWeights = useMemo(
    () => normalizedWeights ?? getNormalizedPreview(weights),
    [normalizedWeights, weights],
  );

  const grossExposure = useMemo(
    () =>
      Object.values(weights).reduce((sum, current) => sum + Math.abs(current), 0),
    [weights],
  );

  const netBias = useMemo(
    () => Object.values(weights).reduce((sum, current) => sum + current, 0),
    [weights],
  );

  return (
    <div className="grid gap-4">
      <section className="glass-panel relative overflow-hidden rounded-[30px] border border-slate-800/70 p-5">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,0.14),transparent_30%),radial-gradient(circle_at_bottom_right,rgba(249,115,22,0.1),transparent_24%)]" />

        <div className="relative">
          <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.35em] text-cyan-300/75">
                Strategy Console
              </div>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white">
                因子控制台
              </h2>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">
                赛博玻璃卡片 + 自动同步。拖动任一因子后，前端会在
                {` ${AUTO_SYNC_DELAY_MS}ms `}
                后自动调用后端评分接口。
              </p>
            </div>

            <div className="grid w-full gap-2 rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3 text-xs text-slate-300 sm:max-w-[320px] 2xl:w-[320px]">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Auto Sync</span>
                <span
                  className={
                    isLoading
                      ? "text-orange-300"
                      : isPendingSync
                        ? "text-cyan-300"
                        : error
                          ? "text-rose-300"
                          : "text-emerald-300"
                  }
                >
                  {isLoading
                    ? "计算中"
                    : isPendingSync
                      ? "待同步"
                      : error
                        ? "异常"
                        : "在线"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Last Sync</span>
                <span>{formatSyncTime(lastUpdatedAt)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Endpoint</span>
                <span className="truncate pl-3 text-right">
                  {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010"}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setWeights(preset.weights);
                  queueSync();
                }}
                className="rounded-full border border-slate-700/80 bg-slate-900/60 px-3 py-2 text-xs font-medium tracking-wide text-slate-300 transition hover:border-cyan-400/40 hover:text-white"
              >
                {preset.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => {
                resetWeights();
                queueSync();
              }}
              className="rounded-full border border-orange-500/30 bg-orange-500/10 px-3 py-2 text-xs font-medium tracking-wide text-orange-200 transition hover:bg-orange-500/20"
            >
              Reset
            </button>
          </div>

          <div className="mt-6 space-y-4">
            {FACTOR_CONFIG.map((factor) => (
              <div
                key={factor.key}
                className="rounded-[24px] border border-slate-800/70 bg-slate-950/50 p-4 transition hover:border-cyan-400/20 hover:bg-slate-900/60"
              >
                <div className="mb-4 flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-sm font-semibold text-white">
                        {factor.label}
                      </h3>
                      <span className="rounded-full border border-slate-700/80 bg-slate-900/70 px-2 py-0.5 text-[10px] uppercase tracking-[0.3em] text-slate-400">
                        {factor.tone}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-400">
                      {factor.helper}
                    </p>
                  </div>
                  <div className="score-glow rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300">
                    {formatSignedWeight(weights[factor.key])}
                  </div>
                </div>

                <Slider
                  min={-100}
                  max={100}
                  step={5}
                  value={[Math.round(weights[factor.key] * 100)]}
                  onValueChange={(value) => {
                    setWeight(factor.key, Number((value[0] / 100).toFixed(2)));
                    queueSync();
                  }}
                />

                <div className="mt-3 flex items-center justify-between text-[11px] uppercase tracking-[0.25em] text-slate-500">
                  <span>-100%</span>
                  <span>Neutral</span>
                  <span>+100%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4">
        <div className="glass-panel rounded-[30px] border border-slate-800/70 p-5">
          <div className="text-xs uppercase tracking-[0.35em] text-cyan-300/75">
            Exposure Matrix
          </div>
          <h3 className="mt-3 text-lg font-semibold text-white">实时权重剖面</h3>
          <div className="mt-5 grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
            <div className="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div className="text-xs uppercase tracking-[0.25em] text-slate-500">
                Gross
              </div>
              <div className="mt-2 text-3xl font-semibold text-white">
                {(grossExposure * 100).toFixed(0)}%
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                因子绝对值总和，用于判断当前策略整体激进程度。
              </p>
            </div>
            <div className="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div className="text-xs uppercase tracking-[0.25em] text-slate-500">
                Net Bias
              </div>
              <div className="mt-2 text-3xl font-semibold text-white">
                {formatSignedWeight(netBias)}
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                正值偏进攻，负值偏防守，反映组合的总体倾向。
              </p>
            </div>
            <div className="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div className="text-xs uppercase tracking-[0.25em] text-slate-500">
                Debounce
              </div>
              <div className="mt-2 text-3xl font-semibold text-white">
                {AUTO_SYNC_DELAY_MS}ms
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                避免每次拖动都立即打后端，保证交互顺滑。
              </p>
            </div>
          </div>
        </div>

        <div className="glass-panel rounded-[30px] border border-slate-800/70 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-[0.35em] text-cyan-300/75">
                Normalization
              </div>
              <h3 className="mt-3 text-lg font-semibold text-white">
                归一化预览
              </h3>
            </div>
            <button
              type="button"
              onClick={() => {
                void loadScores().finally(() => {
                  setSettledVersion(syncVersion);
                });
              }}
              disabled={isLoading}
              className="rounded-full bg-orange-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-orange-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? "计算中..." : "立即刷新"}
            </button>
          </div>

          <div className="mt-5 space-y-3">
            {FACTOR_CONFIG.map((factor) => (
              <div
                key={factor.key}
                className="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"
              >
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-slate-300">{factor.label}</span>
                  <span className="font-medium text-white">
                    {formatSignedWeight(previewWeights[factor.key])}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-900">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-sky-400 via-cyan-300 to-emerald-400"
                    style={{
                      width: `${Math.min(
                        100,
                        Math.abs(previewWeights[factor.key]) * 100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {error ? (
            <div className="mt-4 rounded-2xl border border-rose-500/25 bg-rose-500/10 p-4 text-sm text-rose-200">
              {error}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
