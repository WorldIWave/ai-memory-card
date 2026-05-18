/**
 * Input: ??????????session ?????????  |  Output: ?????????? note/eval/report ??
 * Output: ???????????????????????????
 * Role: ?????????????????????
 * Use: ??? undo ??? session ????????????????????
 */
import * as Dialog from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Brain, Maximize2, MessageSquare, Minimize2, MoreVertical, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createCardNote, saveEvaluationRecord, submitEvaluation } from "../../api/activity";
import type {
  CardEvaluationSubmitInput,
  CardRead,
  EvaluationRead,
  ScheduleDecision,
} from "../../api/types";
import { Badge, Button, StatusMessage, TextareaField } from "../../components/ui";
import { cn } from "../../lib/utils";
import { CardContentRenderer } from "../card-content/card-content-renderer";
import { ReportCardDialog } from "./report-card-dialog";

interface ReviewSessionProps {
  card: Pick<CardRead, "id" | "front" | "back" | "card_type">;
  onGrade?: (grade: Grade) => void | Promise<void>;
  onSkip?: () => void;
  onDecision?: (decision: ScheduleDecision) => void;
  onEdit?: (card: Pick<CardRead, "id" | "front" | "back" | "card_type">) => void;
}

const GRADES = ["again", "hard", "good", "easy"] as const;
type Grade = (typeof GRADES)[number];

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName.toLowerCase();
  if (tagName === "input" || tagName === "textarea" || tagName === "select") {
    return true;
  }

  return target.isContentEditable || target.getAttribute("contenteditable") === "true";
}

function gradeFromShortcut(event: KeyboardEvent): Grade | null {
  switch (event.code) {
    case "Digit1":
    case "Numpad1":
      return "again";
    case "Digit2":
    case "Numpad2":
      return "hard";
    case "Digit3":
    case "Numpad3":
      return "good";
    case "Digit4":
    case "Numpad4":
      return "easy";
    default:
      return null;
  }
}

function evaluationErrorMessage(error: unknown, t: (key: string) => string): string {
  const rawMessage = error instanceof Error ? error.message : "";
  const stableCode = rawMessage.split(":", 1)[0].trim();
  const knownCodes = new Set([
    "plugin_not_configured",
    "plugin_unhealthy",
    "provider_auth_failed",
    "provider_unreachable",
    "provider_model_not_found",
    "provider_request_failed",
    "provider_request_timeout",
    "provider_invalid_response",
    "evaluation_prompt_failed",
    "evaluation_parse_failed",
  ]);
  if (knownCodes.has(stableCode)) {
    return t(`evaluation_error_${stableCode}`);
  }
  return rawMessage || t("evaluation_error");
}

