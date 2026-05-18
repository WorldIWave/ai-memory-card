// Input: folders/decks/cards API responses and user library actions | Output: the Library workspace
// Role: Coordinates folder/deck selection, card grid, edit dialogs, trash, and AI RAG import refresh
// Note: AI import writes through /api/ai/rag/import-cards, then asks this page to reload library state
// Usage: Routed by the local web app as the main Library page
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../api/client";
import type { CardRead, DeckRead, FolderRead } from "../api/types";
import { Modal } from "../components/ui";
import { CardEditorDialog } from "../features/library/card-editor-dialog";
import { DeckEditDialog, FolderRenameDialog } from "../features/library/entity-edit-dialogs";
import { CardGrid } from "../features/library/card-grid";
import { DeckPanel } from "../features/library/deck-panel";
import { FolderPanel } from "../features/library/folder-panel";
import { TrashPanel } from "../features/library/trash-panel";

function firstDeckIdForFolder(decks: DeckRead[], folderId: number | null): number | null {
  if (folderId == null) {
    return null;
  }
  return decks.find((deck) => deck.folder_id === folderId)?.id ?? null;
}

export function LibraryPage() {
  const { t } = useTranslation();
  const [folders, setFolders] = useState<FolderRead[]>([]);
  const [decks, setDecks] = useState<DeckRead[]>([]);
  const [cards, setCards] = useState<CardRead[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<number | null>(null);
  const [selectedDeck, setSelectedDeck] = useState<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [editingCard, setEditingCard] = useState<CardRead | null>(null);
  const [editingFolder, setEditingFolder] = useState<FolderRead | null>(null);
  const [editingDeck, setEditingDeck] = useState<DeckRead | null>(null);
  const [trashOpen, setTrashOpen] = useState(false);
  const [trashRefreshToken, setTrashRefreshToken] = useState(0);
  const selectedFolderRef = useRef<number | null>(selectedFolder);
  const selectedDeckRef = useRef<number | null>(selectedDeck);

  useEffect(() => {
    selectedFolderRef.current = selectedFolder;
  }, [selectedFolder]);

  useEffect(() => {
    selectedDeckRef.current = selectedDeck;
  }, [selectedDeck]);

  useEffect(() => {
    let ignore = false;

    async function load() {
      const [f, d, c] = await Promise.all([
        apiRequest<FolderRead[]>("/api/folders"),
        apiRequest<DeckRead[]>("/api/decks"),
        apiRequest<CardRead[]>("/api/cards"),
      ]);
      if (ignore) return;
      setFolders(f);
      setDecks(d);
      setCards(c);
      const nextFolder =
        selectedFolderRef.current != null && f.some((folder) => folder.id === selectedFolderRef.current)
          ? selectedFolderRef.current
          : f[0]?.id ?? null;
      const nextDeck =
        selectedDeckRef.current != null &&
        d.some(
          (deck) =>
            deck.id === selectedDeckRef.current &&
            (nextFolder == null || deck.folder_id === nextFolder),
        )
          ? selectedDeckRef.current
          : firstDeckIdForFolder(d, nextFolder);
      setSelectedFolder(nextFolder);
      setSelectedDeck(nextDeck);
    }

    void load();
    return () => {
      ignore = true;
    };
  }, [reloadToken]);

  function reload() {
    setReloadToken((v) => v + 1);
  }

  function handleCardSaved(updated: CardRead) {
    setCards((current) => current.map((card) => (card.id === updated.id ? updated : card)));
    setEditingCard(null);
  }

  function handleCardArchived(archived: CardRead) {
    setCards((current) => current.map((card) => (card.id === archived.id ? archived : card)));
    setEditingCard(null);
  }

  function mergeCard(nextCard: CardRead) {
    setCards((current) => {
      if (current.some((card) => card.id === nextCard.id)) {
        return current.map((card) => (card.id === nextCard.id ? nextCard : card));
      }
      return [...current, nextCard];
    });
  }

  async function archiveCardFromGrid(card: CardRead) {
    const archived = await apiRequest<CardRead>(`/api/cards/${card.id}/archive`, {
      method: "POST",
    });
    mergeCard(archived);
    setTrashRefreshToken((value) => value + 1);
  }

  async function archiveCardsFromGrid(cardsToArchive: CardRead[]) {
    const results = await Promise.allSettled(
      cardsToArchive.map((card) =>
        apiRequest<CardRead>(`/api/cards/${card.id}/archive`, {
          method: "POST",
        }),
      ),
    );
    const archivedCards = results.flatMap((result) => (result.status === "fulfilled" ? [result.value] : []));

    if (archivedCards.length > 0) {
      setCards((current) => {
        const archivedById = new Map(archivedCards.map((card) => [card.id, card]));
        const existingIds = new Set(current.map((card) => card.id));
        return [
          ...current.map((card) => archivedById.get(card.id) ?? card),
          ...archivedCards.filter((card) => !existingIds.has(card.id)),
        ];
      });
      setTrashRefreshToken((value) => value + 1);
    }

    const rejected = results.find((result): result is PromiseRejectedResult => result.status === "rejected");
    if (rejected) {
      throw rejected.reason instanceof Error ? rejected.reason : new Error("Archive failed");
    }
  }

  function handleTrashRestored(restored: CardRead) {
    mergeCard(restored);
  }

  function handleFolderSaved(updated: FolderRead) {
    setFolders((current) => current.map((folder) => (folder.id === updated.id ? updated : folder)));
    setEditingFolder((current) => (current?.id === updated.id ? null : current));
  }

  function handleDeckSaved(updated: DeckRead) {
    setDecks((current) => current.map((deck) => (deck.id === updated.id ? updated : deck)));
    if (selectedDeckRef.current === updated.id && selectedFolderRef.current !== updated.folder_id) {
      setSelectedFolder(updated.folder_id);
    }
    setEditingDeck((current) => (current?.id === updated.id ? null : current));
  }

  const selectedDeckRow = decks.find((deck) => deck.id === selectedDeck) ?? null;
  const cardCountByDeck = cards.reduce<Record<number, number>>((acc, card) => {
    if (card.status === "active") {
      acc[card.deck_id] = (acc[card.deck_id] ?? 0) + 1;
    }
    return acc;
  }, {});

  function handleFolderSelect(folderId: number) {
    setSelectedFolder(folderId);
    setSelectedDeck(firstDeckIdForFolder(decks, folderId));
  }

  return (
    <div className="library-workspace">
      <FolderPanel
        folders={folders}
        selectedId={selectedFolder}
        onSelect={handleFolderSelect}
        onRename={setEditingFolder}
        onChanged={reload}
      />
      <DeckPanel
        decks={decks}
        folderId={selectedFolder}
        selectedId={selectedDeck}
        cardCountByDeck={cardCountByDeck}
        onSelect={setSelectedDeck}
        onEditDeck={setEditingDeck}
        onChanged={reload}
      />
      <CardGrid
        cards={cards}
        deckId={selectedDeck}
        deckName={selectedDeckRow?.name ?? null}
        onEditCard={setEditingCard}
        onCreated={reload}
        onArchiveCard={archiveCardFromGrid}
        onArchiveCards={archiveCardsFromGrid}
        onOpenTrash={() => setTrashOpen(true)}
        onAiImported={reload}
      />
      <CardEditorDialog
        card={editingCard}
        decks={decks}
        open={editingCard !== null}
        onOpenChange={(open) => {
          if (!open) setEditingCard(null);
        }}
        onSaved={handleCardSaved}
        onArchived={handleCardArchived}
      />
      <FolderRenameDialog
        folder={editingFolder}
        open={editingFolder !== null}
        onOpenChange={(open) => {
          if (!open) setEditingFolder(null);
        }}
        onSaved={handleFolderSaved}
      />
      <DeckEditDialog
        deck={editingDeck}
        folders={folders}
        open={editingDeck !== null}
        onOpenChange={(open) => {
          if (!open) setEditingDeck(null);
        }}
        onSaved={handleDeckSaved}
      />
      <Modal
        open={trashOpen}
        onOpenChange={setTrashOpen}
        title={t("trash_heading")}
        description={t("trash_hint")}
      >
        <TrashPanel refreshToken={trashRefreshToken} onRestored={handleTrashRestored} />
      </Modal>
    </div>
  );
}
