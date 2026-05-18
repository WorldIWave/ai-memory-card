// Input: sample cards and grid callbacks | Output: CardGrid rendering and action behavior checks
// Role: Verifies card filtering, editing, trash actions, bulk selection, and the AI import entry point
// Note: Tests stay at component level; LibraryPage covers reload wiring after AI import
// Usage: npm run test -- src/features/library/card-grid.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CardRead } from "../../api/types";
import { CardGrid } from "./card-grid";

const cards: CardRead[] = [
  {
    id: 1,
    deck_id: 10,
    card_type: "recall",
    front: "What is binary search?",
    back: "A divide-and-conquer lookup.",
    render_format: "markdown",
    tags: ["search"],
    status: "active",
    created_at: "2026-04-24T00:00:00Z",
  },
  {
    id: 2,
    deck_id: 10,
    card_type: "recall",
    front: "What is a heap?",
    back: "A tree-backed priority queue.",
    render_format: "markdown",
    tags: [],
    status: "active",
    created_at: "2026-04-24T00:00:00Z",
  },
];

async function openCardActionsMenu() {
  const menuButton = await screen.findByRole("button", { name: /card actions/i });
  fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
}

describe("CardGrid", () => {
  beforeEach(async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => [],
      }),
    );
    await import("../../i18n");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the card surface editable when trash callbacks are absent", async () => {
    const onEditCard = vi.fn();

    const { container } = render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={onEditCard}
        onCreated={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /edit what is binary search\?/i }));

    expect(onEditCard).toHaveBeenCalledWith(cards[0]);
    expect(container.querySelector(".library-card-action-row")).not.toBeInTheDocument();
  });

  it("moves a single card to trash without opening the editor", async () => {
    const onArchiveCard = vi.fn().mockResolvedValue(undefined);
    const onArchiveCards = vi.fn().mockResolvedValue(undefined);
    const onEditCard = vi.fn();

    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={onEditCard}
        onCreated={vi.fn()}
        onArchiveCard={onArchiveCard}
        onArchiveCards={onArchiveCards}
        onOpenTrash={vi.fn()}
      />,
    );

    fireEvent.click(
      await screen.findByRole("button", {
        name: /move what is binary search\? to trash/i,
      }),
    );

    await waitFor(() => expect(onArchiveCard).toHaveBeenCalledWith(cards[0]));
    expect(onEditCard).not.toHaveBeenCalled();
    expect(onArchiveCards).not.toHaveBeenCalled();
  });

  it("selects visible cards and confirms a bulk delete to trash", async () => {
    const onArchiveCard = vi.fn().mockResolvedValue(undefined);
    const onArchiveCards = vi.fn().mockResolvedValue(undefined);

    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onArchiveCard={onArchiveCard}
        onArchiveCards={onArchiveCards}
        onOpenTrash={vi.fn()}
      />,
    );

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /select cards/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is binary search\?/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is a heap\?/i }));

    expect(screen.getByText(/2 selected/i)).toBeInTheDocument();
    expect(screen.queryByText(/move selected to trash/i)).not.toBeInTheDocument();

    const deleteButton = screen.getByRole("button", { name: /delete selected cards/i });
    expect(deleteButton).toHaveAttribute("data-tooltip", "Delete");
    expect(deleteButton).toHaveClass("library-selection-delete-button");
    fireEvent.click(deleteButton);
    expect(await screen.findByText(/delete cards\?/i)).toBeInTheDocument();
    expect(screen.getByText(/deleted cards can be restored from trash/i)).toBeInTheDocument();

    const confirmButton = await screen.findByRole("button", { name: /^confirm$/i });
    const cancelButton = screen.getByRole("button", { name: /^cancel$/i });
    expect(
      confirmButton.compareDocumentPosition(cancelButton) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    fireEvent.click(confirmButton);

    await waitFor(() => expect(onArchiveCards).toHaveBeenCalledWith(cards));
    expect(onArchiveCard).not.toHaveBeenCalled();
  });

  it("uses individual checkmarks instead of select-all or cancel controls", async () => {
    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onArchiveCard={vi.fn().mockResolvedValue(undefined)}
        onArchiveCards={vi.fn().mockResolvedValue(undefined)}
        onOpenTrash={vi.fn()}
      />,
    );

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /select cards/i }));

    expect(screen.queryByRole("button", { name: /select all/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clear selection/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel selection/i })).not.toBeInTheDocument();

    const firstCheckbox = screen.getByRole("checkbox", { name: /select what is binary search\?/i });
    fireEvent.click(firstCheckbox);
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();
    fireEvent.click(firstCheckbox);
    expect(screen.getByText(/0 selected/i)).toBeInTheDocument();
  });

  it("keeps the bulk trash confirmation disabled while archive requests are pending", async () => {
    let resolveArchive: (() => void) | undefined;
    const onArchiveCards = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveArchive = resolve;
        }),
    );

    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onArchiveCard={vi.fn().mockResolvedValue(undefined)}
        onArchiveCards={onArchiveCards}
        onOpenTrash={vi.fn()}
      />,
    );

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /select cards/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is binary search\?/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is a heap\?/i }));
    fireEvent.click(screen.getByRole("button", { name: /delete selected cards/i }));

    const confirmButton = await screen.findByRole("button", { name: /^confirm$/i });
    fireEvent.click(confirmButton);

    await waitFor(() => expect(onArchiveCards).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(confirmButton).toBeDisabled());

    fireEvent.click(confirmButton);
    expect(onArchiveCards).toHaveBeenCalledTimes(1);

    resolveArchive?.();
    await waitFor(() => expect(screen.queryByText(/delete cards\?/i)).not.toBeInTheDocument());
  });

  it("shows a bulk archive error without clearing the current selection", async () => {
    const onArchiveCards = vi.fn().mockRejectedValue(new Error("Bulk archive failed"));

    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onArchiveCard={vi.fn().mockResolvedValue(undefined)}
        onArchiveCards={onArchiveCards}
        onOpenTrash={vi.fn()}
      />,
    );

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /select cards/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is binary search\?/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select what is a heap\?/i }));
    fireEvent.click(screen.getByRole("button", { name: /delete selected cards/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByText("Bulk archive failed")).toBeInTheDocument();
    expect(screen.getByText(/2 selected/i)).toBeInTheDocument();
    expect(screen.queryByText(/delete cards\?/i)).not.toBeInTheDocument();
  });

  it("opens the Library trash entry point from the card toolbar", async () => {
    const onOpenTrash = vi.fn();

    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onArchiveCard={vi.fn().mockResolvedValue(undefined)}
        onArchiveCards={vi.fn().mockResolvedValue(undefined)}
        onOpenTrash={onOpenTrash}
      />,
    );

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /open trash/i }));

    expect(onOpenTrash).toHaveBeenCalledTimes(1);
  });

  it("shows the AI import entry point when an import callback is available", async () => {
    render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
        onAiImported={vi.fn()}
      />,
    );

    await openCardActionsMenu();
    expect(await screen.findByRole("menuitem", { name: /ai import/i })).toBeInTheDocument();
  });

  it("keeps knowledge units hidden from the normal card grid", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [
        {
          id: 99,
          deck_id: 10,
          provider_unit_id: "ku_regularization",
          topic: "Regularization",
          summary: "A method that reduces overfitting.",
          source_document: "regularization.md",
          source_span: null,
          raw_payload: {},
          created_at: "2026-04-24T00:00:00Z",
        },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardGrid
        cards={[{ ...cards[0], knowledge_unit_ref_id: 99 }, { ...cards[1], knowledge_unit_ref_id: 99 }]}
        deckId={10}
        deckName="Machine Learning"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    expect(screen.queryByRole("region", { name: /knowledge units/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Regularization")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders cards as a single column list", () => {
    const { container } = render(
      <CardGrid
        cards={cards}
        deckId={10}
        deckName="Algorithms"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    expect(container.querySelector(".library-card-grid")).toHaveClass("library-card-list");
  });

  it("renders markdown and latex card content in the library", () => {
    const latexCard: CardRead = {
      ...cards[0],
      front: "Formula $E=mc^2$",
      back: "**Energy**",
    };

    const { container } = render(
      <CardGrid
        cards={[latexCard]}
        deckId={10}
        deckName="Physics"
        onEditCard={vi.fn()}
        onCreated={vi.fn()}
      />,
    );

    expect(container.querySelector(".card-content-renderer")).not.toBeNull();
    expect(container.querySelector(".katex")).not.toBeNull();
  });
});
