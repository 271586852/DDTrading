/** 评分分项：与后端 ``value_format`` / ``zscore_orientation`` 对齐的展示逻辑 */

import type { FactorFieldInfo } from "@/types/scoring";

export function factorKeysInOrder(
  fv: Record<string, number> | null | undefined,
): string[] {
  if (!fv || typeof fv !== "object") return [];
  return Object.keys(fv).filter((k) => typeof fv[k] === "number");
}

export function formatValueByFormat(format: string, value: number): string {
  switch (format) {
    case "percent_2":
      return `${(value * 100).toFixed(2)}%`;
    case "decimal_2":
      return value.toFixed(2);
    case "decimal_1":
      return value.toFixed(1);
    case "integer":
      return String(Math.round(value));
    case "decimal_3":
      return value.toFixed(3);
    default:
      return Number.isFinite(value) ? value.toFixed(3) : "—";
  }
}

export function formatFactorCellDisplay(
  meta: FactorFieldInfo | undefined,
  fv: Record<string, number> | null | undefined,
  key: string,
): string {
  const v = fv?.[key];
  if (v === undefined || Number.isNaN(v)) return "—";
  return formatValueByFormat(meta?.value_format ?? "decimal_3", v);
}

function erfApprox(z: number): number {
  const x = z;
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const sign = x < 0 ? -1 : 1;
  const abs = Math.abs(x);
  const t = 1.0 / (1.0 + 0.3275911 * abs);
  const y =
    1.0 -
    (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t) * Math.exp(-abs * abs);
  return sign * y;
}

export function zscoreToPercentile(zs: number): string {
  const p = 0.5 * (1 + erfApprox(zs / Math.SQRT2));
  return (p * 100).toFixed(0);
}

export function percentileFromMeta(
  meta: FactorFieldInfo | undefined,
  val: number,
  zs: number | undefined,
  pctFn: (z: number) => string,
): { percentile: string; hint: string } {
  const orient = meta?.zscore_orientation ?? "higher_better";
  if (orient === "none") {
    return { percentile: "—", hint: "—" };
  }
  if (orient === "value_as_percentile_0_100") {
    const p = Math.min(100, Math.max(0, val));
    return { percentile: p.toFixed(0), hint: "分项" };
  }
  if (orient === "lower_better") {
    return { percentile: pctFn(-(zs ?? 0)), hint: "相对分位" };
  }
  return { percentile: pctFn(zs ?? 0), hint: "相对分位" };
}

export function labelForFactor(
  metas: FactorFieldInfo[] | undefined,
  key: string,
): string {
  const m = metas?.find((f) => f.key === key);
  return m?.label ?? key;
}
