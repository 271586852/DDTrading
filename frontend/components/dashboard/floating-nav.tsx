"use client";

import { BarChart3, Home, Settings } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

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

const POSITION_STORAGE_KEY = "ddtrading-floating-nav-position";
const DRAG_THRESHOLD = 4;

type Position = {
  x: number;
  y: number;
};

const DEFAULT_POSITION: Position = { x: 16, y: 545 };

export function FloatingNav() {
  const [active, setActive] = useState<NavItem["id"]>("analysis");
  const [position, setPosition] = useState<Position>(() => {
    if (typeof window === "undefined") {
      return DEFAULT_POSITION;
    }
    const raw = window.localStorage.getItem(POSITION_STORAGE_KEY);
    if (!raw) return DEFAULT_POSITION;
    try {
      const parsed = JSON.parse(raw) as Position;
      if (Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) {
        return parsed;
      }
    } catch {
      // ignore invalid localStorage payload
    }
    return DEFAULT_POSITION;
  });
  const [dragging, setDragging] = useState(false);
  const navRef = useRef<HTMLElement | null>(null);
  const dragOffsetRef = useRef<Position>({ x: 0, y: 0 });
  const dragStartedAtRef = useRef<Position>({ x: 0, y: 0 });
  const movedRef = useRef(false);

  useEffect(() => {
    window.localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(position));
  }, [position]);

  useEffect(() => {
    const onResize = () => {
      const el = navRef.current;
      if (!el) return;
      const maxX = Math.max(0, window.innerWidth - el.offsetWidth);
      const maxY = Math.max(0, window.innerHeight - el.offsetHeight);
      setPosition((prev) => ({
        x: Math.min(Math.max(0, prev.x), maxX),
        y: Math.min(Math.max(0, prev.y), maxY),
      }));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const handlePointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    const el = navRef.current;
    if (!el) return;
    setDragging(true);
    movedRef.current = false;
    dragStartedAtRef.current = { x: event.clientX, y: event.clientY };
    dragOffsetRef.current = {
      x: event.clientX - position.x,
      y: event.clientY - position.y,
    };
    el.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    if (!dragging) return;
    const el = navRef.current;
    if (!el) return;

    const dx = Math.abs(event.clientX - dragStartedAtRef.current.x);
    const dy = Math.abs(event.clientY - dragStartedAtRef.current.y);
    if (dx > DRAG_THRESHOLD || dy > DRAG_THRESHOLD) {
      movedRef.current = true;
    }

    const maxX = Math.max(0, window.innerWidth - el.offsetWidth);
    const maxY = Math.max(0, window.innerHeight - el.offsetHeight);
    const nextX = event.clientX - dragOffsetRef.current.x;
    const nextY = event.clientY - dragOffsetRef.current.y;
    setPosition({
      x: Math.min(Math.max(0, nextX), maxX),
      y: Math.min(Math.max(0, nextY), maxY),
    });
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    if (!dragging) return;
    const el = navRef.current;
    if (el) {
      el.releasePointerCapture(event.pointerId);
    }
    setDragging(false);
  };

  const handleItemClick = (
    event: ReactMouseEvent<HTMLButtonElement>,
    id: NavItem["id"],
  ) => {
    // 若刚发生拖拽，则阻断按钮点击，避免拖动后误切换 tab。
    if (movedRef.current) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    setActive(id);
  };

  return (
    <nav
      ref={navRef}
      aria-label="主导航"
      className="pointer-events-auto fixed z-30 hidden touch-none select-none lg:block"
      style={{ left: position.x, top: position.y }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    >
      <div
        className={
          "flex cursor-grab flex-col items-center gap-1 rounded-full border border-white/5 bg-slate-950/70 px-2 py-3 shadow-[0_20px_50px_rgba(2,6,23,0.6)] backdrop-blur-xl " +
          (dragging ? "cursor-grabbing" : "")
        }
      >
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              type="button"
              onClick={(event) => handleItemClick(event, item.id)}
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
