// Input: refreshToken 外部刷新信号、onRestored(card) 恢复后的回调
// Role: Library 回收站面板，拉取 archived 卡片列表并支持逐张恢复到 active
// Note: 自行管理数据加载（/api/trash），refreshToken 变化时重新拉取
// Usage: <TrashPanel refreshToken={token} onRestored={handleRestored} />
import { RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type { CardRead } from "../../api/types";
import { Button, ConfirmDialog } from "../../components/ui";

interface TrashPanelProps {
  refreshToken: number;
  onRestored: (card: CardRead) => void;
}

export function TrashPanel({ refreshToken, onRestored }: TrashPanelProps) {
  const { t } = useTranslation();
  const [cards, setCards] = useState<CardRead[]>([]);
  const [errorText, setErrorText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [pendingCardId, setPendingCardId] = useState<number | null>(null);
  const [pendingClear, setPendingClear] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CardRead | null>(null);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [hiddenCardIds, setHiddenCardIds] = useState<number[]>([]);

  useEffect(() => {
    setHiddenCardIds((currentIds) =>
      currentIds.filter((hiddenCardId) =>
        cards.some((card) => card.id === hiddenCardId && card.status === "archived"),
      ),
    );
  }, [cards]);

  const visibleCards = cards.filter((card) => card.status === "archived" && !hiddenCardIds.includes(card.id));

  useEffect(() => {
    let ignore = false;

    async function loadTrash() {
      setIsLoading(true);
      setErrorText("");
      try {
        const trashCards = await apiRequest<CardRead[]>("/api/trash");
        if (!ignore) {
          setCards(trashCards);
        }
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : "Failed to load trash");
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void loadTrash();
    return () => {
      ignore = true;
    };
  }, [refreshToken, reloadToken]);

  async function restoreCard(card: CardRead) {
    setPendingCardId(card.id);
    setErrorText("");

    try {
      const restoredCard = await apiRequest<CardRead>(`/api/cards/${card.id}/restore`, {
        method: "POST",
      });
      onRestored(restoredCard);
      setHiddenCardIds((currentIds) =>
        currentIds.includes(card.id) ? currentIds : [...currentIds, card.id],
      );
      setReloadToken((value) => value + 1);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("trash_restore_error"));
    } finally {
      setPendingCardId(null);
    }
  }

  async function permanentlyDeleteCard(card: CardRead) {
    setPendingCardId(card.id);
    setErrorText("");

    try {
      await apiRequest<void>(`/api/trash/${card.id}`, {
        method: "DELETE",
      });
      setHiddenCardIds((currentIds) =>
        currentIds.includes(card.id) ? currentIds : [...currentIds, card.id],
      );
      setDeleteTarget(null);
      setReloadToken((value) => value + 1);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("trash_delete_error"));
    } finally {
      setPendingCardId(null);
    }
  }

  async function clearTrash() {
    setPendingClear(true);
    setErrorText("");

    try {
      await apiRequest<{ deleted_count: number }>("/api/trash", {
        method: "DELETE",
      });
      setHiddenCardIds((currentIds) => [
        ...currentIds,
        ...visibleCards.map((card) => card.id).filter((id) => !currentIds.includes(id)),
      ]);
      setClearConfirmOpen(false);
      setReloadToken((value) => value + 1);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("trash_clear_error"));
    } finally {
      setPendingClear(false);
    }
  }

  return (
    <section className="settings-card">
      <div className="trash-panel-header">
        <div className="library-section-heading">
          <h3>{t("trash_heading")}</h3>
          <p className="hint-text">{t("trash_hint")}</p>
        </div>
        {visibleCards.length > 0 ? (
          <Button
            type="button"
            variant="danger"
            size="sm"
            onClick={() => setClearConfirmOpen(true)}
            disabled={pendingClear || pendingCardId !== null}
          >
            <Trash2 size={16} aria-hidden="true" />
            {t("trash_clear")}
          </Button>
        ) : null}
      </div>
      {isLoading ? <p className="hint-text">{t("trash_loading")}</p> : null}
      {!isLoading && !errorText && visibleCards.length === 0 ? (
        <p className="hint-text">{t("trash_empty")}</p>
      ) : null}
      {visibleCards.length > 0 ? (
        <ul className="card-action-list">
          {visibleCards.map((card) => {
            const isPending = pendingCardId === card.id;
            return (
              <li key={card.id} className="card-action-row">
                <div>
                  <p className="card-action-title">{card.front}</p>
                  <p className="card-action-meta">
                    {card.card_type} card | {card.status}
                  </p>
                </div>
                <div className="trash-card-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => void restoreCard(card)}
                    disabled={isPending || pendingClear}
                    aria-label={`Restore ${card.front}`}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                    {isPending ? t("trash_restore_loading") : t("trash_restore")}
                  </Button>
                  <Button
                    type="button"
                    variant="danger"
                    size="icon"
                    onClick={() => setDeleteTarget(card)}
                    disabled={isPending || pendingClear}
                    aria-label={t("trash_delete_label", { front: card.front })}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
      {errorText ? <p className="status-error">{errorText}</p> : null}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && pendingCardId === null) {
            setDeleteTarget(null);
          }
        }}
        title={t("trash_delete_title")}
        description={t("trash_delete_description")}
        cancelLabel={t("cancel")}
        confirmLabel={t("confirm")}
        destructive
        confirmDisabled={pendingCardId !== null}
        cancelDisabled={pendingCardId !== null}
        actionOrder="confirm-cancel"
        onConfirm={() => {
          if (deleteTarget) {
            void permanentlyDeleteCard(deleteTarget);
          }
        }}
      />
      <ConfirmDialog
        open={clearConfirmOpen}
        onOpenChange={(open) => {
          if (!pendingClear) {
            setClearConfirmOpen(open);
          }
        }}
        title={t("trash_clear_title")}
        description={t("trash_clear_description")}
        cancelLabel={t("cancel")}
        confirmLabel={t("confirm")}
        destructive
        confirmDisabled={pendingClear}
        cancelDisabled={pendingClear}
        actionOrder="confirm-cancel"
        onConfirm={() => void clearTrash()}
      />
    </section>
  );
}
