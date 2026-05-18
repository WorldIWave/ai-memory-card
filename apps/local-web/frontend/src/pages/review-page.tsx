/**
 * Input: ?????review session API???????  |  Output: ??????session ???????
 * Output: ????????? session?????/?????????
 * Role: ?? review ???? orchestrator??? API ? ReviewSession ??
 * Use: ?????????????????????? features/review/review-session
 */
import { RotateCcw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getReviewSession, submitReviewSession, undoReviewSession } from "../api/review";
import { apiRequest } from "../api/client";
import type { CardRead, DeckRead, ReviewGrade, ReviewSessionRead } from "../api/types";
import { Button, Card, EmptyState, Skeleton, StatusMessage } from "../components/ui";
import { CardEditorDialog } from "../features/library/card-editor-dialog";
import { DeckSwitcher } from "../features/review/deck-switcher";
import { ReviewSession } from "../features/review/review-session";

export function ReviewPage() {
  const { t } = useTranslation();
  const [decks, setDecks] = useState<DeckRead[]>([]);
  const [reviewSession, setReviewSession] = useState<ReviewSessionRead | null>(null);
  const [isLoadingDecks, setIsLoadingDecks] = useState(true);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isUndoing, setIsUndoing] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [selectedDeckId, setSelectedDeckId] = useState<number | null>(null);
  const [editingCard, setEditingCard] = useState<CardRead | null>(null);
  const explicitSelectionRef = useRef(false);
  const sessionRequestIdRef = useRef(0);
  const selectionVersionRef = useRef(0);
  const currentSessionIdRef = useRef<string | null>(null);
  const suppressSessionEffectRef = useRef(false);
  const retrySelectionTargetRef = useRef<number | null | undefined>(undefined);

  useEffect(() => {
    currentSessionIdRef.current = reviewSession?.session_id ?? null;
  }, [reviewSession]);

  function invalidateSelectionGuards() {
    selectionVersionRef.current += 1;
    currentSessionIdRef.current = null;
  }

  function applySelectionChange(deckId: number | null) {
    invalidateSelectionGuards();
    setReviewSession(null);
    setSelectedDeckId(deckId);
  }

  const loadDecks = useCallback(async (applySelection = true) => {
    setIsLoadingDecks(true);
    setErrorText("");
    try {
      const deckRows = await apiRequest<DeckRead[]>("/api/decks");
      setDecks(deckRows);
      if (applySelection) {
        setSelectedDeckId((current) => {
          if (deckRows.length === 0) {
            return null;
          }
          if (explicitSelectionRef.current) {
            if (current === null) {
              return null;
            }
            if (deckRows.some((deck) => deck.id === current)) {
              return current;
            }
            return deckRows[0]?.id ?? null;
          }
          if (current !== null && deckRows.some((deck) => deck.id === current)) {
            return current;
          }
          return deckRows[0]?.id ?? null;
        });
      }
      return deckRows;
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("review_error"));
      return null;
    } finally {
      setIsLoadingDecks(false);
    }
  }, [t]);

  const loadSession = useCallback(
    async (deckId: number | null) => {
      const requestId = ++sessionRequestIdRef.current;
      const selectionVersion = selectionVersionRef.current;
      setIsLoadingSession(true);
      setErrorText("");
      try {
        const session = deckId === null ? await getReviewSession("all") : await getReviewSession("deck", deckId);
        if (requestId !== sessionRequestIdRef.current || selectionVersion !== selectionVersionRef.current) {
          return;
        }
        setReviewSession(session);
      } catch (error) {
        if (requestId !== sessionRequestIdRef.current || selectionVersion !== selectionVersionRef.current) {
          return;
        }
        setReviewSession(null);
        setErrorText(error instanceof Error ? error.message : t("review_error"));
      } finally {
        if (requestId === sessionRequestIdRef.current && selectionVersion === selectionVersionRef.current) {
          setIsLoadingSession(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    void loadDecks();
  }, [loadDecks]);

  useEffect(() => {
    if (isLoadingDecks) {
      return;
    }
    if (suppressSessionEffectRef.current) {
      if (retrySelectionTargetRef.current === undefined) {
        return;
      }
      if (selectedDeckId !== retrySelectionTargetRef.current) {
        return;
      }
      suppressSessionEffectRef.current = false;
      retrySelectionTargetRef.current = undefined;
    }
    if (selectedDeckId === null && decks.length === 0) {
      setReviewSession(null);
      setIsLoadingSession(false);
      return;
    }
    void loadSession(selectedDeckId);
  }, [decks.length, isLoadingDecks, loadSession, selectedDeckId]);

  const currentCard = reviewSession?.queue[0] ?? null;
  const isLoading = isLoadingDecks || isLoadingSession;
  const isDone = !isLoading && !errorText && reviewSession !== null && reviewSession.queue.length === 0;
  const progressText =
    reviewSession && reviewSession.counts.total > 0 && reviewSession.queue.length > 0
      ? t("review_progress", {
          current: reviewSession.counts.total - reviewSession.queue.length + 1,
          total: reviewSession.counts.total,
        })
      : t("review_today");

  const handleUndo = useCallback(async () => {
    if (!reviewSession?.can_undo || isUndoing) {
      return;
    }
    const activeSessionId = reviewSession.session_id;
    const activeSelectionVersion = selectionVersionRef.current;
    setErrorText("");
    setIsUndoing(true);
    try {
      const nextSession = await undoReviewSession(activeSessionId);
      if (
        currentSessionIdRef.current !== activeSessionId ||
        selectionVersionRef.current !== activeSelectionVersion
      ) {
        return;
      }
      setReviewSession(nextSession);
    } catch (error) {
      if (
        currentSessionIdRef.current === activeSessionId &&
        selectionVersionRef.current === activeSelectionVersion
      ) {
        setErrorText(error instanceof Error ? error.message : t("review_undo_error"));
      }
    } finally {
      setIsUndoing(false);
    }
  }, [isUndoing, reviewSession, t]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z") {
        return;
      }
      if (event.target instanceof HTMLElement) {
        const tagName = event.target.tagName.toLowerCase();
        if (tagName === "input" || tagName === "textarea" || tagName === "select") {
          return;
        }
        if (event.target.isContentEditable || event.target.getAttribute("contenteditable") === "true") {
          return;
        }
      }
      event.preventDefault();
      void handleUndo();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleUndo]);

  async function handleGrade(grade: ReviewGrade) {
    if (!reviewSession || !currentCard) {
      return;
    }
    const activeSessionId = reviewSession.session_id;
    const activeSelectionVersion = selectionVersionRef.current;

    const nextSession = await submitReviewSession(reviewSession.session_id, {
      card_id: currentCard.id,
      grade,
      review_mode: "flip_card",
      trigger_type: "scheduled",
    });
    if (
      currentSessionIdRef.current !== activeSessionId ||
      selectionVersionRef.current !== activeSelectionVersion
    ) {
      return;
    }
    setReviewSession(nextSession);
  }

  async function handleRetry() {
    const previousSelection = selectedDeckId;
    suppressSessionEffectRef.current = true;
    retrySelectionTargetRef.current = undefined;
    const deckRows = await loadDecks(false);

    if (deckRows === null) {
      suppressSessionEffectRef.current = false;
      await loadSession(previousSelection);
      return;
    }

    const retryDeckId =
      previousSelection !== null && deckRows.some((deck) => deck.id === previousSelection)
        ? previousSelection
        : previousSelection === null
          ? null
          : deckRows[0]?.id ?? null;

    if (retryDeckId !== previousSelection) {
      retrySelectionTargetRef.current = retryDeckId;
      applySelectionChange(retryDeckId);
      return;
    }

    suppressSessionEffectRef.current = false;
    retrySelectionTargetRef.current = undefined;
    await loadSession(retryDeckId);
  }

  function handleSkip() {
    setReviewSession((current) => {
      if (!current || current.queue.length <= 1) {
        return current;
      }

      const [firstCard, ...rest] = current.queue;
      return {
        ...current,
        queue: [...rest, firstCard],
      };
    });
  }

  function handleCardSaved(updated: CardRead) {
    if (reviewSession?.scope === "deck" && selectedDeckId !== null && updated.deck_id !== selectedDeckId) {
      setEditingCard(null);
      void loadSession(selectedDeckId);
      return;
    }

    setReviewSession((current) =>
      current
        ? {
            ...current,
            queue: current.queue.map((card) => (card.id === updated.id ? updated : card)),
          }
        : current,
    );
    setEditingCard(null);
  }

  return (
    <div className="review-page">
      <Card className="review-toolbar">
        <div className="review-toolbar-main">
          <DeckSwitcher
            decks={decks}
            selectedDeckId={selectedDeckId}
            onSelect={(id) => {
              explicitSelectionRef.current = true;
              if (id === selectedDeckId) {
                return;
              }
              applySelectionChange(id);
            }}
          />
          <span className="review-progress">{progressText}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("review_undo")}
            disabled={!reviewSession?.can_undo || isUndoing}
            onClick={() => void handleUndo()}
          >
            <Undo2 size={18} aria-hidden="true" />
          </Button>
        </div>
      </Card>

      <main className="review-stage">
        {isLoading ? (
          <Card className="review-loading-card">
            <Skeleton className="h-5 w-36" aria-label={t("review_loading")} />
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-10 w-40 self-center" />
          </Card>
        ) : null}

        {errorText ? (
          <Card className="review-state-card">
            <StatusMessage tone="error">{errorText}</StatusMessage>
            <Button onClick={() => void handleRetry()}>
              <RotateCcw size={16} aria-hidden="true" />
              {t("review_retry")}
            </Button>
          </Card>
        ) : null}

        {!isLoading && !errorText && decks.length === 0 ? (
          <Card className="review-state-card">
            <EmptyState
              icon={RotateCcw}
              title={t("review_empty")}
              description={t("library_select_deck_action")}
            />
          </Card>
        ) : null}

        {!isLoading && !errorText && currentCard ? (
          <ReviewSession
            key={`${reviewSession?.session_id ?? "none"}:${reviewSession?.queue.map((card) => card.id).join(",") ?? "empty"}`}
            card={currentCard}
            onGrade={handleGrade}
            onSkip={handleSkip}
            onEdit={(card) => {
              const queueCard = reviewSession?.queue.find((item) => item.id === card.id);
              setEditingCard((queueCard ?? currentCard) as CardRead);
            }}
          />
        ) : null}

        {isDone ? (
          <Card className="review-state-card">
            <EmptyState
              icon={RotateCcw}
              title={t("review_completed")}
              description={t("review_empty")}
            />
          </Card>
        ) : null}
      </main>

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
