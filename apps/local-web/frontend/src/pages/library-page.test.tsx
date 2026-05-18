// Input: mocked Library API responses and browser actions | Output: page-level Library behavior checks
// Role: Verifies folder/deck/card orchestration, trash flows, and AI RAG import refresh wiring
// Note: Tests mock fetch at the HTTP boundary so component state and real dialogs stay exercised
// Usage: npm run test -- src/pages/library-page.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("LibraryPage", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function openCardActionsMenu() {
    const menuButton = await screen.findByRole("button", { name: /card actions/i });
    fireEvent.keyDown(menuButton, { key: "ArrowDown", code: "ArrowDown" });
  }

  it("renders folder, deck, and card workspace regions from loaded data", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 3,
            deck_id: 2,
            card_type: "recall",
            front: "What is binary search?",
            back: "A divide-and-conquer lookup.",
            render_format: "markdown",
            tags: ["search"],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    expect(await screen.findByRole("region", { name: /folders/i })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: /decks|library/i })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: /cards/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /algorithms.*sm2_basic/i })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /edit what is binary search/i }));
    expect(await screen.findByRole("dialog", { name: /edit card/i })).toBeInTheDocument();
  });

  it("preserves the selected deck after a reload triggered by card creation", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 3,
            name: "Systems",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 4,
            deck_id: 2,
            card_type: "recall",
            front: "Algorithms prompt",
            back: "Algorithms answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 5,
            deck_id: 3,
            card_type: "recall",
            front: "Systems prompt",
            back: "Systems answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ draft_id: "draft-systems-card" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: 6,
          deck_id: 3,
          card_type: "recall",
          front: "Created in systems",
          back: "Created answer.",
          render_format: "markdown",
          tags: [],
          status: "active",
          created_at: "2026-04-19T00:00:00Z",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 3,
            name: "Systems",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 4,
            deck_id: 2,
            card_type: "recall",
            front: "Algorithms prompt",
            back: "Algorithms answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 5,
            deck_id: 3,
            card_type: "recall",
            front: "Systems prompt",
            back: "Systems answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 6,
            deck_id: 3,
            card_type: "recall",
            front: "Created in systems",
            back: "Created answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    fireEvent.click(await screen.findByRole("button", { name: /systems.*sm2_basic/i }));
    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /create card/i }));

    fireEvent.change(await screen.findByPlaceholderText(/front/i), { target: { value: "Created in systems" } });
    fireEvent.change(await screen.findByPlaceholderText(/back/i), { target: { value: "Created answer." } });
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByRole("button", { name: /edit systems prompt/i })).toBeInTheDocument();
  });

  it("switches to a deck in the selected folder instead of keeping a deck from another folder", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          { id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" },
          { id: 2, name: "Work", created_at: "2026-04-19T00:00:00Z" },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 3,
            name: "Systems",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 2,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 4,
            deck_id: 2,
            card_type: "recall",
            front: "Algorithms prompt",
            back: "Algorithms answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
          {
            id: 5,
            deck_id: 3,
            card_type: "recall",
            front: "Systems prompt",
            back: "Systems answer.",
            render_format: "markdown",
            tags: [],
            status: "active",
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    expect(await screen.findByRole("button", { name: /edit algorithms prompt/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^work$/i }));

    expect(await screen.findByRole("button", { name: /systems.*sm2_basic/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /edit systems prompt/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit algorithms prompt/i })).not.toBeInTheDocument();
  });

  it("moves a card to trash from the Library grid and removes it from active cards", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const archivedCard = {
      id: 3,
      deck_id: 2,
      card_type: "recall",
      front: "What is binary search?",
      back: "A divide-and-conquer lookup.",
      render_format: "markdown",
      tags: ["search"],
      status: "archived",
      created_at: "2026-04-19T00:00:00Z",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            ...archivedCard,
            status: "active",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => archivedCard,
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    expect(await screen.findByRole("button", { name: /edit what is binary search/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /move what is binary search\? to trash/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("/api/cards/3/archive"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /edit what is binary search/i })).not.toBeInTheDocument(),
    );
  });

  it("opens trash from Library and restores a trashed card into the active grid", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const archivedCard = {
      id: 7,
      deck_id: 2,
      card_type: "recall",
      front: "What is soft delete?",
      back: "A logical delete.",
      render_format: "markdown",
      tags: [],
      status: "archived",
      created_at: "2026-04-19T00:00:00Z",
    };
    const restoredCard = { ...archivedCard, status: "active" };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => restoredCard,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /open trash/i }));
    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /restore what is soft delete\?/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/7/restore"),
        expect.objectContaining({ method: "POST" }),
      ),
    );

    fireEvent.keyDown(screen.getByRole("dialog", { name: /trash/i }), { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog", { name: /trash/i })).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: /edit what is soft delete/i })).toBeInTheDocument();
  });

  it("moves selected cards to trash through the existing single-card archive API", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const firstCard = {
      id: 4,
      deck_id: 2,
      card_type: "recall",
      front: "Algorithms prompt",
      back: "Algorithms answer.",
      render_format: "markdown",
      tags: [],
      status: "active",
      created_at: "2026-04-19T00:00:00Z",
    };
    const secondCard = {
      id: 5,
      deck_id: 2,
      card_type: "recall",
      front: "Systems prompt",
      back: "Systems answer.",
      render_format: "markdown",
      tags: [],
      status: "active",
      created_at: "2026-04-19T00:00:00Z",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [{ id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" }],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 2,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-19T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [firstCard, secondCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...firstCard, status: "archived" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ...secondCard, status: "archived" }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    expect(await screen.findByRole("button", { name: /edit algorithms prompt/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /edit systems prompt/i })).toBeInTheDocument();

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /select cards/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select algorithms prompt/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /select systems prompt/i }));
    fireEvent.click(screen.getByRole("button", { name: /delete selected cards/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/4/archive"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/5/archive"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /edit algorithms prompt/i })).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /edit systems prompt/i })).not.toBeInTheDocument(),
    );
  });

  it("clears the selected deck and card panel after deleting the last deck", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const folder = { id: 1, name: "Default", created_at: "2026-04-19T00:00:00Z" };
    const deck = {
      id: 2,
      name: "Algorithms",
      description: "",
      default_scheduler_type: "sm2_basic",
      visibility: "normal",
      folder_id: 1,
      created_at: "2026-04-19T00:00:00Z",
    };
    const card = {
      id: 4,
      deck_id: 2,
      card_type: "recall",
      front: "Algorithms prompt",
      back: "Algorithms answer.",
      render_format: "markdown",
      tags: [],
      status: "active",
      created_at: "2026-04-19T00:00:00Z",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [folder],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [deck],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [card],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: async () => ({}),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [folder],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<LibraryPage />);

    expect(await screen.findByRole("button", { name: /edit algorithms prompt/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /delete algorithms/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/decks/2"),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    expect(await screen.findByText(/select a deck to view cards/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit algorithms prompt/i })).not.toBeInTheDocument();
  });

  it("reloads the selected deck after AI RAG import finishes", async () => {
    await import("../i18n");
    const { LibraryPage } = await import("./library-page");

    const folder = { id: 1, name: "Default", created_at: "2026-04-24T00:00:00Z" };
    const deck = {
      id: 2,
      name: "Machine Learning",
      description: "",
      default_scheduler_type: "sm2_basic",
      visibility: "normal",
      folder_id: 1,
      created_at: "2026-04-24T00:00:00Z",
    };
    const importedCard = {
      id: 8,
      deck_id: 2,
      knowledge_unit_ref_id: 9,
      card_type: "recall",
      front: "What does regularization reduce?",
      back: "Overfitting.",
      render_format: "markdown",
      tags: ["ai-generated"],
      status: "active",
      created_at: "2026-04-24T00:00:00Z",
    };

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [folder],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [deck],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          plugin_id: "rag-core",
          plugin_name: "RAG Card Generation",
          plugin_version: "0.1.0",
          protocol_version: "1",
          enabled: true,
          state: "ready",
          health: { status: "ok" },
          capabilities: [{ name: "rag.generate_cards" }],
          configuration: {
            provider_profile: "openai_compatible",
            base_url: "http://127.0.0.1:9000",
            api_key_configured: true,
            model: "gpt-4o-mini",
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          deck,
          cards: [importedCard],
          imported_count: 1,
          knowledge_units: [{ unit_id: "ku_regularization", topic: "Regularization" }],
          warnings: [],
          provider_meta: { trace_id: "library-rag-import" },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [folder],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [deck],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [importedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 9,
            deck_id: 2,
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
    const file = new File(["ignored"], "regularization.md", { type: "text/markdown" });
    Object.defineProperty(file, "text", {
      value: vi.fn().mockResolvedValue("Regularization reduces overfitting."),
    });

    render(<LibraryPage />);

    await openCardActionsMenu();
    fireEvent.click(await screen.findByRole("menuitem", { name: /ai import/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /generate and import/i })).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText(/files/i), {
      target: { files: [file] },
    });
    fireEvent.submit(screen.getByRole("button", { name: /generate and import/i }).closest("form")!);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/ai/rag/import-cards"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const importCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/ai/rag/import-cards"));
    expect(importCall).toBeTruthy();
    const importBody = JSON.parse(String(importCall?.[1]?.body));
    expect(importBody.deck_id).toBe(2);
    expect(importBody).not.toHaveProperty("deck_name");
    fireEvent.keyDown(screen.getByRole("dialog", { name: /ai import/i }), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /ai import/i })).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: /edit what does regularization reduce/i })).toBeInTheDocument();
  });
});
