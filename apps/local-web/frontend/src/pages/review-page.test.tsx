import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewPage } from "./review-page";

vi.mock("../features/library/card-editor-dialog", () => ({
  CardEditorDialog: (props: {
    open: boolean;
    card: ({ deck_id: number; front: string } & Record<string, unknown>) | null;
    onSaved: (card: { deck_id: number; front: string } & Record<string, unknown>) => void;
  }) => {
    if (!props.open || props.card === null) {
      return null;
    }

    const card = props.card;

    return (
      <div role="dialog" aria-label="Mock card editor">
        <button
          type="button"
          onClick={() =>
            props.onSaved({
              ...card,
              deck_id: card.deck_id + 1,
              front: `${card.front} moved`,
            })
          }
        >
          Save moved card
        </button>
        <button
          type="button"
          onClick={() =>
            props.onSaved({
              ...card,
              front: `${card.front} updated`,
            })
          }
        >
          Save edited card
        </button>
      </div>
    );
  },
}));

function createDeck(id: number, name: string) {
  return {
    id,
    name,
    description: "",
    default_scheduler_type: "sm2_basic",
    visibility: "normal" as const,
    folder_id: 1,
    created_at: "2026-04-03T00:00:00Z",
  };
}

function createCard(id: number, front: string, deckId = 1) {
  return {
    id,
    deck_id: deckId,
    card_type: "recall",
    front,
    back: `${front} answer`,
    render_format: "markdown",
    tags: [],
    status: "active" as const,
    created_at: "2026-04-03T00:00:00Z",
  };
}

function deferredResponse<T>() {
  let resolve: ((value: T) => void) | undefined;
  let reject: ((reason?: unknown) => void) | undefined;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return {
    promise,
    resolve: (value: T) => resolve?.(value),
    reject: (reason?: unknown) => reject?.(reason),
  };
}

