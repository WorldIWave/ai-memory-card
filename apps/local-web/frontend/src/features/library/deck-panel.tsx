/**
 * Input: ??????????????/??/????  |  Output: ?????
 * Output: ?? deck ????????????
 * Role: ?? Library ??????????
 * Use: ???????????????????????? library page
 */
import * as Dialog from "@radix-ui/react-dialog";
import { Layers, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type { DeckRead } from "../../api/types";
import { Badge, Button, ConfirmDialog, EmptyState, TextField } from "../../components/ui";
import { cn } from "../../lib/utils";

interface Props {
  decks: DeckRead[];
  folderId: number | null;
  selectedId: number | null;
  cardCountByDeck?: Record<number, number>;
  onSelect: (id: number) => void;
  onEditDeck: (deck: DeckRead) => void;
  onChanged: () => void;
}

export function DeckPanel({
  decks,
  folderId,
  selectedId,
  cardCountByDeck = {},
  onSelect,
  onEditDeck,
  onChanged,
}: Props) {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DeckRead | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErrorText, setDeleteErrorText] = useState("");
  const filtered = folderId == null ? decks : decks.filter((d) => d.folder_id === folderId);

  async function deleteDeck(deck: DeckRead) {
    if (deleting) return;
    setDeleting(true);
    setDeleteErrorText("");
    try {
      await apiRequest(`/api/decks/${deck.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      onChanged();
    } catch (error) {
      setDeleteErrorText(error instanceof Error ? error.message : t("deck_delete_error"));
    } finally {
      setDeleting(false);
    }
  }

  async function createDeck() {
    if (!newName.trim() || submitting) return;
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiRequest("/api/decks", {
        method: "POST",
        body: { name: newName.trim(), folder_id: folderId ?? 1 },
      });
      setNewName("");
      setDialogOpen(false);
      onChanged();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Create deck failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="library-column library-column-wide" aria-label={t("nav_library")}>
      <div className="library-column-header">
        <div>
          <p className="library-column-kicker">{t("nav_library")}</p>
          <h2>{filtered.length}</h2>
        </div>
        <Layers size={18} aria-hidden="true" />
      </div>

      <div className="library-list">
        {filtered.length === 0 ? (
          <EmptyState
            icon={Layers}
            title={t("library_no_decks")}
            description={t("deck_new")}
            className="min-h-40"
          />
        ) : null}

        {filtered.map((deck) => (
          <div key={deck.id} className={cn("library-deck-card", selectedId === deck.id && "is-selected")}>
            <button onClick={() => onSelect(deck.id)} className="library-deck-main min-w-0 flex-1 text-left">
              <span className="library-deck-name block truncate font-semibold" title={deck.name}>
                {deck.name}
              </span>
              <span className="library-deck-scheduler mt-1 block truncate text-xs text-[var(--text-muted)]">
                {deck.default_scheduler_type}
              </span>
            </button>
            <Badge tone={selectedId === deck.id ? "primary" : "neutral"}>{cardCountByDeck[deck.id] ?? 0}</Badge>
            <button
              onClick={() => onEditDeck(deck)}
              className="library-icon-button library-icon-button-edit"
              aria-label={`${t("deck_edit")} ${deck.name}`}
              title={t("deck_edit")}
            >
              <Pencil size={15} aria-hidden="true" />
            </button>
            <button
              onClick={() => {
                setDeleteErrorText("");
                setDeleteTarget(deck);
              }}
              className="library-icon-button"
              aria-label={`Delete ${deck.name}`}
              title="Delete"
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>

      <Button variant="secondary" onClick={() => setDialogOpen(true)} className="mt-3 w-full">
        <Plus size={16} aria-hidden="true" />
        {t("deck_new")}
      </Button>

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="ui-dialog-overlay" />
          <Dialog.Content className="ui-dialog-content" aria-describedby={undefined}>
            <Dialog.Title className="mb-4 text-base font-semibold">{t("deck_new")}</Dialog.Title>
            <TextField
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void createDeck();
              }}
              placeholder={t("deck_name_placeholder")}
              className="mb-4"
            />
            {errorMsg ? <p className="mb-2 text-sm text-[var(--danger)]">{errorMsg}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDialogOpen(false)} size="sm">
                {t("cancel")}
              </Button>
              <Button onClick={() => void createDeck()} disabled={submitting} size="sm">
                {submitting ? t("saving") : t("confirm")}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) {
            setDeleteTarget(null);
            setDeleteErrorText("");
          }
        }}
        title={t("deck_delete_title")}
        description={t("deck_delete_description")}
        confirmLabel={t("confirm")}
        cancelLabel={t("cancel")}
        destructive
        confirmDisabled={deleting}
        cancelDisabled={deleting}
        actionOrder="confirm-cancel"
        errorText={deleteErrorText}
        onConfirm={() => {
          if (deleteTarget) {
            void deleteDeck(deleteTarget);
          }
        }}
      />
    </section>
  );
}
