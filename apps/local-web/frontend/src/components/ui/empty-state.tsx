/**
 * Input: ???????????????  |  Output: ???????????
 * Output: ?????????????????????? UI
 * Role: ???????????????????
 * Use: ??????????????????????????
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex min-h-48 flex-col items-center justify-center gap-3 text-center", className)}>
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--primary-soft)] text-[var(--color-primary)]">
        <Icon aria-hidden="true" size={26} />
      </div>
      <div>
        <h3 className="text-base font-semibold text-[var(--text-main)]">{title}</h3>
        <p className="mt-1 max-w-sm text-sm text-[var(--text-muted)]">{description}</p>
      </div>
      {action}
    </div>
  );
}
