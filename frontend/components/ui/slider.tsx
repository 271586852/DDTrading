"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

import { cn } from "@/lib/utils";

function Slider({
  className,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn(
        "relative flex w-full touch-none select-none items-center py-2",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-900/90 ring-1 ring-inset ring-slate-700/70">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-gradient-to-r from-sky-400 via-cyan-300 to-emerald-400 shadow-[0_0_24px_rgba(34,211,238,0.35)]" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block size-5 rounded-full border border-sky-300/80 bg-white shadow-[0_0_0_4px_rgba(14,165,233,0.15),0_0_30px_rgba(56,189,248,0.45)] transition hover:scale-105 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50" />
    </SliderPrimitive.Root>
  );
}

export { Slider };
