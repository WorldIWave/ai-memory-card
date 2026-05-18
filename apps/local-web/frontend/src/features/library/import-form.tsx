// Input: onImported(result) 导入成功后的回调，接收 ImportCardsResponse
// Role: Library 导入表单，支持 json/csv/markdown 格式将卡片批量导入到指定卡组
// Note: payload 文本框预填了 JSON 示例；deck_name 为空时由后端自动从 payload 读取
// Usage: <ImportForm onImported={handleImported} />
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type { ImportCardsResponse } from "../../api/types";

interface ImportFormProps {
  onImported: (result: ImportCardsResponse) => void;
}

export function ImportForm({ onImported }: ImportFormProps) {
  const { t } = useTranslation();
  const [format, setFormat] = useState<"json" | "csv" | "markdown">("json");
  const [deckName, setDeckName] = useState("");
  const [payload, setPayload] = useState("{\"deck\":{\"name\":\"ML\"},\"cards\":[{\"card_type\":\"recall\",\"front\":\"Question\",\"back\":\"Answer\",\"render_format\":\"markdown\"}]}");
  const [statusText, setStatusText] = useState<string>("");
  const [errorText, setErrorText] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorText("");
    setStatusText("");

    try {
      const response = await apiRequest<ImportCardsResponse>("/api/imports/cards", {
        method: "POST",
        body: {
          format,
          deck_name: deckName.trim() || undefined,
          payload,
        },
      });
      setStatusText(t("import_success", { count: response.imported_count, deck: response.deck.name }));
      onImported(response);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("import_error"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label>
        {t("import_format")}
        <select aria-label={t("import_format")} value={format} onChange={(event) => setFormat(event.target.value as "json" | "csv" | "markdown") }>
          <option value="json">{t("import_format_json")}</option>
          <option value="csv">{t("import_format_csv")}</option>
          <option value="markdown">{t("import_format_markdown")}</option>
        </select>
      </label>
      <label>
        {t("import_deck_name")}
        <input aria-label={t("import_deck_name")} value={deckName} onChange={(event) => setDeckName(event.target.value)} placeholder={t("import_payload_placeholder")} />
      </label>
      <label>
        {t("import_payload")}
        <textarea aria-label={t("import_payload")} value={payload} onChange={(event) => setPayload(event.target.value)} rows={8} />
      </label>
      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? t("import_button_loading") : t("import_button")}
      </button>
      {statusText ? <p className="status-ok">{statusText}</p> : null}
      {errorText ? <p className="status-error">{errorText}</p> : null}
    </form>
  );
}
