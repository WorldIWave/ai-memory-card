/**
 * Input: status?message ??? action  |  Output: ????/??/?????
 * Output: ? API ????????????????????
 * Role: ???????????????????
 * Use: ????????????????????? toast ??
 */
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

interface StatusMessageProps extends HTMLAttributes<HTMLParagraphElement> {
  tone?: "success" | "error" | "info";
}

export function StatusMessage({ className, tone = "info", ...props }: StatusMessageProps) {
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "rounded-[var(--radius-md)] px-3 py-2 text-sm",
        tone === "success" && "bg-[var(--success-soft)] text-[var(--success)]",
        tone === "error" && "bg-[var(--danger-soft)] text-[var(--danger)]",
        tone === "info" && "bg-[var(--primary-soft)] text-[#287968]",
        className,
      )}
      {...props}
    />
  );
}
