"use client";

export function SentimentCard() {
  return (
    <article className="glass-panel relative overflow-hidden rounded-[24px] border border-purple-500/20 p-6 shadow-[0_0_34px_rgba(168,85,247,0.12)]">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-20 -left-10 h-48 w-48 rounded-full bg-purple-500/15 blur-3xl"
      />
      <header className="flex flex-col">
        <h3 className="text-sm font-medium tracking-wide text-white">
          Market Sentiment
        </h3>
        <span className="text-[11px] uppercase tracking-[0.3em] text-purple-300/70">
          恐惧贪婪指数
        </span>
      </header>

      <div className="relative mt-4 flex items-center justify-center">
        <SentimentGauge />
      </div>

      <p className="mt-2 text-center text-[11px] text-slate-500">
        数据暂未接入，等待情绪模型就绪
      </p>
    </article>
  );
}

function SentimentGauge() {
  // SVG 半圆仪表占位 —— 数字 --，保留未来接入位点
  const size = 200;
  const stroke = 14;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = Math.PI * r;

  return (
    <svg
      width={size}
      height={size / 2 + 20}
      viewBox={`0 0 ${size} ${size / 2 + 20}`}
      aria-label="sentiment gauge placeholder"
    >
      <defs>
        <linearGradient id="gaugeTrack" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(148,163,184,0.15)" />
          <stop offset="100%" stopColor="rgba(148,163,184,0.25)" />
        </linearGradient>
        <linearGradient id="gaugeValue" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#c4b5fd" />
        </linearGradient>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <path
        d={`M ${stroke / 2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke / 2} ${cy}`}
        fill="none"
        stroke="url(#gaugeTrack)"
        strokeWidth={stroke}
        strokeLinecap="round"
      />
      {/* 占位指针：固定在中间 */}
      <path
        d={`M ${stroke / 2} ${cy} A ${r} ${r} 0 0 1 ${cx} ${stroke / 2}`}
        fill="none"
        stroke="url(#gaugeValue)"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${circumference * 0.5} ${circumference}`}
        filter="url(#glow)"
        opacity={0.5}
      />
      <text
        x={cx}
        y={cy - 4}
        textAnchor="middle"
        className="fill-slate-300"
        style={{ fontSize: 32, fontWeight: 600 }}
      >
        --
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        className="fill-slate-500"
        style={{ fontSize: 11, letterSpacing: "0.2em" }}
      >
        暂无数据
      </text>
    </svg>
  );
}
