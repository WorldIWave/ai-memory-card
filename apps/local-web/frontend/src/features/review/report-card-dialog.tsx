/**
 * Input: ?? card?open ?????????  |  Output: ????????
 * Output: ?? reason/note ?????? learning event
 * Role: ?? review ?????????????????
 * Use: ??????????????????????? note ??
 */
import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { reportCard } from "../../api/activity";
import type { CardActivityItem } from "../../api/types";
import { Button, SelectField, StatusMessage, TextareaField } from "../../components/ui";

interface ReportCardDialogProps {
  cardId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRecorded: (activity: CardActivityItem) => void;
  onFixNow: () => void;
}

const REASONS = ["content", "answer", "format", "other"] as const;
type ReportReason = (typeof REASONS)[number];

export function ReportCardDialog({ cardId, open, onOpenChange, onRecorded, onFixNow }: ReportCardDialogProps) {
  const { t } = useTranslation();
  const [reason, setReason] = useState<ReportReason>("content");
  const [note, setNote] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    if (open) {
      setReason("content");
      setNote("");
      setErrorText("");
      setIsSubmitting(false);
    }
  }, [open]);

  async function recordIssue(fixNow: boolean) {
    if (isSubmitting) return;

    setIsSubmitting(true);
    setErrorText("");

    try {
      const activity = await reportCard(cardId, {
        reason,
        note: note.trim(),
      });
      onRecorded(activity);
      onOpenChange(false);
      if (fixNow) {
        onFixNow();
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("report_card_error"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content">
          <Dialog.Title className="mb-3 text-base font-semibold">{t("report_card_title")}</Dialog.Title>
          <Dialog.Description className="mb-4 text-sm text-[var(--text-muted)]">
            {t("report_card_description")}
          </Dialog.Description>

          <div className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
              <span>{t("report_card_reason")}</span>
              <SelectField value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
                <option value="content">{t("report_card_reason_content")}</option>
                <option value="answer">{t("report_card_reason_answer")}</option>
                <option value="format">{t("report_card_reason_format")}</option>
                <option value="other">{t("report_card_reason_other")}</option>
              </SelectField>
            </label>

            <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
              <span>{t("report_card_note")}</span>
              <TextareaField
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={4}
                placeholder={t("report_card_note_placeholder")}
              />
            </label>

            {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
                {t("cancel")}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => void recordIssue(true)} disabled={isSubmitting}>
                {t("report_card_fix_now")}
              </Button>
              <Button size="sm" onClick={() => void recordIssue(false)} disabled={isSubmitting}>
                {isSubmitting ? t("saving") : t("report_card_submit")}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
