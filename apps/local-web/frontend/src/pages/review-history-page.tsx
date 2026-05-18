/**
 * Input: ????????? history ??  |  Output: ????/?????
 * Output: ? review history ?????????????
 * Role: ?????????????????
 * Use: ??????????????????????? utils/???
 */
import { Clock3, History, PencilLine } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { listReviewHistory } from "../api/activity";
import { apiRequest } from "../api/client";
import type { CardRead, DeckRead, ReviewHistoryItem } from "../api/types";
import { CardEditorDialog } from "../features/library/card-editor-dialog";
import { Badge, Button, Card, EmptyState, PageHeader, Skeleton, StatusMessage } from "../components/ui";

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

function gradeTone(grade: string): "danger" | "accent" | "success" | "primary" {
  if (grade === "again") {
    return "danger";
  }
  if (grade === "hard") {
    return "accent";
  }
  if (grade === "easy") {
    return "primary";
  }
  return "success";
}

export function ReviewHistoryPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<ReviewHistoryItem[]>([]);
  const [cards, setCards] = useState<CardRead[]>([]);
  const [decks, setDecks] = useState<DeckRead[]>([]);
  const [editingCard, setEditingCard] = useState<CardRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    let ignore = false;

    async function load() {
      setIsLoading(true);
      setErrorText("");
      try {
        const [history, cardRows, deckRows] = await Promise.all([
          listReviewHistory(),
          apiRequest<CardRead[]>("/api/cards"),
          apiRequest<DeckRead[]>("/api/decks"),
        ]);
        if (ignore) {
          return;
        }
        setItems(history);
        setCards(cardRows);
        setDecks(deckRows);
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("library_error"));
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      ignore = true;
    };
  }, [t]);

  const cardMap = useMemo(() => new Map(cards.map((card) => [card.id, card])), [cards]);

  function handleEditCard(cardId: number) {
    setEditingCard(cardMap.get(cardId) ?? null);
  }

  function handleCardSaved(updated: CardRead) {
    setCards((current) => current.map((card) => (card.id === updated.id ? updated : card)));
    setItems((current) =>
      current.map((item) => (item.card_id === updated.id ? { ...item, card_front: updated.front, deck_id: updated.deck_id } : item)),
    );
    setEditingCard(null);
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title={t("review_history_title", { defaultValue: "Review history" })}
        description={t("review_history_subtitle", {
          defaultValue: "Revisit recent scheduled reviews and jump back into card editing.",
        })}
      />

      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

      {isLoading ? (
        <section className="grid gap-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </section>
      ) : items.length === 0 ? (
        <Card panel>
          <EmptyState
            icon={History}
            title={t("review_history_empty_title", { defaultValue: "No recent reviews yet" })}
            description={t("review_history_empty_description", {
              defaultValue: "Finish a few scheduled reviews and they will appear here.",
            })}
            className="min-h-64"
          />
        </Card>
      ) : (
        <section className="grid gap-3" aria-label={t("review_history_title", { defaultValue: "Review history" })}>
          {items.map((item) => (
            <Card key={item.id} className="grid gap-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="grid gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={gradeTone(item.grade)}>{item.grade}</Badge>
                    {item.deck_name ? <Badge tone="neutral">{item.deck_name}</Badge> : null}
                  </div>
                  <h2 className="text-base font-semibold text-[var(--text-main)]">{item.card_front}</h2>
                </div>
                <Button variant="secondary" size="sm" onClick={() => handleEditCard(item.card_id)}>
                  <PencilLine size={16} aria-hidden="true" />
                  {t("card_edit")}
                </Button>
              </div>

              <div className="flex flex-wrap items-center gap-4 text-sm text-[var(--text-muted)]">
                <span className="inline-flex items-center gap-1.5">
                  <Clock3 size={14} aria-hidden="true" />
                  {formatTimestamp(item.reviewed_at)}
                </span>
                <span>
                  {t("review_history_interval", {
                    defaultValue: "Next interval: {{days}} days",
                    days: item.interval_days ?? 0,
                  })}
                </span>
              </div>
            </Card>
          ))}
        </section>
      )}

      <CardEditorDialog
        card={editingCard}
        decks={decks}
        open={editingCard !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingCard(null);
          }
        }}
        onSaved={handleCardSaved}
      />
    </div>
  );
}
