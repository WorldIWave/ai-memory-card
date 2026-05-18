/**
 * Input: deckId ??????????  |  Output: ???????????
 * Output: ?? recall/mcq ????????????????
 * Role: ?? Library ??????????
 * Use: ???? cloze ?????????????????????????
 */
import * as Dialog from "@radix-ui/react-dialog";
import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { createCardAssetDraft, uploadCardImage } from "../../api/assets";
import { apiRequest } from "../../api/client";
import { Button } from "../../components/ui";
import { cn } from "../../lib/utils";
import { CardContentEditor } from "../card-content/card-content-editor";

type CardType = "recall" | "mcq";

const CARD_TYPE_TABS: { key: CardType; translationKey: "card_type_qa" | "card_type_mcq" }[] = [
  { key: "recall", translationKey: "card_type_qa" },
  { key: "mcq", translationKey: "card_type_mcq" },
];

interface Props {
  deckId: number;
  onCreated: () => void;
  trigger?: ReactElement | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function CreateCardDialog({ deckId, onCreated, trigger, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const [internalOpen, setInternalOpen] = useState(false);
  const [type, setType] = useState<CardType>("recall");
  const [front, setFront] = useState("");
  const [back, setBack] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const dialogOpen = open ?? internalOpen;

  function setDialogOpen(nextOpen: boolean) {
    if (open === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  }

  async function submit() {
    if (!front.trim() || submitting) return;
    setSubmitting(true);
    try {
      await apiRequest("/api/cards", {
        method: "POST",
        body: {
          deck_id: deckId,
          card_type: type,
          front: front.trim(),
          back: back.trim(),
          render_format: "markdown",
          tags: [],
        },
      });
      setFront("");
      setBack("");
      setDraftId(null);
      setDialogOpen(false);
      onCreated();
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!dialogOpen || draftId) {
      return;
    }

    let cancelled = false;
    void createCardAssetDraft()
      .then((draft) => {
        if (!cancelled && typeof draft.draft_id === "string") {
          setDraftId(draft.draft_id);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDraftId(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dialogOpen, draftId]);

  return (
    <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
      {trigger !== null ? (
        <Dialog.Trigger asChild>
          {trigger ?? (
            <Button size="icon" aria-label={t("card_create")}>
              <Plus size={18} aria-hidden="true" />
            </Button>
          )}
        </Dialog.Trigger>
      ) : null}
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content" aria-describedby={undefined}>
          <Dialog.Title className="mb-4 text-base font-semibold">{t("card_create")}</Dialog.Title>
          <div className="mb-4 flex gap-1 rounded-[var(--radius-md)] bg-slate-100 p-1">
            {CARD_TYPE_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setType(tab.key)}
                className={cn(
                  "flex-1 rounded-[var(--radius-md)] py-1.5 text-sm",
                  type === tab.key ? "bg-white font-semibold shadow-[var(--shadow-sm)]" : "text-[var(--text-muted)]",
                )}
              >
                {t(tab.translationKey)}
              </button>
            ))}
          </div>
          <div className="grid gap-3">
            <CardContentEditor
              label={t("card_front_placeholder")}
              value={front}
              onChange={setFront}
              placeholder={t("card_front_placeholder")}
              rows={3}
              uploadImage={draftId ? (file) => uploadCardImage({ file, draftId }) : undefined}
            />
            <CardContentEditor
              label={t("card_back_placeholder")}
              value={back}
              onChange={setBack}
              placeholder={t("card_back_placeholder")}
              rows={3}
              uploadImage={draftId ? (file) => uploadCardImage({ file, draftId }) : undefined}
            />
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDialogOpen(false)} size="sm">
              {t("cancel")}
            </Button>
            <Button onClick={() => void submit()} disabled={submitting} size="sm">
              {submitting ? t("saving") : t("confirm")}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
