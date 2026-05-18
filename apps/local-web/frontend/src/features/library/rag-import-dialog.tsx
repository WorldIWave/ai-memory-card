// Input: selected deck id and uploaded text files | Output: imported local cards
// Role: Provides the Library UI entry for calling /api/ai/rag/import-cards through the local backend
// Note: The dialog reads browser-accessible text files; PDF/Word parsing should be added upstream later
// Usage: <RAGImportDialog deckId={deckId} deckName={deckName} onImported={reloadLibrary} />
import type { FormEvent, ReactElement } from "react";
import { cloneElement, useEffect, useMemo, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { useTranslation } from "react-i18next";

import { getRagPluginStatus } from "../../api/ai-plugin";
import { apiRequest } from "../../api/client";
import type {
  PluginStatusRead,
  RAGImportCardsInput,
  RAGImportCardsResponse,
  RAGImportDocumentInput,
} from "../../api/types";
import { Button, FieldShell, Modal, SelectField, StatusMessage } from "../../components/ui";

interface RAGImportDialogProps {
  deckId?: number | null;
  deckName?: string | null;
  onImported: (result: RAGImportCardsResponse) => void;
  trigger?: ReactElement<{ onClick?: () => void }> | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

async function filesToDocuments(files: File[]): Promise<RAGImportDocumentInput[]> {
  return Promise.all(
    files.map(async (file) => ({
      filename: file.name,
      content_type: file.type || "text/plain",
      text: await readTextFile(file),
    })),
  );
}

async function readTextFile(file: File): Promise<string> {
  if (typeof file.arrayBuffer !== "function") {
    if (typeof file.text === "function") {
      return file.text();
    }
    if (typeof Response !== "undefined") {
      return new Response(file).text();
    }
    return readTextWithFileReader(file);
  }

  const buffer = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    try {
      return new TextDecoder("gb18030").decode(buffer);
    } catch {
      return new TextDecoder("utf-8").decode(buffer);
    }
  }
}

function readTextWithFileReader(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error ?? new Error("failed to read file"));
    reader.readAsText(file);
  });
}

function getProgressEstimate(elapsedSeconds: number): { percent: number; labelKey: string } {
  if (elapsedSeconds < 10) {
    return { percent: 12 + Math.floor(elapsedSeconds * 1.2), labelKey: "rag_import_progress_preparing" };
  }
  if (elapsedSeconds < 45) {
    return { percent: 24 + Math.floor((elapsedSeconds - 10) * 0.6), labelKey: "rag_import_progress_extracting" };
  }
  if (elapsedSeconds < 120) {
    return { percent: 45 + Math.floor((elapsedSeconds - 45) * 0.33), labelKey: "rag_import_progress_generating" };
  }
  if (elapsedSeconds < 240) {
    return { percent: 70 + Math.floor((elapsedSeconds - 120) * 0.13), labelKey: "rag_import_progress_optimizing" };
  }
  return { percent: Math.min(95, 86 + Math.floor((elapsedSeconds - 240) * 0.03)), labelKey: "rag_import_progress_waiting" };
}

function formatImportError(error: unknown, fallback: string, timeoutMessage: string): string {
  const message = error instanceof Error ? error.message : fallback;
  const normalized = message.toLowerCase();
  if (normalized.includes("plugin_runtime_request_failed") && normalized.includes("timed out")) {
    return timeoutMessage;
  }
  return message;
}

