/**
 * Input: ???????? rangeDays  |  Output: ?? 7/30 ??????
 * Output: ?????? trend points ????????
 * Role: ?? Data ?????????????
 * Use: ?????????????????????? data page
 */
import { BarChart3 } from "lucide-react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import type { StatsTrendRead } from "../../api/types";
import { Card, EmptyState, Skeleton } from "../../components/ui";

interface StudyTrendChartProps {
  trend: StatsTrendRead | null;
  isLoading: boolean;
}

function formatShortDate(date: string, language: string) {
  const parsedDate = new Date(`${date}T00:00:00`);

  if (Number.isNaN(parsedDate.getTime())) {
    return date;
  }

  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
  }).format(parsedDate);
}

export function StudyTrendChart({ trend, isLoading }: StudyTrendChartProps) {
  const { i18n, t } = useTranslation();
  const points = trend?.points ?? [];

  if (isLoading) {
    return (
      <Card className="data-chart-card" panel>
        <div className="data-chart-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_chart_title")}</h2>
          </div>
          <BarChart3 size={22} aria-hidden="true" />
        </div>
        <div className="data-chart-skeleton">
          <Skeleton className="h-48 w-full" />
          <div className="data-trend-label-skeletons">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-10 w-full" />
            ))}
          </div>
        </div>
      </Card>
    );
  }

  if (!points.length) {
    return (
      <Card className="data-chart-card" panel>
        <div className="data-chart-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_chart_title")}</h2>
          </div>
          <BarChart3 size={22} aria-hidden="true" />
        </div>
        <EmptyState
          icon={BarChart3}
          title={t("stats_chart_empty_title")}
          description={t("stats_chart_empty_description")}
          className="min-h-56"
        />
      </Card>
    );
  }

  const chartWidth = 720;
  const chartHeight = 220;
  const inset = 20;
  const plotWidth = chartWidth - inset * 2;
  const plotHeight = chartHeight - inset * 2;
  const maxReviewCount = Math.max(...points.map((point) => point.review_count), 1);
  const slotWidth = plotWidth / points.length;
  const barWidth = Math.max(8, slotWidth * 0.58);

  return (
    <Card className="data-chart-card" panel>
      <div className="data-chart-header">
        <div>
          <p className="library-column-kicker">{t("nav_data")}</p>
          <h2>{t("stats_chart_title")}</h2>
        </div>
        <BarChart3 size={22} aria-hidden="true" />
      </div>

      <div key={trend?.range_days ?? "trend"} className="data-trend-chart-shell is-animated">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          role="img"
          aria-label={t("stats_chart_title")}
          className="data-trend-chart"
        >
          <line
            x1={inset}
            y1={chartHeight - inset}
            x2={chartWidth - inset}
            y2={chartHeight - inset}
            className="data-trend-baseline"
          />
          {points.map((point, index) => {
            const barHeight = Math.max(4, (point.review_count / maxReviewCount) * plotHeight);
            const x = inset + index * slotWidth + (slotWidth - barWidth) / 2;
            const y = chartHeight - inset - barHeight;

            return (
              <rect
                key={point.date}
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx={Math.min(8, barWidth / 2)}
                className="data-trend-bar"
                style={{ "--bar-index": index } as CSSProperties}
              >
                <title>{`${formatShortDate(point.date, i18n.language)}: ${point.review_count}`}</title>
              </rect>
            );
          })}
        </svg>

        <ol className="data-trend-label-list">
          {points.map((point, index) => (
            <li
              key={point.date}
              className="data-trend-label-item"
              style={{ "--bar-index": index } as CSSProperties}
            >
              <span>{formatShortDate(point.date, i18n.language)}</span>
              <strong>{point.review_count}</strong>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}
