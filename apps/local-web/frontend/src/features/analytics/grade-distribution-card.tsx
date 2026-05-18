/**
 * Input: ????????  |  Output: again/hard/good/easy ????
 * Output: ? grade count ? ratio ??????????
 * Role: ?? Data ?????????????
 * Use: ?????????? review ????????
 */
import { Activity } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { GradeDistributionRead, ReviewGrade } from "../../api/types";
import { Card, EmptyState, Skeleton } from "../../components/ui";

interface GradeDistributionCardProps {
  distribution: GradeDistributionRead | null;
  isLoading: boolean;
}

const gradeOrder: ReviewGrade[] = ["again", "hard", "good", "easy"];

export function GradeDistributionCard({ distribution, isLoading }: GradeDistributionCardProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <Card className="data-support-card" panel>
        <div className="data-card-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_grade_distribution_title")}</h2>
          </div>
          <Activity size={20} aria-hidden="true" />
        </div>
        <div className="grade-distribution-list">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="grade-distribution-row">
              <div className="grade-distribution-copy">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-3 w-10" />
              </div>
              <Skeleton className="h-2.5 flex-1" />
              <Skeleton className="h-4 w-14" />
            </div>
          ))}
        </div>
      </Card>
    );
  }

  if (!distribution || distribution.total_reviews === 0) {
    return (
      <Card className="data-support-card" panel>
        <div className="data-card-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_grade_distribution_title")}</h2>
          </div>
          <Activity size={20} aria-hidden="true" />
        </div>
        <EmptyState
          icon={Activity}
          title={t("stats_grade_distribution_empty_title")}
          description={t("stats_grade_distribution_empty_description")}
          className="min-h-48"
        />
      </Card>
    );
  }

  const itemsByGrade = new Map(distribution.items.map((item) => [item.grade, item]));

  return (
    <Card className="data-support-card" panel>
      <div className="data-card-header">
        <div>
          <p className="library-column-kicker">{t("nav_data")}</p>
          <h2>{t("stats_grade_distribution_title")}</h2>
          <p className="data-card-subtitle">
            {t("stats_grade_distribution_total", { count: distribution.total_reviews })}
          </p>
        </div>
        <Activity size={20} aria-hidden="true" />
      </div>

      <ul className="grade-distribution-list">
        {gradeOrder.map((grade) => {
          const item = itemsByGrade.get(grade);
          const count = item?.count ?? 0;
          const percentage = Math.round((item?.ratio ?? 0) * 100);

          return (
            <li key={grade} className="grade-distribution-row">
              <div className="grade-distribution-copy">
                <p className="grade-distribution-label">{t(`review_${grade}`)}</p>
                <p className="grade-distribution-count">{count}</p>
              </div>
              <div className="grade-distribution-meter" aria-hidden="true">
                <span className={`grade-distribution-fill grade-distribution-fill-${grade}`} style={{ width: `${percentage}%` }} />
              </div>
              <strong className="grade-distribution-percent">{percentage}%</strong>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
