// Input: mocked deck rows and HTTP delete responses | Output: deck panel deletion confirmation behavior
// Role: Protects Library deck deletion from immediate destructive actions
// Usage: npm run test -- src/features/library/deck-panel.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeckRead } from "../../api/types";
import { DeckPanel } from "./deck-panel";

const deck: DeckRead = {
  id: 3,
  name: "Algorithms",
  description: "",
  default_scheduler_type: "sm2_basic",
  visibility: "normal",
  folder_id: 1,
  created_at: "2026-04-25T00:00:00Z",
};

describe("DeckPanel", () => {
  beforeEach(async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    await import("../../i18n");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks for confirmation before deleting a deck", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => ({}),
    });
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DeckPanel
        decks={[deck]}
        folderId={1}
        selectedId={3}
        cardCountByDeck={{ 3: 2 }}
        onSelect={vi.fn()}
        onEditDeck={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /delete algorithms/i }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(await screen.findByRole("dialog", { name: /delete deck\?/i })).toBeInTheDocument();
    expect(screen.getByText(/deleting a deck also deletes its cards/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/decks/3"),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("keeps the delete confirmation open and shows an error when deletion fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Deck delete failed" }),
    });
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DeckPanel
        decks={[deck]}
        folderId={1}
        selectedId={3}
        cardCountByDeck={{ 3: 2 }}
        onSelect={vi.fn()}
        onEditDeck={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /delete algorithms/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Deck delete failed");
    expect(screen.getByRole("dialog", { name: /delete deck\?/i })).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("constrains long deck names so they do not force horizontal scrolling", () => {
    const longDeck: DeckRead = {
      ...deck,
      name: "A very long generated textbook deck name that should never push the library column sideways",
    };

    const { container } = render(
      <DeckPanel
        decks={[longDeck]}
        folderId={1}
        selectedId={3}
        cardCountByDeck={{ 3: 41 }}
        onSelect={vi.fn()}
        onEditDeck={vi.fn()}
        onChanged={vi.fn()}
      />,
    );

    expect(container.querySelector(".library-deck-main")).toHaveClass("min-w-0");
    expect(container.querySelector(".library-deck-name")).toHaveClass("truncate");
    expect(container.querySelector(".library-deck-scheduler")).toHaveClass("truncate");
  });
});
