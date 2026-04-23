"use client";

import { create } from "zustand";

import {
  ApiError,
  listTradeStrategies,
  normalizeSymbol,
  runBacktest,
} from "@/lib/api";
import type {
  BacktestResponse,
  TradeStrategyInfo,
} from "@/types/backtest";

type FormState = {
  symbol: string;
  startDate: string;
  endDate: string;
  initialCash: number;
  strategyId: string | null;
};

type BacktestStore = {
  strategies: TradeStrategyInfo[];
  strategiesError: string | null;
  form: FormState;
  isRunning: boolean;
  error: string | null;
  result: BacktestResponse | null;

  loadStrategies: () => Promise<void>;
  setForm: (patch: Partial<FormState>) => void;
  runBacktest: () => Promise<void>;
  resetResult: () => void;
};

function getDefaultDates(): { start: string; end: string } {
  const today = new Date();
  const end = today.toISOString().slice(0, 10);
  const past = new Date(today);
  past.setFullYear(past.getFullYear() - 1);
  return { start: past.toISOString().slice(0, 10), end };
}

const defaults = getDefaultDates();

export const useBacktestStore = create<BacktestStore>((set, get) => ({
  strategies: [],
  strategiesError: null,
  form: {
    symbol: "",
    startDate: defaults.start,
    endDate: defaults.end,
    initialCash: 100000,
    strategyId: null,
  },
  isRunning: false,
  error: null,
  result: null,

  loadStrategies: async () => {
    try {
      const strategies = await listTradeStrategies();
      set((state) => ({
        ...state,
        strategies,
        strategiesError: null,
        form: {
          ...state.form,
          strategyId: state.form.strategyId ?? strategies[0]?.id ?? null,
        },
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载交易策略失败";
      set((state) => ({ ...state, strategiesError: message }));
    }
  },

  setForm: (patch) =>
    set((state) => ({ ...state, form: { ...state.form, ...patch } })),

  runBacktest: async () => {
    const { form } = get();
    if (!form.symbol.trim()) {
      set((state) => ({ ...state, error: "请输入股票代码" }));
      return;
    }
    let normalizedSymbol: string;
    try {
      normalizedSymbol = normalizeSymbol(form.symbol);
    } catch (err) {
      const message = err instanceof Error ? err.message : "代码格式不正确";
      set((state) => ({ ...state, error: message }));
      return;
    }
    if (!form.startDate || !form.endDate) {
      set((state) => ({ ...state, error: "请选择起止日期" }));
      return;
    }
    if (form.endDate < form.startDate) {
      set((state) => ({ ...state, error: "结束日期不能早于开始日期" }));
      return;
    }
    if (!form.strategyId) {
      set((state) => ({ ...state, error: "请先选择一个交易策略" }));
      return;
    }
    if (!(form.initialCash > 0)) {
      set((state) => ({ ...state, error: "初始资金需大于 0" }));
      return;
    }

    set((state) => ({
      ...state,
      isRunning: true,
      error: null,
    }));

    try {
      const result = await runBacktest({
        symbol: normalizedSymbol,
        start_date: form.startDate,
        end_date: form.endDate,
        initial_cash: form.initialCash,
        strategy_id: form.strategyId,
      });
      set((state) => ({
        ...state,
        isRunning: false,
        result,
        form: { ...state.form, symbol: normalizedSymbol },
      }));
    } catch (err) {
      let message: string;
      if (err instanceof ApiError) {
        if (err.status === 404) {
          message = `代码 ${normalizedSymbol} 不在本地缓存中，请先执行 /refresh。`;
        } else {
          message = err.message;
        }
      } else if (err instanceof Error) {
        message = err.message;
      } else {
        message = "回测失败";
      }
      set((state) => ({
        ...state,
        isRunning: false,
        error: message,
        result: null,
      }));
    }
  },

  resetResult: () =>
    set((state) => ({ ...state, result: null, error: null })),
}));
