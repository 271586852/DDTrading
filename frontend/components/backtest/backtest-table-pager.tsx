"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;
export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

export function useClientPagination<T>(
  items: T[],
  defaultPageSize: PageSizeOption = 25,
) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSizeState] = useState<PageSizeOption>(defaultPageSize);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPage(1);
  }, [items.length]);

  useEffect(() => {
    setPage((p) => Math.min(p, totalPages));
  }, [totalPages]);

  const safePage = Math.min(Math.max(1, page), totalPages);
  const offset = (safePage - 1) * pageSize;

  const pageItems = useMemo(
    () => items.slice(offset, offset + pageSize),
    [items, offset, pageSize],
  );

  const setPageSize = useCallback((n: number) => {
    const allowed = new Set<number>(PAGE_SIZE_OPTIONS);
    const v = (allowed.has(n) ? n : 25) as PageSizeOption;
    setPageSizeState(v);
    setPage(1);
  }, []);

  return {
    page: safePage,
    setPage,
    pageSize,
    setPageSize,
    pageItems,
    total,
    totalPages,
    offset,
  };
}

export function BacktestTablePager({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (p: number) => void;
  onPageSizeChange: (n: number) => void;
}) {
  if (total <= 0) return null;

  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-white/5 pt-4 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs tabular-nums">
        共 <span className="text-slate-200">{total}</span> 条 · 第{" "}
        <span className="text-slate-200">{page}</span> / {totalPages} 页
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">每页</span>
          <select
            className="rounded-lg border border-white/10 bg-slate-950/80 px-2 py-1 text-slate-200"
            value={pageSize}
            onChange={(e) => {
              onPageSizeChange(Number(e.target.value));
            }}
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="rounded-lg border border-white/10 px-3 py-1 text-xs text-slate-200 hover:bg-white/5 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            上一页
          </button>
          <button
            type="button"
            className="rounded-lg border border-white/10 px-3 py-1 text-xs text-slate-200 hover:bg-white/5 disabled:opacity-40"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}
