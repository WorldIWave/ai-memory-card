// Input: selected deck id and visible cards | Output: compact knowledge-unit overview for the deck
// Role: Fetches stored RAG knowledge units and shows which generated cards point back to each unit
// Note: The panel is read-only; persistence happens in the backend RAG import service
// Usage: <KnowledgeUnitPanel deckId={deckId} cards={filteredCards} />
import { BrainCircuit, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest } from "../../api/client";
import type { CardRead, KnowledgeUnitRead } from "../../api/types";
import { Badge, StatusMessage } from "../../components/ui";

interface KnowledgeUnitPanelProps {
  deckId: number | null;
  cards: CardRead[];
}

export function KnowledgeUnitPanel({ deckId, cards }: KnowledgeUnitPanelProps) {
  const { t } = useTranslation();
  const [units, setUnits] = useState<KnowledgeUnitRead[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorText, setErrorText] = useState("");

  const linkedCardCountByUnit = useMemo(() => {
    const counts = new Map<number, number>();
    for (const card of cards) {
      if (card.knowledge_unit_ref_id == null) continue;
      counts.set(card.knowledge_unit_ref_id, (counts.get(card.knowledge_unit_ref_id) ?? 0) + 1);
    }
    return counts;
  }, [cards]);
  const hasLinkedCards = linkedCardCountByUnit.size > 0;

  useEffect(() => {
    if (deckId == null || !hasLinkedCards) {
      setUnits([]);
      setErrorText("");
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setErrorText("");

    apiRequest<KnowledgeUnitRead[]>(`/api/ai/knowledge-units?deck_id=${deckId}`, {
      signal: controller.signal,
    })
      .then((nextUnits) => setUnits(Array.isArray(nextUnits) ? nextUnits : []))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setErrorText(error instanceof Error ? error.message : t("knowledge_units_error"));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      });

    return () => controller.abort();
  }, [deckId, hasLinkedCards, t]);

  if (deckId == null || !hasLinkedCards || (!isLoading && !errorText && units.length === 0)) {
    return null;
  }

  return (
    <section className="knowledge-unit-panel" aria-label={t("knowledge_units_heading")}>
      <div className="knowledge-unit-panel-header">
        <div className="knowledge-unit-heading">
          <BrainCircuit size={18} aria-hidden="true" />
          <h3>{t("knowledge_units_heading")}</h3>
        </div>
        <Badge tone="neutral">{t("knowledge_units_count", { count: units.length })}</Badge>
      </div>

      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}
      {isLoading ? <StatusMessage>{t("knowledge_units_loading")}</StatusMessage> : null}
      {!isLoading && !errorText ? (
        <div className="knowledge-unit-list">
          {units.map((unit) => {
            const linkedCount = linkedCardCountByUnit.get(unit.id) ?? 0;
            return (
              <article key={unit.id} className="knowledge-unit-item">
                <div className="knowledge-unit-item-main">
                  <h4>{unit.topic}</h4>
                  {unit.summary ? <p>{unit.summary}</p> : null}
                </div>
                <div className="knowledge-unit-item-meta">
                  <Badge tone="primary">{t("knowledge_unit_linked_cards", { count: linkedCount })}</Badge>
                  {unit.source_document ? (
                    <span className="knowledge-unit-source">
                      <FileText size={14} aria-hidden="true" />
                      {unit.source_document}
                    </span>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