export function ReviewSession({ card, onGrade, onSkip, onDecision, onEdit }: ReviewSessionProps) {
  const { t } = useTranslation();
  const evaluationRequestRef = useRef<AbortController | null>(null);
  const noteRequestRef = useRef<AbortController | null>(null);
  const [showAnswer, setShowAnswer] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);
  const [evalText, setEvalText] = useState("");
  const [evaluationResult, setEvaluationResult] = useState<EvaluationRead | null>(null);
  const [evaluationError, setEvaluationError] = useState("");
  const [evaluating, setEvaluating] = useState(false);
  const [savingEvaluation, setSavingEvaluation] = useState(false);
  const [evalExpanded, setEvalExpanded] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  function resetEvaluationState() {
    setEvalText("");
    setEvaluationResult(null);
    setEvaluationError("");
    setEvaluating(false);
    setSavingEvaluation(false);
  }

  function abortEvaluationRequest() {
    evaluationRequestRef.current?.abort();
    evaluationRequestRef.current = null;
  }

  function abortNoteRequest() {
    noteRequestRef.current?.abort();
    noteRequestRef.current = null;
  }

  function handleNoteOpenChange(nextOpen: boolean) {
    setNoteOpen(nextOpen);
    if (!nextOpen) {
      abortNoteRequest();
      setSavingNote(false);
      setNoteError("");
    }
  }

  useEffect(() => {
    abortEvaluationRequest();
    abortNoteRequest();
    setShowAnswer(false);
    setErrorText("");
    setIsSubmitting(false);
    setNoteOpen(false);
    setNote("");
    setNoteError("");
    setSavingNote(false);
    setEvalOpen(false);
    resetEvaluationState();
    setReportOpen(false);
    return () => {
      abortEvaluationRequest();
      abortNoteRequest();
    };
  }, [card.id, card.front, card.back, card.card_type]);

  async function submitGrade(grade: Grade) {
    if (isSubmitting) return;
    setIsSubmitting(true);
    setErrorText("");
    try {
      await onGrade?.(grade);
      setShowAnswer(false);
      setIsSubmitting(false);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("review_submit_error"));
      setIsSubmitting(false);
    }
  }

  function revealAnswer() {
    if (!showAnswer) {
      setShowAnswer(true);
    }
  }

  async function submitEvaluationRequest() {
    const explanation = evalText.trim();
    if (!explanation || evaluating || savingEvaluation) return;
    abortEvaluationRequest();
    const controller = new AbortController();
    evaluationRequestRef.current = controller;
    const payload: CardEvaluationSubmitInput = {
      card_id: card.id,
      target_unit: { text: card.front },
      learner_explanation: explanation,
      persist: false,
    };
    setEvaluationResult(null);
    setEvaluating(true);
    setEvaluationError("");

    try {
      const result = await submitEvaluation(payload, { signal: controller.signal });
      if (controller.signal.aborted || evaluationRequestRef.current !== controller) {
        return;
      }
      setEvaluationResult(result);
    } catch (error) {
      if (controller.signal.aborted || evaluationRequestRef.current !== controller) {
        return;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setEvaluationError(evaluationErrorMessage(error, t));
    } finally {
      if (evaluationRequestRef.current === controller) {
        evaluationRequestRef.current = null;
        setEvaluating(false);
      }
    }
  }

  function handleEvalOpenChange(nextOpen: boolean) {
    setEvalOpen(nextOpen);
    if (!nextOpen) {
      abortEvaluationRequest();
      setEvaluating(false);
      setSavingEvaluation(false);
    }
  }

  function closeAndClearEvaluation() {
    abortEvaluationRequest();
    resetEvaluationState();
    setEvalExpanded(false);
    setEvalOpen(false);
  }

  async function confirmEvaluationRecord() {
    const explanation = evalText.trim();
    if (!evaluationResult || !explanation || evaluating || savingEvaluation) return;
    abortEvaluationRequest();
    const controller = new AbortController();
    evaluationRequestRef.current = controller;
    setSavingEvaluation(true);
    setEvaluationError("");
    try {
      await saveEvaluationRecord(
        {
          card_id: card.id,
          learner_explanation: explanation,
          result: evaluationResult,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted || evaluationRequestRef.current !== controller) {
        return;
      }
      resetEvaluationState();
      setEvalOpen(false);
    } catch (error) {
      if (controller.signal.aborted || evaluationRequestRef.current !== controller) {
        return;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setEvaluationError(t("evaluation_save_error"));
    } finally {
      if (evaluationRequestRef.current === controller) {
        evaluationRequestRef.current = null;
        setSavingEvaluation(false);
      }
    }
  }

  async function saveNote() {
    if (!note.trim()) return;
    abortNoteRequest();
    const controller = new AbortController();
    noteRequestRef.current = controller;
    setSavingNote(true);
    setNoteError("");
    try {
      await createCardNote(card.id, {
        note: note.trim(),
        source: "review",
      }, { signal: controller.signal });
      if (controller.signal.aborted || noteRequestRef.current !== controller) {
        return;
      }
      setNote("");
      setNoteOpen(false);
    } catch (error) {
      if (controller.signal.aborted || noteRequestRef.current !== controller) {
        return;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      setNoteError(t("review_note_save_error"));
    } finally {
      if (noteRequestRef.current === controller) {
        noteRequestRef.current = null;
        setSavingNote(false);
      }
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isEditableTarget(e.target)) {
        return;
      }
      if (noteOpen || evalOpen || reportOpen) {
        return;
      }
      if (
        e.code === "Space" &&
        !(e.target instanceof Element && e.target.closest("button, [role='button'], [role='menuitem'], [role='option']"))
      ) {
        e.preventDefault();
        setShowAnswer((v) => !v);
        return;
      }
      if (showAnswer) {
        if (e.target instanceof Element && e.target.closest("[role='menuitem'], [role='option']")) {
          return;
        }

        const grade = gradeFromShortcut(e);
        if (grade) {
          e.preventDefault();
          void submitGrade(grade);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evalOpen, noteOpen, reportOpen, showAnswer, isSubmitting]);

  const gradeLabels: Record<Grade, string> = {
    again: t("review_again"),
    hard: t("review_hard"),
    good: t("review_good"),
    easy: t("review_easy"),
  };

  return (
    <div className="review-session" aria-live="polite">
      <div className="review-session-menu">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label="Menu">
              <MoreVertical size={18} aria-hidden="true" />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="z-50 min-w-[180px] rounded-[var(--radius-md)] border border-[var(--border-light)] bg-white p-1 shadow-[var(--shadow-md)]">
              <DropdownMenu.Item
                onSelect={() => onEdit?.(card)}
                className="cursor-pointer rounded px-3 py-2 text-sm text-[var(--text-muted)] hover:bg-[var(--primary-soft)]"
              >
                {t("review_menu_edit_card")}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => void submitGrade("easy")}
                className="cursor-pointer rounded px-3 py-2 text-sm hover:bg-[var(--primary-soft)]"
              >
                {t("review_menu_mark_known")}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => {
                  onSkip?.();
                  onDecision?.({
                    card_id: card.id,
                    scheduler_type: "",
                    next_due_at: "",
                    interval_days: 0,
                    reason: "skip",
                  });
                }}
                className="cursor-pointer rounded px-3 py-2 text-sm hover:bg-[var(--primary-soft)]"
              >
                {t("review_menu_skip")}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => setReportOpen(true)}
                className="cursor-pointer rounded px-3 py-2 text-sm text-[var(--danger)] hover:bg-[var(--danger-soft)]"
              >
                {t("review_menu_report_error")}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      <article
        className={cn("review-flashcard", showAnswer && "is-revealed")}
        aria-label="Flashcard"
        tabIndex={showAnswer ? undefined : 0}
        onClick={revealAnswer}
      >
        <div className="review-flashcard-face">
          <Badge tone="primary">{card.card_type}</Badge>
          <CardContentRenderer
            className="review-flashcard-prompt"
            content={card.front}
            variant="review"
          />
        </div>
        {showAnswer ? (
          <div className="review-flashcard-answer">
            <CardContentRenderer content={card.back} variant="review" />
          </div>
        ) : null}
      </article>

      {showAnswer ? (
        <div className="review-grade-row">
          {GRADES.map((grade, index) => (
            <button
              key={grade}
              type="button"
              disabled={isSubmitting}
              onClick={() => void submitGrade(grade)}
              className={cn("review-grade-button", `review-grade-${grade}`)}
            >
              <span>{gradeLabels[grade]}</span>
              <small>{index + 1}</small>
            </button>
          ))}
        </div>
      ) : null}

      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

      <div className="review-floating-actions">
        <Button variant="secondary" size="icon" onClick={() => setEvalOpen(true)} aria-label={t("evaluation_button")}>
          <Brain size={18} aria-hidden="true" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          onClick={() => {
            setNoteError("");
            setNoteOpen(true);
          }}
          aria-label={t("review_note_button")}
        >
          <MessageSquare size={18} aria-hidden="true" />
        </Button>
      </div>

      <Dialog.Root open={noteOpen} onOpenChange={handleNoteOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="ui-dialog-overlay" />
          <Dialog.Content className="ui-dialog-content">
            <Dialog.Title className="mb-3 text-base font-semibold">{t("review_note_title")}</Dialog.Title>
            <Dialog.Description className="sr-only">{t("review_note_placeholder")}</Dialog.Description>
            <TextareaField
              autoFocus
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              placeholder={t("review_note_placeholder")}
              aria-label={t("review_note_title")}
            />
            {noteError ? <StatusMessage tone="error">{noteError}</StatusMessage> : null}
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => handleNoteOpenChange(false)} size="sm">
                {t("cancel")}
              </Button>
              <Button onClick={() => void saveNote()} disabled={savingNote} size="sm">
                {savingNote ? t("saving") : t("confirm")}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={evalOpen} onOpenChange={handleEvalOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="ui-dialog-overlay" />
          <Dialog.Content className={cn("ui-dialog-content ui-dialog-content-evaluation", evalExpanded && "is-expanded")}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <Dialog.Title className="text-base font-semibold">{t("evaluation_title")}</Dialog.Title>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("evaluation_minimize")}
                  onClick={() => handleEvalOpenChange(false)}
                >
                  <Minimize2 size={16} aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={evalExpanded ? t("evaluation_restore") : t("evaluation_expand")}
                  onClick={() => setEvalExpanded((value) => !value)}
                >
                  <Maximize2 size={16} aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("evaluation_close")}
                  onClick={closeAndClearEvaluation}
                >
                  <X size={16} aria-hidden="true" />
                </Button>
              </div>
            </div>
            <Dialog.Description className="sr-only">{t("evaluation_description")}</Dialog.Description>
            <div className="mb-3 grid gap-2 rounded-[var(--radius-sm)] border border-[var(--border-light)] bg-[var(--surface-muted)] p-3 text-sm">
              <span className="font-semibold text-[var(--text-muted)]">{t("evaluation_card_context")}</span>
              <div className="grid gap-1">
                <span className="text-xs font-semibold text-[var(--text-muted)]">{t("evaluation_card_front")}</span>
                <CardContentRenderer content={card.front} />
              </div>
              <div className="grid gap-1 border-t border-[var(--border-light)] pt-2">
                <span className="text-xs font-semibold text-[var(--text-muted)]">{t("evaluation_card_back")}</span>
                <CardContentRenderer content={card.back} />
              </div>
            </div>
            <TextareaField
              autoFocus
              value={evalText}
              onChange={(e) => {
                setEvalText(e.target.value);
                setEvaluationResult(null);
                setEvaluationError("");
              }}
              rows={4}
              placeholder={t("evaluation_placeholder")}
            />
            {evaluationError ? <StatusMessage tone="error">{evaluationError}</StatusMessage> : null}
            {evaluationResult ? (
              <div className="mt-4 grid gap-2 rounded-[var(--radius-sm)] border border-[var(--border-light)] bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_mastery")}</span>
                  <strong>{evaluationResult.mastery_score.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_concept")}</span>
                  <strong>{evaluationResult.concept_score.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_mechanism")}</span>
                  <strong>{evaluationResult.mechanism_score.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_boundary")}</span>
                  <strong>{evaluationResult.boundary_score.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_misconception")}</span>
                  <strong>{evaluationResult.misconception_score.toFixed(2)}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>{t("evaluation_confidence")}</span>
                  <strong>{evaluationResult.confidence_score.toFixed(2)}</strong>
                </div>
                <div className="mt-2 border-t border-[var(--border-light)] pt-2">
                  <div className="flex items-center justify-between gap-3">
                    <span>{t("evaluation_misconception_status")}</span>
                    <strong>
                      {evaluationResult.misconception_detected
                        ? t("evaluation_misconception_detected")
                        : t("evaluation_no_misconception")}
                    </strong>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <span>{t("evaluation_certainty_status")}</span>
                    <strong>
                      {evaluationResult.uncertain
                        ? t("evaluation_uncertain")
                        : t("evaluation_stable")}
                    </strong>
                  </div>
                </div>
                {evaluationResult.feedback ? (
                  <p className="text-[var(--text-muted)]">{evaluationResult.feedback}</p>
                ) : null}
                {evaluationResult.weak_points.length > 0 ? (
                  <div className="grid gap-1">
                    <span className="font-semibold">{t("evaluation_weak_points")}</span>
                    <span className="text-[var(--text-muted)]">{evaluationResult.weak_points.join(", ")}</span>
                  </div>
                ) : null}
                {evaluationResult.reinforcement_advice.length > 0 ? (
                  <div className="grid gap-1">
                    <span className="font-semibold">{t("evaluation_reinforcement_advice")}</span>
                    <ul className="list-disc space-y-1 pl-5 text-[var(--text-muted)]">
                      {evaluationResult.reinforcement_advice.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => void confirmEvaluationRecord()}
                disabled={!evaluationResult || evaluating || savingEvaluation}
                size="sm"
              >
                {savingEvaluation ? t("saving") : t("confirm")}
              </Button>
              <Button
                onClick={() => void submitEvaluationRequest()}
                disabled={!evalText.trim() || evaluating || savingEvaluation}
                size="sm"
              >
                {evaluating ? t("evaluating") : t("evaluate")}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <ReportCardDialog
        cardId={card.id}
        open={reportOpen}
        onOpenChange={setReportOpen}
        onRecorded={() => {}}
        onFixNow={() => onEdit?.(card)}
      />
    </div>
  );
}