export function RAGImportDialog({ deckId, deckName, onImported, trigger, open, onOpenChange }: RAGImportDialogProps) {
  const { t, i18n } = useTranslation();
  const initialLanguage = i18n.language?.startsWith("en") ? "en" : "zh";
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [internalOpen, setInternalOpen] = useState(false);
  const [language, setLanguage] = useState(initialLanguage);
  const [files, setFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [pluginStatus, setPluginStatus] = useState<PluginStatusRead | null>(null);
  const dialogOpen = open ?? internalOpen;
  const isPluginReady = pluginStatus?.state === "ready";
  const pluginStateLabel = pluginStatus ? t(`plugin_state_${pluginStatus.state}`) : t("plugin_state_unknown");
  const pluginHealthLabel = t(`plugin_health_${String(pluginStatus?.health?.status ?? "unknown")}`);
  const progress = getProgressEstimate(elapsedSeconds);

  function setDialogOpen(nextOpen: boolean) {
    if (open === undefined) {
      setInternalOpen(nextOpen);
    }
    onOpenChange?.(nextOpen);
  }

  const selectedFileLabel = useMemo(
    () => (files.length === 0 ? t("rag_import_no_files") : t("rag_import_file_count", { count: files.length })),
    [files.length, t],
  );
  const filePickerLabel = useMemo(() => {
    if (files.length === 1) {
      return files[0].name;
    }
    return selectedFileLabel;
  }, [files, selectedFileLabel]);

  function resetMessages() {
    setStatusText("");
    setErrorText("");
  }

  useEffect(() => {
    if (!dialogOpen) {
      return;
    }
    let ignore = false;
    void getRagPluginStatus()
      .then((status) => {
        if (!ignore) {
          setPluginStatus(status);
        }
      })
      .catch((error) => {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("rag_import_error"));
        }
      });
    return () => {
      ignore = true;
    };
  }, [dialogOpen, t]);

  useEffect(() => {
    if (!isSubmitting) {
      setElapsedSeconds(0);
      return;
    }
    const intervalId = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isSubmitting]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetMessages();
    if (pluginStatus?.state !== "ready") {
      setErrorText(t("plugin_not_ready"));
      return;
    }
    if (files.length === 0) {
      setErrorText(t("rag_import_file_required"));
      return;
    }

    setIsSubmitting(true);
    setElapsedSeconds(0);
    try {
      const documents = await filesToDocuments(files);
      const body: RAGImportCardsInput = {
        deck_id: deckId ?? undefined,
        documents,
        generation_prefs: {
          backend: "llm",
          card_types: ["recall", "understanding", "boundary"],
          max_cards_per_unit: 3,
          language,
        },
      };
      const response = await apiRequest<RAGImportCardsResponse>("/api/ai/rag/import-cards", {
        method: "POST",
        body,
      });
      setStatusText(t("rag_import_success", { count: response.imported_count, deck: response.deck.name }));
      onImported(response);
    } catch (error) {
      setErrorText(formatImportError(error, t("rag_import_error"), t("rag_import_error_timeout")));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      {trigger !== null ? (
        trigger ? (
          cloneElement(trigger, { onClick: () => setDialogOpen(true) })
        ) : (
          <Button type="button" variant="secondary" onClick={() => setDialogOpen(true)}>
            <Upload size={16} aria-hidden="true" />
            {t("rag_import_trigger")}
          </Button>
        )
      ) : null}
      <Modal
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t("rag_import_title")}
        description={t("rag_import_description")}
      >
        <form className="form-grid" onSubmit={onSubmit}>
          {pluginStatus ? (
            <StatusMessage tone={isPluginReady ? "success" : "error"}>
              {String(pluginStatus.plugin_id)} · {String(pluginStatus.configuration?.provider_profile ?? "openai_compatible")} ·{" "}
              {pluginStateLabel} · {pluginHealthLabel}
            </StatusMessage>
          ) : null}
          {deckName ? <StatusMessage>{t("rag_import_target_deck", { deck: deckName })}</StatusMessage> : null}
          <FieldShell label={t("rag_import_files")} hint={selectedFileLabel}>
            <input
              ref={fileInputRef}
              className="rag-import-file-input"
              aria-label={t("rag_import_files")}
              type="file"
              multiple
              accept=".txt,.md,.markdown,.jsonl,.json,text/plain,text/markdown,application/json"
              onChange={(event) => {
                resetMessages();
                setFiles(Array.from(event.target.files ?? []));
              }}
            />
            <button
              type="button"
              className="rag-import-file-picker"
              onClick={() => fileInputRef.current?.click()}
              disabled={isSubmitting}
            >
              <Upload size={16} aria-hidden="true" />
              <span>{filePickerLabel}</span>
            </button>
          </FieldShell>
          <div className="grid gap-3 md:grid-cols-1">
            <FieldShell label={t("settings_language")}>
              <SelectField
                aria-label={t("settings_language")}
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
              >
                <option value="zh">{t("settings_language_zh")}</option>
                <option value="en">{t("settings_language_en")}</option>
              </SelectField>
            </FieldShell>
          </div>
          <Button type="submit" disabled={isSubmitting || !isPluginReady}>
            {isSubmitting ? t("rag_import_button_loading") : t("rag_import_button")}
          </Button>
          {isSubmitting ? (
            <div className="rag-import-progress-panel">
              <div className="rag-import-progress-meta">
                <span>{t(progress.labelKey)}</span>
                <span>{t("rag_import_progress_elapsed", { seconds: elapsedSeconds })}</span>
              </div>
              <div
                className="rag-import-progress-track"
                role="progressbar"
                aria-label={t("rag_import_progress_label")}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress.percent}
              >
                <span className="rag-import-progress-fill" style={{ width: `${progress.percent}%` }} />
              </div>
            </div>
          ) : null}
          {statusText ? <StatusMessage tone="success">{statusText}</StatusMessage> : null}
          {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}
        </form>
      </Modal>
    </>
  );
}