describe("ReviewPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the first deck review session instead of the legacy queue endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "What is RAG?")],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByRole("article", { name: /flashcard/i })).toBeInTheDocument();
    expect(screen.getByText("What is RAG?")).toBeInTheDocument();

    await waitFor(() =>
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        expect.stringContaining("/api/review/session?scope=deck&deck_id=1"),
        expect.objectContaining({ method: "GET" }),
      ),
    );
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/review/queue"),
      expect.anything(),
    );
  });

  it("keeps showing the card when again returns it in the backend queue", async () => {
    const card = createCard(7, "Repeat me");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [card],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [card],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: true,
          decision: {
            card_id: 7,
            scheduler_type: "sm2_basic",
            next_due_at: "2026-04-21T00:00:00Z",
            interval_days: 0,
            reason: "again",
            session_action: "repeat_now",
            reinsert_after: 0,
            learning_state: "learning",
            learning_step: 0,
            session_repeats_today: 1,
            hard_attempts_today: 0,
            repetition_delta: 0,
            lapses_delta: 1,
            state_patch: {},
            explainability: {},
          },
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Repeat me")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("article", { name: /flashcard/i }));
    fireEvent.click(screen.getByRole("button", { name: /again/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/review/session/2026-04-20%3Adeck%3A1/submit"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"grade":"again"'),
        }),
      ),
    );
    expect(await screen.findByText("Repeat me")).toBeInTheDocument();
    expect(screen.queryByText(/review complete/i)).not.toBeInTheDocument();
  });

  it("posts undo through the encoded session undo endpoint", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(12, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:12",
          scope: "deck",
          deck_id: 12,
          queue: [createCard(9, "Undo me", 12)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:12",
          scope: "deck",
          deck_id: 12,
          queue: [createCard(9, "Undo me", 12)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
          restored_card_id: 9,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    const undoButton = await screen.findByRole("button", { name: /undo/i });
    fireEvent.click(undoButton);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/review/session/2026-04-20%3Adeck%3A12/undo"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });

  it("disables undo while an undo request is in flight", async () => {
    const undoResponse = deferredResponse<{
      ok: boolean;
      status: number;
      json: () => Promise<unknown>;
    }>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(12, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:12",
          scope: "deck",
          deck_id: 12,
          queue: [createCard(9, "Undo me", 12)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: true,
        }),
      })
      .mockImplementationOnce(() => undoResponse.promise);

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    const undoButton = await screen.findByRole("button", { name: /undo/i });
    fireEvent.click(undoButton);
    fireEvent.click(undoButton);

    expect(undoButton).toBeDisabled();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter((call) => String(call[0]).includes("/api/review/session/2026-04-20%3Adeck%3A12/undo")),
      ).toHaveLength(1),
    );

    undoResponse.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        session_id: "2026-04-20:deck:12",
        scope: "deck",
        deck_id: 12,
        queue: [createCard(9, "Undo me", 12)],
        counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
        can_undo: false,
        restored_card_id: 9,
      }),
    });

    await waitFor(() => expect(undoButton).toBeDisabled());
  });

  it("loads the combined review session when the user switches to all decks", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Deck one card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:all",
          scope: "all",
          deck_id: null,
          queue: [createCard(2, "Combined card", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Deck one card")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /all decks/i }));

    expect(await screen.findByText("Combined card")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/review/session?scope=all"),
        expect.objectContaining({ method: "GET" }),
      ),
    );
  });

  it("does not blank the stage when re-selecting the active deck", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Stay visible", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Stay visible")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /default/i }));
    const defaultButtons = await screen.findAllByRole("button", { name: /^default$/i });
    fireEvent.click(defaultButtons[defaultButtons.length - 1]);

    expect(screen.getByText("Stay visible")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("skips the current card locally by moving it to the end of the queue", async () => {
    const firstCard = createCard(1, "First card");
    const secondCard = createCard(2, "Second card");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [firstCard, secondCard],
          counts: { new: 0, learning: 2, review: 0, relearning: 0, total: 2 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("First card")).toBeInTheDocument();

    const menuButton = screen.getByRole("button", { name: /^menu$/i });
    fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /skip for now/i }));

    expect(await screen.findByText("Second card")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("ignores a stale deck session response after switching to all decks", async () => {
    const deckSession = deferredResponse<{
      ok: boolean;
      status: number;
      json: () => Promise<unknown>;
    }>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockImplementationOnce(() => deckSession.promise)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:all",
          scope: "all",
          deck_id: null,
          queue: [createCard(22, "All decks winner", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        expect.stringContaining("/api/review/session?scope=deck&deck_id=1"),
        expect.objectContaining({ method: "GET" }),
      ),
    );

    fireEvent.click(await screen.findByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /all decks/i }));

    expect(await screen.findByText("All decks winner")).toBeInTheDocument();

    deckSession.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        session_id: "2026-04-20:deck:1",
        scope: "deck",
        deck_id: 1,
        queue: [createCard(11, "Stale deck card", 1)],
        counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
        can_undo: false,
      }),
    });

    await waitFor(() => expect(screen.queryByText("Stale deck card")).not.toBeInTheDocument());
    expect(screen.getByText("All decks winner")).toBeInTheDocument();
  });

  it("retries from an explicit all decks selection without falling back to the first deck", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Deck card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "All decks failed" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:all",
          scope: "all",
          deck_id: null,
          queue: [createCard(3, "Recovered all decks card", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Deck card")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /all decks/i }));
    await waitFor(() => expect(screen.getByText("All decks failed")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("Recovered all decks card")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /all decks/i })).toBeInTheDocument();

    const sessionCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes("/api/review/session?"));

    expect(sessionCalls[sessionCalls.length - 1]).toContain("/api/review/session?scope=all");
    expect(sessionCalls.filter((url) => url.includes("scope=deck&deck_id=1")).length).toBe(1);
  });

  it("keeps retry scoped to the current deck when deck refresh fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:2",
          scope: "deck",
          deck_id: 2,
          queue: [createCard(2, "Algorithms card", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Deck two session failed" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Deck refresh failed" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:2",
          scope: "deck",
          deck_id: 2,
          queue: [createCard(4, "Recovered algorithms card", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /algorithms/i }));

    await waitFor(() => expect(screen.getByText("Deck two session failed")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("Recovered algorithms card")).toBeInTheDocument();

    const sessionCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes("/api/review/session?"));

    expect(sessionCalls[sessionCalls.length - 1]).toContain("/api/review/session?scope=deck&deck_id=2");
    expect(sessionCalls.some((url) => url.includes("/api/review/session?scope=all"))).toBe(false);
  });

  it("reloads the current deck session when an edited card moves to another deck", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Deck one card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(2, "Replacement card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Deck one card")).toBeInTheDocument();

    const menuButton = screen.getByRole("button", { name: /^menu$/i });
    fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /edit card/i }));
    fireEvent.click(await screen.findByRole("button", { name: /save moved card/i }));

    expect(await screen.findByText("Replacement card")).toBeInTheDocument();
    expect(screen.queryByText("Deck one card moved")).not.toBeInTheDocument();

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/review/session?scope=deck&deck_id=1"),
        expect.objectContaining({ method: "GET" }),
      ),
    );
  });

  it("keeps edit actions on the card menu instead of the toolbar menu", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Toolbar target", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Toolbar target")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /review menu/i })).not.toBeInTheDocument();

    const cardMenuButton = screen.getByRole("button", { name: /^menu$/i });
    fireEvent.keyDown(cardMenuButton, { key: "ArrowDown", code: "ArrowDown" });
    fireEvent.click(await screen.findByRole("menuitem", { name: /edit card/i }));

    expect(await screen.findByRole("dialog", { name: /mock card editor/i })).toBeInTheDocument();
  });

  it("ignores a stale scheduled grade response after switching selections", async () => {
    const submitResponse = deferredResponse<{
      ok: boolean;
      status: number;
      json: () => Promise<unknown>;
    }>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Deck one prompt", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockImplementationOnce(() => submitResponse.promise)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:all",
          scope: "all",
          deck_id: null,
          queue: [createCard(2, "All decks prompt", 2)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Deck one prompt")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("article", { name: /flashcard/i }));
    fireEvent.click(screen.getByRole("button", { name: /good/i }));

    fireEvent.click(screen.getByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /all decks/i }));

    expect(await screen.findByText("All decks prompt")).toBeInTheDocument();

    submitResponse.resolve({
      ok: true,
      status: 200,
      json: async () => ({
        session_id: "2026-04-20:deck:1",
        scope: "deck",
        deck_id: 1,
        queue: [createCard(9, "Stale graded deck prompt", 1)],
        counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
        can_undo: true,
        decision: {
          card_id: 1,
          scheduler_type: "sm2_basic",
          next_due_at: "2026-04-21T00:00:00Z",
          interval_days: 1,
          reason: "good",
          session_action: "remove",
          reinsert_after: null,
          learning_state: "review",
          learning_step: 0,
          session_repeats_today: 0,
          hard_attempts_today: 0,
          repetition_delta: 1,
          lapses_delta: 0,
          state_patch: {},
          explainability: {},
        },
      }),
    });

    await waitFor(() => expect(screen.queryByText("Stale graded deck prompt")).not.toBeInTheDocument());
    expect(screen.getByText("All decks prompt")).toBeInTheDocument();
  });

  it("does not duplicate session loads when retry falls back to the first deck", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default"), createDeck(2, "Algorithms")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(1, "Default card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: "Deck two failed" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [createDeck(1, "Default")],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          session_id: "2026-04-20:deck:1",
          scope: "deck",
          deck_id: 1,
          queue: [createCard(3, "Recovered default card", 1)],
          counts: { new: 0, learning: 1, review: 0, relearning: 0, total: 1 },
          can_undo: false,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewPage />);

    expect(await screen.findByText("Default card")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /default/i }));
    fireEvent.click(await screen.findByRole("button", { name: /algorithms/i }));
    await waitFor(() => expect(screen.getByText("Deck two failed")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("Recovered default card")).toBeInTheDocument();

    const sessionCalls = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((url) => url.includes("/api/review/session?"));

    expect(sessionCalls.filter((url) => url.includes("scope=deck&deck_id=1")).length).toBe(2);
    expect(sessionCalls.filter((url) => url.includes("scope=deck&deck_id=2")).length).toBe(1);
  });
});
