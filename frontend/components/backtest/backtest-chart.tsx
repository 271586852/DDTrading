"use client";

import type { EChartsOption } from "echarts";
import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

import type { BacktestResponse } from "@/types/backtest";

type Props = {
  result: BacktestResponse;
};

const CHART_BG = "transparent";
const GRID_COLOR = "rgba(148, 163, 184, 0.12)";
const AXIS_COLOR = "rgba(148, 163, 184, 0.4)";
const TEXT_COLOR = "#cbd5f5";

export function BacktestChart({ result }: Props) {
  const equityOption = useMemo<EChartsOption>(
    () => buildEquityOption(result),
    [result],
  );
  const priceOption = useMemo<EChartsOption>(
    () => buildPriceOption(result),
    [result],
  );

  return (
    <section className="glass-panel rounded-[24px] border border-cyan-400/15 p-6 shadow-[0_0_40px_rgba(34,211,238,0.08)]">
      <header className="mb-4 flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <p className="text-[11px] uppercase tracking-[0.3em] text-cyan-300/80">
            Strategy Dashboard
          </p>
          <h2 className="text-lg font-semibold tracking-tight text-white">
            权益曲线 & 成交点位
          </h2>
        </div>
        <span className="text-[11px] text-slate-500">
          powered by AKQuant · ECharts
        </span>
      </header>

      <div className="flex flex-col gap-6">
        <div className="rounded-2xl border border-white/5 bg-slate-950/40 p-3">
          <ReactECharts
            key={`equity-${result.symbol}-${result.effective_range.start}-${result.effective_range.end}`}
            option={equityOption}
            style={{ height: 320, width: "100%" }}
            notMerge
            lazyUpdate
            opts={{ renderer: "canvas" }}
            theme="dark-quant"
          />
        </div>

        <div className="rounded-2xl border border-white/5 bg-slate-950/40 p-3">
          <ReactECharts
            key={`price-${result.symbol}-${result.effective_range.start}-${result.effective_range.end}`}
            option={priceOption}
            style={{ height: 320, width: "100%" }}
            notMerge
            lazyUpdate
            opts={{ renderer: "canvas" }}
            theme="dark-quant"
          />
        </div>
      </div>
    </section>
  );
}

function buildEquityOption(result: BacktestResponse): EChartsOption {
  const equityPoints = result.equity_curve.map((p) => [p.date, p.equity] as [
    string,
    number,
  ]);
  // 回撤以负值展示更直观 (0 ~ -X%)
  const drawdownPoints = result.equity_curve.map((p) => [
    p.date,
    -Math.abs(p.drawdown_pct),
  ] as [string, number]);

  const initialCash = result.initial_cash;

  return {
    backgroundColor: CHART_BG,
    textStyle: { color: TEXT_COLOR },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.95)",
      borderColor: "rgba(56, 189, 248, 0.3)",
      textStyle: { color: TEXT_COLOR },
      axisPointer: { type: "cross", lineStyle: { color: AXIS_COLOR } },
      valueFormatter: (value) =>
        typeof value === "number" ? value.toFixed(2) : String(value ?? "--"),
    },
    legend: {
      data: ["权益", "回撤 %"],
      textStyle: { color: TEXT_COLOR },
      top: 0,
      right: 12,
    },
    grid: [
      {
        left: 60,
        right: 60,
        top: 36,
        height: 180,
        containLabel: false,
      },
      {
        left: 60,
        right: 60,
        top: 240,
        height: 60,
        containLabel: false,
      },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: [
      {
        type: "time",
        gridIndex: 0,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisLabel: { color: TEXT_COLOR, fontSize: 10 },
        splitLine: { show: false },
      },
      {
        type: "time",
        gridIndex: 1,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisLabel: { color: TEXT_COLOR, fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        type: "value",
        name: "权益",
        nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
        scale: true,
        gridIndex: 0,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisLabel: {
          color: TEXT_COLOR,
          fontSize: 10,
          formatter: (value: number) =>
            Math.abs(value) >= 10000
              ? `${(value / 10000).toFixed(1)}万`
              : value.toFixed(0),
        },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
      {
        type: "value",
        name: "回撤 %",
        nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
        max: 0,
        gridIndex: 1,
        axisLine: { lineStyle: { color: AXIS_COLOR } },
        axisLabel: {
          color: TEXT_COLOR,
          fontSize: 10,
          formatter: (value: number) => `${value.toFixed(1)}%`,
        },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
    ],
    series: [
      {
        name: "权益",
        type: "line",
        data: equityPoints,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: "#22d3ee", width: 2 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(34, 211, 238, 0.35)" },
              { offset: 1, color: "rgba(34, 211, 238, 0)" },
            ],
          },
        },
        markLine: {
          symbol: "none",
          silent: true,
          lineStyle: {
            type: "dashed",
            color: "rgba(148, 163, 184, 0.5)",
          },
          label: {
            color: TEXT_COLOR,
            formatter: "初始 {c}",
          },
          data: [{ yAxis: initialCash }],
        },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: "回撤 %",
        type: "line",
        data: drawdownPoints,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: "#f97316", width: 1.4 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(249, 115, 22, 0)" },
              { offset: 1, color: "rgba(249, 115, 22, 0.35)" },
            ],
          },
        },
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
    ],
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0, 1],
        throttle: 50,
      },
      {
        type: "slider",
        xAxisIndex: [0, 1],
        bottom: 4,
        height: 14,
        borderColor: "rgba(148, 163, 184, 0.2)",
        textStyle: { color: TEXT_COLOR, fontSize: 10 },
        dataBackground: {
          lineStyle: { color: "rgba(34, 211, 238, 0.3)" },
          areaStyle: { color: "rgba(34, 211, 238, 0.1)" },
        },
      },
    ],
  };
}

