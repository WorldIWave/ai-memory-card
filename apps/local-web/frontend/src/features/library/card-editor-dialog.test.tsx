import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CardEditorDialog } from "./card-editor-dialog";

describe("CardEditorDialog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads card data, saves edits, and calls onSaved", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Updated question",
          back: "Updated answer",
          render_format: "markdown",
          tags: ["edited"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
          updated_at: "2026-04-20T00:00:00Z",
          content_version: 2,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardEditorDialog
        card={{
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
        }}
        decks={[
          {
            id: 1,
            name: "Default",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-20T00:00:00Z",
          },
        ]}
        open
        onOpenChange={() => {}}
        onSaved={onSaved}
      />,
    );

    expect(screen.getByText(/edit the card fields below/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9/activity"),
        expect.anything(),
      ),
    );
    fireEvent.change(screen.getByLabelText(/front/i), { target: { value: "Updated question" } });
    fireEvent.change(screen.getByLabelText(/back/i), { target: { value: "Updated answer" } });
    fireEvent.change(screen.getByLabelText(/tags/i), { target: { value: "edited" } });
    fireEvent.click(screen.getByRole("button", { name: /save card/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9"),
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ front: "Updated question" })),
    );
  });

  it("disables saving and shows a deck-required message when no decks are available", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardEditorDialog
        card={{
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
        }}
        decks={[]}
        open
        onOpenChange={() => {}}
        onSaved={onSaved}
      />,
    );

    expect(screen.getByText(/add or select a deck before saving this card/i)).toBeInTheDocument();

    const saveButton = screen.getByRole("button", { name: /save card/i });
    expect(saveButton).toBeDisabled();

    fireEvent.click(saveButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/cards/9/activity"),
      expect.anything(),
    );
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("loads activity when the editor opens for a card", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardEditorDialog
        card={{
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
        }}
        decks={[
          {
            id: 1,
            name: "Default",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-20T00:00:00Z",
          },
        ]}
        open
        onOpenChange={() => {}}
        onSaved={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9/activity"),
        expect.anything(),
      ),
    );
  });

  it("archives the card through the trash endpoint when requested", async () => {
    const onArchived = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "archived",
          created_at: "2026-04-20T00:00:00Z",
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardEditorDialog
        card={{
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
        }}
        decks={[
          {
            id: 1,
            name: "Default",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-20T00:00:00Z",
          },
        ]}
        open
        onOpenChange={() => {}}
        onSaved={vi.fn()}
        onArchived={onArchived}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /move to trash/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9/archive"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(onArchived).toHaveBeenCalledWith(expect.objectContaining({ id: 9, status: "archived" }));
  });

  it("uploads pasted images to the current card namespace and saves markdown", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          asset_id: "asset-1",
          filename: "image.png",
          content_type: "image/png",
          size_bytes: 3,
          url: "/api/assets/cards/9/image.png",
          markdown: "![image](/api/assets/cards/9/image.png)",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question\n\n![image](/api/assets/cards/9/image.png)",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
          updated_at: "2026-04-20T00:00:00Z",
          content_version: 2,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CardEditorDialog
        card={{
          id: 9,
          deck_id: 1,
          card_type: "recall",
          front: "Old question",
          back: "Old answer",
          render_format: "markdown",
          tags: ["old"],
          status: "active",
          created_at: "2026-04-20T00:00:00Z",
        }}
        decks={[
          {
            id: 1,
            name: "Default",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-20T00:00:00Z",
          },
        ]}
        open
        onOpenChange={() => {}}
        onSaved={onSaved}
      />,
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9/activity"),
        expect.anything(),
      ),
    );

    const file = new File(["png"], "image.png", { type: "image/png" });
    fireEvent.paste(screen.getByLabelText(/front/i), {
      clipboardData: {
        items: [
          {
            kind: "file",
            type: "image/png",
            getAsFile: () => file,
          },
        ],
      },
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/assets/cards/upload"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const uploadCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/assets/cards/upload"))!;
    const [, uploadRequest] = uploadCall as [string, RequestInit];
    expect((uploadRequest.body as FormData).get("card_id")).toBe("9");

    fireEvent.click(screen.getByRole("button", { name: /save card/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9"),
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const saveCall = fetchMock.mock.calls.find(
      ([url, request]) => String(url).includes("/api/cards/9") && (request as RequestInit).method === "PUT",
    )!;
    const [, saveRequest] = saveCall as [string, RequestInit];
    expect(String(saveRequest.body)).toContain("![image](/api/assets/cards/9/image.png)");
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }));
  });
});
