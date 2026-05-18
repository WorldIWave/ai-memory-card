/**
 * Input: ?? card?deck ?????/????  |  Output: ????????????
 * Output: ?????????????????????
 * Role: ?? library/review ???????????
 * Use: ???????????????? card ????????
 */
import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { listCardActivity } from "../../api/activity";
import { uploadCardImage } from "../../api/assets";
import { apiRequest } from "../../api/client";
import type { CardActivityItem, CardRead, CardUpdateInput, DeckRead } from "../../api/types";
import { Button, SelectField, StatusMessage, TextField } from "../../components/ui";
import { CardContentEditor } from "../card-content/card-content-editor";
import { CardActivityPanel } from "./card-activity-panel";

interface CardEditorDialogProps {
  card: CardRead | null;
  decks: DeckRead[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (card: CardRead) => void;
  onArchived?: (card: CardRead) => void;
}

const USER_CARD_TYPES = ["recall", "mcq"] as const;

function parseTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

export function CardEditorDialog({ card, decks, open, onOpenChange, onSaved, onArchived }: CardEditorDialogProps) {
  const { t } = useTranslation();
  const deckMissing = decks.length === 0;
  const [deckId, setDeckId] = useState(String(card?.deck_id ?? decks[0]?.id ?? 0));
  const [cardType, setCardType] = useState(card?.card_type ?? USER_CARD_TYPES[0]);
  const [front, setFront] = useState(card?.front ?? "");
  const [back, setBack] = useState(card?.back ?? "");
  const [tags, setTags] = useState(card?.tags.join(", ") ?? "");
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [activityItems, setActivityItems] = useState<CardActivityItem[]>([]);
  const [activityError, setActivityError] = useState("");
  const [activityLoading, setActivityLoading] = useState(false);

  useEffect(() => {
    if (!open || !card) {
      return;
    }

    setDeckId(String(card.deck_id));
    setCardType(card.card_type);
    setFront(card.front);
    setBack(card.back);
    setTags(card.tags.join(", "));
    setStatusText("");
    setErrorText("");
    setArchiving(false);
    setActivityItems([]);
    setActivityError("");
  }, [card, open]);

  useEffect(() => {
    if (card || deckId !== "0" || deckMissing) {
      return;
    }

    setDeckId(String(decks[0].id));
  }, [card, deckId, deckMissing, decks]);

  useEffect(() => {
    if (!open || !card) {
      return;
    }

    let cancelled = false;
    setActivityLoading(true);
    setActivityError("");

    void listCardActivity(card.id)
      .then((items) => {
        if (cancelled) {
          return;
        }
        setActivityItems(items);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setActivityError(error instanceof Error ? error.message : t("card_save_error"));
      })
      .finally(() => {
        if (cancelled) {
          return;
        }
        setActivityLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [card, open, t]);

  async function save() {
    if (!card || saving || archiving) {
      return;
    }

    if (deckMissing) {
      setErrorText(t("card_deck_required"));
      return;
    }

    setSaving(true);
    setStatusText("");
    setErrorText("");

    const payload: CardUpdateInput = {
      deck_id: Number(deckId),
      card_type: cardType,
      front: front.trim(),
      back: back.trim(),
      render_format: card.render_format || "markdown",
      tags: parseTags(tags),
    };

    try {
      const updated = await apiRequest<CardRead>(`/api/cards/${card.id}`, {
        method: "PUT",
        body: payload,
      });
      setStatusText(t("card_saved"));
      onSaved(updated);
      onOpenChange(false);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("card_save_error"));
    } finally {
      setSaving(false);
    }
  }

  async function archiveCard() {
    if (!card || archiving || saving) {
      return;
    }

    setArchiving(true);
    setStatusText("");
    setErrorText("");

    try {
      const archived = await apiRequest<CardRead>(`/api/cards/${card.id}/archive`, {
        method: "POST",
      });
      onArchived?.(archived);
      onOpenChange(false);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("archive_error"));
      setArchiving(false);
    }
  }

  const cardTypeOptions = card?.card_type === "cloze"
    ? [...USER_CARD_TYPES, "cloze"]
    : [...USER_CARD_TYPES];

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content">
          <Dialog.Title className="mb-4 text-base font-semibold">{t("card_edit")}</Dialog.Title>
          <Dialog.Description className="mb-4 text-sm text-[var(--text-muted)]">
            {t("card_edit_description")}
          </Dialog.Description>

          <div className="grid gap-3">
            <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
              <span>{t("card_deck_label")}</span>
              <SelectField value={deckId} onChange={(event) => setDeckId(event.target.value)} disabled={decks.length === 0}>
                {decks.map((deck) => (
                  <option key={deck.id} value={String(deck.id)}>
                    {deck.name}
                  </option>
                ))}
              </SelectField>
            </label>

            <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
              <span>{t("card_type_qa")}</span>
              <SelectField value={cardType} onChange={(event) => setCardType(event.target.value)}>
                {cardTypeOptions.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </SelectField>
            </label>

            <CardContentEditor
              label={t("card_front_placeholder")}
              value={front}
              onChange={setFront}
              rows={6}
              uploadImage={card ? (file) => uploadCardImage({ file, cardId: card.id }) : undefined}
            />

            <CardContentEditor
              label={t("card_back_placeholder")}
              value={back}
              onChange={setBack}
              rows={6}
              uploadImage={card ? (file) => uploadCardImage({ file, cardId: card.id }) : undefined}
            />

            <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
              <span>{t("card_tags_label")}</span>
              <TextField
                value={tags}
                onChange={(event) => setTags(event.target.value)}
                placeholder={t("card_tags_placeholder")}
              />
            </label>
          </div>

          <section className="mt-4 grid gap-3">
            <div>
              <h3 className="text-sm font-semibold text-[var(--text-main)]">
                {t("card_activity_heading", { defaultValue: "Recent activity" })}
              </h3>
            </div>
            <CardActivityPanel items={activityItems} isLoading={activityLoading} errorText={activityError} />
          </section>

          {deckMissing ? <StatusMessage tone="error">{t("card_deck_required")}</StatusMessage> : null}
          {statusText ? <StatusMessage tone="success">{statusText}</StatusMessage> : null}
          {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

          <div className="mt-4 flex items-center justify-between gap-2">
            <div>
              {onArchived ? (
                <Button
                  variant="danger"
                  onClick={() => void archiveCard()}
                  disabled={archiving || saving}
                  size="sm"
                >
                  {archiving ? t("archive_button_loading") : t("card_move_to_trash")}
                </Button>
              ) : null}
            </div>
            <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)} size="sm">
              {t("cancel")}
            </Button>
            <Button
              onClick={() => void save()}
              disabled={saving || archiving || deckMissing || !front.trim() || !back.trim()}
              size="sm"
            >
              {saving ? t("saving") : t("card_save")}
            </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