function buildPriceOption(result: BacktestResponse): EChartsOption {
  const pricePoints = result.price_series
    .filter((p) => p.close != null)
    .map((p) => [p.date, p.close as number] as [string, number]);

  const buyMarkers = result.trade_markers
    .filter((m) => m.side === "buy" && m.price != null)
    .map((m) => ({
      coord: [m.date, m.price as number],
      name: "buy",
      symbol: "triangle",
      symbolSize: 11,
      itemStyle: { color: "#f43f5e" },
      label: { show: false },
    }));

  const sellMarkers = result.trade_markers
    .filter((m) => m.side === "sell" && m.price != null)
    .map((m) => ({
      coord: [m.date, m.price as number],
      name: "sell",
      symbol: "triangle",
      symbolRotate: 180,
      symbolSize: 11,
      itemStyle: { color: "#10b981" },
      label: { show: false },
    }));

  return {
    backgroundColor: CHART_BG,
    textStyle: { color: TEXT_COLOR },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.95)",
      borderColor: "rgba(56, 189, 248, 0.3)",
      textStyle: { color: TEXT_COLOR },
      axisPointer: { type: "cross", lineStyle: { color: AXIS_COLOR } },
      valueFormatter: (value) =>
        typeof value === "number" ? value.toFixed(2) : String(value ?? "--"),
    },
    legend: {
      data: ["收盘价", "买入", "卖出"],
      textStyle: { color: TEXT_COLOR },
      top: 0,
      right: 12,
    },
    grid: {
      left: 60,
      right: 60,
      top: 36,
      bottom: 52,
      containLabel: false,
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 10 },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      name: "价格",
      nameTextStyle: { color: TEXT_COLOR, fontSize: 11 },
      scale: true,
      axisLine: { lineStyle: { color: AXIS_COLOR } },
      axisLabel: { color: TEXT_COLOR, fontSize: 10 },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series: [
      {
        name: "收盘价",
        type: "line",
        data: pricePoints,
        showSymbol: false,
        smooth: false,
        lineStyle: { color: "#a78bfa", width: 1.6 },
      },
      {
        name: "买入",
        type: "scatter",
        data: buyMarkers.map((m) => m.coord),
        symbol: "triangle",
        symbolSize: 11,
        itemStyle: { color: "#f43f5e" },
        tooltip: { show: true },
      },
      {
        name: "卖出",
        type: "scatter",
        data: sellMarkers.map((m) => m.coord),
        symbol: "triangle",
        symbolRotate: 180,
        symbolSize: 11,
        itemStyle: { color: "#10b981" },
        tooltip: { show: true },
      },
    ],
    dataZoom: [
      { type: "inside", throttle: 50 },
      {
        type: "slider",
        bottom: 4,
        height: 14,
        borderColor: "rgba(148, 163, 184, 0.2)",
        textStyle: { color: TEXT_COLOR, fontSize: 10 },
        dataBackground: {
          lineStyle: { color: "rgba(167, 139, 250, 0.3)" },
          areaStyle: { color: "rgba(167, 139, 250, 0.1)" },
        },
      },
    ],
  };
}
