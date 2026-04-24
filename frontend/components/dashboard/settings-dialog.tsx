"use client";

import { Loader2, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { refreshMarketData } from "@/lib/api";
import type { RefreshResponse } from "@/types/scoring";

type SettingsDialogProps = {
  open: boolean;
  onClose: () => void;
};

export function SettingsDialog({ open, onClose }: SettingsDialogProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [result, setResult] = useState<RefreshResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !refreshing) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, refreshing]);

  if (!open) return null;

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const response = await refreshMarketData("incremental");
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新数据失败");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={onClose} />
      <div className="glass-panel relative z-10 w-full max-w-xl rounded-[24px] border border-cyan-400/20 p-6 shadow-[0_0_60px_rgba(34,211,238,0.12)]">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-cyan-300/70">
              Settings
            </p>
            <h2 className="mt-2 text-xl font-semibold tracking-tight text-white">
              数据更新
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              点击“更新数据”会触发一次全市场增量刷新：日线按已缓存最后日期补拉，
              名称做 upsert，PE 快照按天补齐到最新。
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/5 bg-slate-900/40 p-2 text-slate-400 hover:border-rose-400/40 hover:text-rose-200"
            aria-label="关闭设置"
          >
            <X className="h-4 w-4" strokeWidth={1.8} />
          </button>
        </header>

        <div className="mt-6 rounded-2xl border border-white/5 bg-slate-950/40 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-white">全市场数据</p>
              <p className="mt-1 text-xs text-slate-500">
                默认走增量刷新，通常比全量重建快很多。
              </p>
            </div>
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
              className="inline-flex items-center justify-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 transition hover:border-cyan-300/50 hover:bg-cyan-400/15 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {refreshing ? (
                <Loader2 className="h-4 w-4 animate-spin" strokeWidth={1.8} />
              ) : (
                <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
              )}
              {refreshing ? "更新中..." : "更新数据"}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              数据更新完成，当前模式：
              <span className="ml-2 font-semibold">{result.summary.mode}</span>
            </div>
            <SummaryCard
              title="日线缓存"
              lines={[
                `行数 ${result.summary.daily.rows_before ?? 0} -> ${result.summary.daily.rows_after ?? result.summary.daily.rows ?? 0}`,
                `新增行 ${result.summary.daily.rows_added ?? 0}`,
                `更新标的 ${result.summary.daily.updated_symbols ?? 0}`,
                `失败标的 ${result.summary.daily.failed_symbols ?? 0}`,
              ]}
            />
            <SummaryCard
              title="名称快照"
              lines={[
                `行数 ${result.summary.names.rows_before ?? 0} -> ${result.summary.names.rows_after ?? result.summary.names.rows ?? 0}`,
                `upsert 标的 ${result.summary.names.upserted_symbols ?? 0}`,
                result.summary.names.warning ?? "名称快照已完成合并",
              ]}
            />
            <SummaryCard
              title="PE 快照"
              lines={[
                `行数 ${result.summary.pe.rows_before ?? 0} -> ${result.summary.pe.rows_after ?? result.summary.pe.rows ?? 0}`,
                `更新标的 ${result.summary.pe.updated_symbols ?? 0}`,
                `路径 ${result.summary.pe.path}`,
              ]}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ title, lines }: { title: string; lines: string[] }) {
  return (
    <section className="rounded-2xl border border-white/5 bg-slate-950/40 p-4">
      <h3 className="text-sm font-medium text-white">{title}</h3>
      <ul className="mt-2 space-y-1.5 text-xs leading-5 text-slate-400">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}
