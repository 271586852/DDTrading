"use client";

import { create } from "zustand";

import { fetchScores } from "@/lib/api";
import type { FactorWeights, RankedStock, ScoreResponse } from "@/types/scoring";

export const DEFAULT_WEIGHTS: FactorWeights = {
  pe_weight: 0.3,
  momentum_weight: 0.5,
  volatility_weight: -0.2,
};

type ScoringStore = {
  weights: FactorWeights;
  normalizedWeights: FactorWeights | null;
  results: RankedStock[];
  totalUniverse: number;
  returnedCount: number;
  lastUpdatedAt: number | null;
  isLoading: boolean;
  error: string | null;
  setWeight: (key: keyof FactorWeights, value: number) => void;
  setWeights: (weights: FactorWeights) => void;
  resetWeights: () => void;
  loadScores: () => Promise<void>;
};

function applyResponse(state: ScoringStore, payload: ScoreResponse) {
  return {
    ...state,
    normalizedWeights: payload.normalized_weights,
    results: payload.top_50,
    totalUniverse: payload.total_universe,
    returnedCount: payload.returned_count,
    lastUpdatedAt: Date.now(),
    isLoading: false,
    error: null,
  };
}

export const useScoringStore = create<ScoringStore>((set, get) => ({
  weights: DEFAULT_WEIGHTS,
  normalizedWeights: null,
  results: [],
  totalUniverse: 0,
  returnedCount: 0,
  lastUpdatedAt: null,
  isLoading: false,
  error: null,
  setWeight: (key, value) =>
    set((state) => ({
      ...state,
      weights: {
        ...state.weights,
        [key]: value,
      },
    })),
  setWeights: (weights) =>
    set((state) => ({
      ...state,
      weights,
    })),
  resetWeights: () =>
    set((state) => ({
      ...state,
      weights: DEFAULT_WEIGHTS,
    })),
  loadScores: async () => {
    const weights = get().weights;
    set((state) => ({ ...state, isLoading: true, error: null }));

    try {
      const payload = await fetchScores(weights);
      set((state) => applyResponse(state, payload));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown scoring error";
      set((state) => ({
        ...state,
        isLoading: false,
        error: message,
      }));
    }
  },
}));
