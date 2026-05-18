/**
 * Input: ?? children?tone ? className  |  Output: ????????? Badge
 * Output: ?????????????????? UI
 * Role: ??????????????????
 * Use: ?????????????????? Card ? StatusMessage
 */
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type BadgeTone = "primary" | "accent" | "neutral" | "danger" | "success";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = "primary", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
        tone === "primary" && "bg-[var(--primary-soft)] text-[#287968]",
        tone === "accent" && "bg-[var(--accent-soft)] text-[#9A5A20]",
        tone === "neutral" && "bg-slate-100 text-slate-600",
        tone === "danger" && "bg-[var(--danger-soft)] text-[var(--danger)]",
        tone === "success" && "bg-[var(--success-soft)] text-[var(--success)]",
        className,
      )}
      {...props}
    />
  );
}
