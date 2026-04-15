"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

import type { RankedStock } from "@/types/scoring";

const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
});

type FactorMiniChartProps = {
  stock: RankedStock;
};

const FACTOR_ORDER: Array<{
  label: string;
  valueKey: keyof RankedStock["factor_zscores"];
  color: string;
}> = [
  {
    label: "PE",
    valueKey: "pe_ratio",
    color: "#38bdf8",
  },
  {
    label: "MOM",
    valueKey: "momentum_20d",
    color: "#22c55e",
  },
  {
    label: "VOL",
    valueKey: "volatility",
    color: "#fb923c",
  },
];

export function FactorMiniChart({ stock }: FactorMiniChartProps) {
  const option: EChartsOption = {
    animation: false,
    grid: {
      top: 8,
      bottom: 10,
      left: 6,
      right: 6,
      containLabel: false,
    },
    xAxis: {
      type: "category",
      data: FACTOR_ORDER.map((item) => item.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: "#64748b",
        fontSize: 9,
      },
    },
    yAxis: {
      type: "value",
      min: -3,
      max: 3,
      axisLabel: { show: false },
      splitLine: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    tooltip: { show: false },
    series: [
      {
        type: "bar",
        data: FACTOR_ORDER.map((item) => ({
          value: Number(stock.factor_zscores[item.valueKey].toFixed(2)),
          itemStyle: {
            color: item.color,
            borderRadius: [4, 4, 0, 0],
            shadowBlur: 14,
            shadowColor: item.color,
            opacity: 0.92,
          },
        })),
        barWidth: 10,
      },
    ],
  };

  return (
    <div className="rounded-2xl border border-slate-800/70 bg-slate-950/70 px-3 py-2">
      <ReactECharts
        option={option}
        style={{ height: 88, width: "100%" }}
        opts={{ renderer: "svg" }}
      />
    </div>
  );
}
