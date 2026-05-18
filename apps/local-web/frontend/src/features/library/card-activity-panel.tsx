/**
 * Input: ???????????  |  Output: ???????????????
 * Output: ? note/report/review ?????????????
 * Role: ??????????????????????????
 * Use: ?????????????????????????
 */
import { History } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CardActivityItem } from "../../api/types";
import { EmptyState, Skeleton, StatusMessage } from "../../components/ui";

interface CardActivityPanelProps {
  items: CardActivityItem[];
  isLoading: boolean;
  errorText: string;
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

export function CardActivityPanel({ items, isLoading, errorText }: CardActivityPanelProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="grid gap-2" aria-label={t("card_activity_loading", { defaultValue: "Loading activity" })}>
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }

  if (errorText) {
    return <StatusMessage tone="error">{errorText}</StatusMessage>;
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={History}
        title={t("card_activity_empty_title", { defaultValue: "No activity yet" })}
        description={t("card_activity_empty_description", {
          defaultValue: "Review, evaluate, or report issues to build this card history.",
        })}
        className="min-h-36 rounded-[var(--radius-md)] border border-dashed border-[var(--border-light)] bg-[var(--bg-app)]/70 px-4"
      />
    );
  }

  return (
    <ul className="grid gap-2" aria-label={t("card_activity_heading", { defaultValue: "Recent activity" })}>
      {items.map((item) => (
        <li
          key={item.id}
          className="rounded-[var(--radius-md)] border border-[var(--border-light)] bg-[var(--bg-app)]/60 px-3 py-3"
        >
          <div className="flex items-start justify-between gap-3">
            <strong className="text-sm font-semibold text-[var(--text-main)]">{item.summary}</strong>
            <span className="shrink-0 text-xs text-[var(--text-muted)]">{formatTimestamp(item.created_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
