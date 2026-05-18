// Input: selected deck cards plus edit/create/archive/AI import callbacks | Output: card grid and toolbar
// Role: Shows active cards for one deck and exposes create, trash, bulk archive, and AI import actions
// Note: AI import only triggers the local bridge; file reading and persistence live outside this component
// Usage: <CardGrid cards={cards} deckId={selectedDeck} onAiImported={reload} />
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Archive, BookOpen, CheckSquare, Layers, MoreHorizontal, Plus, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { CardRead, RAGImportCardsResponse } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, EmptyState, StatusMessage } from "../../components/ui";
import { cn } from "../../lib/utils";
import { CardContentRenderer } from "../card-content/card-content-renderer";
import { CreateCardDialog } from "./create-card-dialog";
import { RAGImportDialog } from "./rag-import-dialog";

const MENU_ITEM_CLASS =
  "flex w-full cursor-pointer items-center gap-2 rounded px-3 py-2 text-left text-sm text-[var(--text-main)] outline-none hover:bg-[var(--primary-soft)] focus:bg-[var(--primary-soft)] data-[disabled]:pointer-events-none data-[disabled]:opacity-40";

interface Props {
  cards: CardRead[];
  deckId: number | null;
  deckName?: string | null;
  onEditCard: (card: CardRead) => void;
  onCreated: () => void;
  onArchiveCard?: (card: CardRead) => Promise<void>;
  onArchiveCards?: (cards: CardRead[]) => Promise<void>;
  onOpenTrash?: () => void;
  onAiImported?: (result: RAGImportCardsResponse) => void;
}

