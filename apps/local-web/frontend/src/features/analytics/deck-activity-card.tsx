/**
 * Input: ?????????  |  Output: deck activity ????
 * Output: ?????? review_count/unique_cards ????????
 * Role: ?? Data ?????????????????
 * Use: ?????????????????????????????
 */
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { DeckActivityRead } from "../../api/types";
import { Card, EmptyState, Skeleton } from "../../components/ui";

interface DeckActivityCardProps {
  deckActivity: DeckActivityRead | null;
  isLoading: boolean;
}

export function DeckActivityCard({ deckActivity, isLoading }: DeckActivityCardProps) {
  const { t } = useTranslation();
  const items = deckActivity?.items ?? [];

  if (isLoading) {
    return (
      <Card className="data-support-card" panel>
        <div className="data-card-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_deck_activity_title")}</h2>
          </div>
          <BookOpen size={20} aria-hidden="true" />
        </div>
        <div className="deck-activity-list">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="deck-activity-row">
              <div className="deck-activity-copy">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-20" />
              </div>
              <div className="deck-activity-metrics">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-20" />
              </div>
            </div>
          ))}
        </div>
      </Card>
    );
  }

  if (!items.length) {
    return (
      <Card className="data-support-card" panel>
        <div className="data-card-header">
          <div>
            <p className="library-column-kicker">{t("nav_data")}</p>
            <h2>{t("stats_deck_activity_title")}</h2>
          </div>
          <BookOpen size={20} aria-hidden="true" />
        </div>
        <EmptyState
          icon={BookOpen}
          title={t("stats_deck_activity_empty_title")}
          description={t("stats_deck_activity_empty_description")}
          className="min-h-48"
        />
      </Card>
    );
  }

  return (
    <Card className="data-support-card" panel>
      <div className="data-card-header">
        <div>
          <p className="library-column-kicker">{t("nav_data")}</p>
          <h2>{t("stats_deck_activity_title")}</h2>
          <p className="data-card-subtitle">{t("stats_deck_activity_subtitle")}</p>
        </div>
        <BookOpen size={20} aria-hidden="true" />
      </div>

      <ol className="deck-activity-list">
        {items.map((item) => (
          <li key={item.deck_id} className="deck-activity-row">
            <div className="deck-activity-copy">
              <h3>{item.deck_name}</h3>
              <p>{t("stats_deck_activity_unique_cards", { count: item.unique_cards })}</p>
            </div>
            <div className="deck-activity-metrics">
              <span>{t("stats_deck_activity_reviews", { count: item.review_count })}</span>
              <span>{t("stats_deck_activity_cards", { count: item.unique_cards })}</span>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
