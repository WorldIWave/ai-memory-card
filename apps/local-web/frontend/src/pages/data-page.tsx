/**
 * Input: ????????? analytics ??  |  Output: ???????????????
 * Output: ?? Data ????????????????????
 * Role: ??????????????????
 * Use: ??????????? section ???????????? features/analytics
 */
import { Activity, BookOpen, CalendarCheck, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { getStatsAnalytics } from "../api/stats";
import type { StatsAnalyticsRangeDays, StatsAnalyticsRead } from "../api/types";
import { Card, MetricCard, PageHeader, SegmentedControl, Skeleton, StatusMessage } from "../components/ui";
import { DeckActivityCard } from "../features/analytics/deck-activity-card";
import { GradeDistributionCard } from "../features/analytics/grade-distribution-card";
import { StudyTrendChart } from "../features/analytics/study-trend-chart";

export function DataPage() {
  const { t } = useTranslation();
  const [rangeDays, setRangeDays] = useState<StatsAnalyticsRangeDays>(7);
  const [analytics, setAnalytics] = useState<StatsAnalyticsRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setIsLoading(true);
      setErrorText("");

      try {
        const nextAnalytics = await getStatsAnalytics(rangeDays, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setAnalytics(nextAnalytics);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setErrorText(error instanceof Error ? error.message : t("stats_load_error"));
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      controller.abort();
    };
  }, [rangeDays, t]);

  const summary = analytics?.summary;
  const isInitialLoading = isLoading && analytics === null;
  const metrics = [
    {
      label: t("stats_today_reviewed"),
      value: summary?.today_reviewed ?? "-",
      icon: <CalendarCheck size={20} aria-hidden="true" />,
    },
    {
      label: t("stats_total_cards"),
      value: summary?.total_cards ?? "-",
      icon: <BookOpen size={20} aria-hidden="true" />,
    },
    {
      label: t("stats_daily_new_avg"),
      value: summary?.daily_new_avg ?? "-",
      icon: <TrendingUp size={20} aria-hidden="true" />,
    },
    {
      label: t("stats_daily_review_avg"),
      value: summary?.daily_review_avg ?? "-",
      icon: <Activity size={20} aria-hidden="true" />,
    },
  ];

  const rangeOptions = [
    { value: 7 as const, label: t("stats_range_7_days") },
    { value: 30 as const, label: t("stats_range_30_days") },
  ];

  return (
    <div className="data-page">
      <PageHeader
        title={t("stats_heading")}
        description={t("stats_subtitle")}
        action={
          <Link
            to="/history"
            className="inline-flex min-h-10 items-center justify-center rounded-[var(--radius-md)] border border-[var(--border-light)] bg-white px-4 py-2 text-sm font-semibold text-[var(--text-main)] shadow-[var(--shadow-sm)] transition hover:border-[var(--color-primary)]"
          >
            {t("review_history_title", { defaultValue: "Review history" })}
          </Link>
        }
      />

      <div className="data-toolbar">
        <SegmentedControl
          label={t("stats_range_label")}
          value={rangeDays}
          options={rangeOptions}
          onChange={(nextValue) => setRangeDays(nextValue as StatsAnalyticsRangeDays)}
        />
      </div>

      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

      <section className="data-metric-grid" aria-label={t("stats_heading")}>
        {isInitialLoading
          ? Array.from({ length: 4 }).map((_, index) => (
              <Card key={index} className="grid gap-3">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-9 w-16" />
                <Skeleton className="h-3 w-20" />
              </Card>
            ))
          : metrics.map((metric) => (
              <MetricCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
                icon={metric.icon}
              />
            ))}
      </section>

      <StudyTrendChart trend={analytics?.trend ?? null} isLoading={isInitialLoading} />

      <section className="data-analytics-grid">
        <GradeDistributionCard distribution={analytics?.grade_distribution ?? null} isLoading={isInitialLoading} />
        <DeckActivityCard deckActivity={analytics?.deck_activity ?? null} isLoading={isInitialLoading} />
      </section>
    </div>
  );
}