export function CardGrid({
  cards,
  deckId,
  deckName,
  onEditCard,
  onCreated,
  onArchiveCard,
  onArchiveCards,
  onOpenTrash,
  onAiImported,
}: Props) {
  const { t } = useTranslation();
  const filtered = useMemo(
    () => (deckId == null ? [] : cards.filter((c) => c.deck_id === deckId && c.status === "active")),
    [cards, deckId],
  );
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [confirmBulkOpen, setConfirmBulkOpen] = useState(false);
  const [pendingArchiveIds, setPendingArchiveIds] = useState<number[]>([]);
  const [errorText, setErrorText] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [aiImportOpen, setAiImportOpen] = useState(false);

  const selectedCards = useMemo(
    () => filtered.filter((card) => selectedIds.includes(card.id)),
    [filtered, selectedIds],
  );
  const canArchiveCards = Boolean(onArchiveCards);
  const hasPendingArchive = pendingArchiveIds.length > 0;

  useEffect(() => {
    setSelectionMode(false);
    setSelectedIds([]);
    setConfirmBulkOpen(false);
    setErrorText("");
    setCreateOpen(false);
    setAiImportOpen(false);
  }, [deckId]);

  useEffect(() => {
    const visibleIds = new Set(filtered.map((card) => card.id));
    setSelectedIds((current) => current.filter((id) => visibleIds.has(id)));
  }, [filtered]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectionMode(false);
      setConfirmBulkOpen(false);
    }
  }, [filtered.length]);

  async function archiveCard(card: CardRead) {
    if (!onArchiveCard) return;

    setErrorText("");
    setPendingArchiveIds((current) => [...current, card.id]);
    try {
      await onArchiveCard(card);
      setSelectedIds((current) => current.filter((id) => id !== card.id));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("archive_error"));
    } finally {
      setPendingArchiveIds((current) => current.filter((id) => id !== card.id));
    }
  }

  function toggleSelected(cardId: number) {
    setSelectedIds((current) =>
      current.includes(cardId) ? current.filter((id) => id !== cardId) : [...current, cardId],
    );
  }

  function toggleSelectionMode() {
    setSelectionMode((current) => {
      const next = !current;
      if (!next) {
        setSelectedIds([]);
        setConfirmBulkOpen(false);
      }
      return next;
    });
    setErrorText("");
  }

  async function archiveSelectedCards() {
    if (!onArchiveCards || selectedCards.length === 0 || hasPendingArchive) return;

    const archiveIds = selectedCards.map((card) => card.id);
    setPendingArchiveIds(archiveIds);
    setErrorText("");

    try {
      await onArchiveCards(selectedCards);
      setSelectedIds([]);
      setSelectionMode(false);
      setConfirmBulkOpen(false);
    } catch (error) {
      setConfirmBulkOpen(false);
      setErrorText(error instanceof Error ? error.message : t("card_bulk_trash_error"));
    } finally {
      setPendingArchiveIds([]);
    }
  }

  return (
    <section className="library-card-panel" aria-label="Cards">
      <div className="library-card-toolbar">
        <div>
          <p className="library-column-kicker">{deckName ?? t("library_select_deck_action")}</p>
          <h2>
            {filtered.length} {t("card_count")}
          </h2>
        </div>
        {deckId != null || onOpenTrash ? (
          <div className="library-card-toolbar-actions">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <Button type="button" variant="secondary" size="icon" aria-label={t("card_actions_menu")}>
                  <MoreHorizontal size={18} aria-hidden="true" />
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content className="library-card-menu-content" align="end">
                  {deckId != null ? (
                    <DropdownMenu.Item className={MENU_ITEM_CLASS} onSelect={() => setCreateOpen(true)}>
                      <Plus size={16} aria-hidden="true" />
                      {t("card_create")}
                    </DropdownMenu.Item>
                  ) : null}
                  {onAiImported && deckId != null ? (
                    <DropdownMenu.Item className={MENU_ITEM_CLASS} onSelect={() => setAiImportOpen(true)}>
                      <Upload size={16} aria-hidden="true" />
                      {t("rag_import_trigger")}
                    </DropdownMenu.Item>
                  ) : null}
                  {canArchiveCards && filtered.length > 0 ? (
                    <DropdownMenu.Item className={MENU_ITEM_CLASS} onSelect={toggleSelectionMode}>
                      <CheckSquare size={16} aria-hidden="true" />
                      {t("card_select_mode")}
                    </DropdownMenu.Item>
                  ) : null}
                  {onOpenTrash ? (
                    <DropdownMenu.Item className={MENU_ITEM_CLASS} onSelect={onOpenTrash}>
                      <Archive size={16} aria-hidden="true" />
                      {t("trash_open")}
                    </DropdownMenu.Item>
                  ) : null}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        ) : null}
      </div>

      {deckId != null ? (
        <CreateCardDialog
          deckId={deckId}
          onCreated={onCreated}
          open={createOpen}
          onOpenChange={setCreateOpen}
          trigger={null}
        />
      ) : null}
      {onAiImported && deckId != null ? (
        <RAGImportDialog
          deckId={deckId}
          deckName={deckName}
          onImported={onAiImported}
          open={aiImportOpen}
          onOpenChange={setAiImportOpen}
          trigger={null}
        />
      ) : null}

      <div className="library-card-body">
        {errorText ? (
          <div className="library-card-status">
            <StatusMessage tone="error">{errorText}</StatusMessage>
          </div>
        ) : null}

        {deckId == null ? (
          <EmptyState
            icon={Layers}
            title={t("library_select_deck")}
            description={t("library_select_deck_action")}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title={t("card_table_empty")}
            description={t("card_create")}
            action={
              <CreateCardDialog
                deckId={deckId}
                onCreated={onCreated}
                trigger={
                  <Button>
                    <Plus size={16} aria-hidden="true" />
                    {t("card_create")}
                  </Button>
                }
              />
            }
          />
        ) : (
          <>
            {canArchiveCards && selectionMode ? (
              <div className="library-selection-toolbar">
                <Badge tone="primary">{t("card_selected_count", { count: selectedCards.length })}</Badge>
                <Button
                  type="button"
                  variant="danger"
                  size="icon"
                  className="library-tooltip-button library-selection-delete-button"
                  aria-label={t("card_bulk_move_to_trash")}
                  data-tooltip={t("delete")}
                  onClick={() => setConfirmBulkOpen(true)}
                  disabled={selectedCards.length === 0 || hasPendingArchive}
                >
                  <Trash2 size={16} aria-hidden="true" />
                </Button>
              </div>
            ) : null}

            <div className="library-card-grid library-card-list">
              {filtered.map((card) => {
                const isSelected = selectedIds.includes(card.id);
                const isArchiving = pendingArchiveIds.includes(card.id);
                const hasCardControls = selectionMode || Boolean(onArchiveCard);

                return (
                  <article
                    key={card.id}
                    className={cn("library-card-preview", isSelected && "is-selected")}
                  >
                    <Card className="library-card-preview-card grid h-full gap-0 p-0 text-sm">
                      <button
                        type="button"
                        className={cn(
                          "library-card-edit-button",
                          !hasCardControls && "library-card-edit-button-full",
                        )}
                        aria-label={`Edit ${card.front}`}
                        onClick={() => onEditCard(card)}
                        disabled={isArchiving || selectionMode}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <CardContentRenderer
                            className="library-card-front-content font-semibold"
                            content={card.front}
                            variant="compact"
                          />
                          <Badge tone="primary">{card.card_type}</Badge>
                        </div>
                        {card.back ? (
                          <CardContentRenderer
                            className="library-card-back-content text-[var(--text-muted)]"
                            content={card.back}
                            variant="compact"
                          />
                        ) : null}
                        {card.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-1.5">
                            {card.tags.slice(0, 3).map((tag) => (
                              <Badge key={tag} tone="neutral">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        ) : null}
                      </button>
                      {hasCardControls ? (
                        <div className="library-card-action-row">
                          {selectionMode ? (
                            <label className="library-card-select">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                aria-label={t("card_select_label", { front: card.front })}
                                onChange={() => toggleSelected(card.id)}
                                disabled={isArchiving || hasPendingArchive}
                              />
                            </label>
                          ) : null}
                          {onArchiveCard ? (
                            <Button
                              type="button"
                              variant="danger"
                              size="icon"
                              className="library-card-trash-button"
                              aria-label={t("card_move_to_trash_label", { front: card.front })}
                              onClick={() => void archiveCard(card)}
                              disabled={isArchiving || hasPendingArchive}
                            >
                              <Trash2 size={16} aria-hidden="true" />
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </Card>
                  </article>
                );
              })}
            </div>

            {canArchiveCards ? (
              <ConfirmDialog
                open={confirmBulkOpen}
                onOpenChange={(open) => {
                  if (!hasPendingArchive) {
                    setConfirmBulkOpen(open);
                  }
                }}
                title={t("card_bulk_trash_title")}
                description={t("card_bulk_trash_description", { count: selectedCards.length })}
                cancelLabel={t("cancel")}
                confirmLabel={t("confirm")}
                destructive
                confirmDisabled={hasPendingArchive}
                cancelDisabled={hasPendingArchive}
                actionOrder="confirm-cancel"
                onConfirm={() => void archiveSelectedCards()}
              />
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
