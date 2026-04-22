"use client";

import { BarChart3, Home, Settings } from "lucide-react";
import { useState } from "react";

type NavItem = {
  id: "analysis" | "home" | "settings";
  label: string;
  icon: typeof BarChart3;
};

const ITEMS: NavItem[] = [
  { id: "analysis", label: "分析", icon: BarChart3 },
  { id: "home", label: "首页", icon: Home },
  { id: "settings", label: "设置", icon: Settings },
];

export function FloatingNav() {
  const [active, setActive] = useState<NavItem["id"]>("analysis");

  return (
    <nav
      aria-label="主导航"
      className="pointer-events-auto fixed left-4 bottom-10 z-30 hidden lg:block"
    >
      <div className="flex flex-col items-center gap-1 rounded-full border border-white/5 bg-slate-950/70 px-2 py-3 shadow-[0_20px_50px_rgba(2,6,23,0.6)] backdrop-blur-xl">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setActive(item.id)}
              aria-label={item.label}
              aria-pressed={isActive}
              className={
                "group relative flex h-11 w-11 items-center justify-center rounded-full transition-all duration-200 " +
                (isActive
                  ? "bg-cyan-400/15 text-cyan-200 shadow-[0_0_18px_rgba(56,189,248,0.55)]"
                  : "text-slate-400 hover:text-cyan-100 hover:bg-white/5")
              }
            >
              <Icon
                className={
                  "h-5 w-5 transition-transform duration-200 " +
                  (isActive ? "scale-110" : "group-hover:scale-105")
                }
                strokeWidth={1.6}
              />
              <span className="pointer-events-none absolute left-full ml-3 whitespace-nowrap rounded-md border border-white/5 bg-slate-900/95 px-2 py-1 text-[11px] text-slate-300 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100">
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
