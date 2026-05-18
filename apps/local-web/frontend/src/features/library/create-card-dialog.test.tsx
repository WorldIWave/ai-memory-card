import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateCardDialog } from "./create-card-dialog";

describe("CreateCardDialog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the unfinished cloze card type out of the user-facing card type tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 1,
          deck_id: 1,
          card_type: "recall",
          front: "Question",
          back: "Answer",
          render_format: "markdown",
          tags: [],
          status: "active",
          created_at: "2026-04-24T00:00:00Z",
        }),
      }),
    );

    render(<CreateCardDialog deckId={1} onCreated={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /create card/i }));

    expect(await screen.findByRole("button", { name: /q&a/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mcq/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cloze/i })).not.toBeInTheDocument();

  });

  it("uploads pasted images to a draft namespace and saves markdown", async () => {
    const onCreated = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ draft_id: "draft_123" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          asset_id: "asset-1",
          filename: "image.png",
          content_type: "image/png",
          size_bytes: 3,
          url: "/api/assets/cards/drafts/draft_123/image.png",
          markdown: "![image](/api/assets/cards/drafts/draft_123/image.png)",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({
          id: 1,
          deck_id: 1,
          card_type: "recall",
          front: "Question\n\n![image](/api/assets/cards/drafts/draft_123/image.png)",
          back: "Answer",
          render_format: "markdown",
          tags: [],
          status: "active",
          created_at: "2026-04-24T00:00:00Z",
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<CreateCardDialog deckId={1} onCreated={onCreated} />);

    fireEvent.click(screen.getByRole("button", { name: /create card/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/assets/cards/drafts"),
        expect.objectContaining({ method: "POST" }),
      ),
    );

    fireEvent.change(screen.getByLabelText(/front/i), { target: { value: "Question" } });
    fireEvent.change(screen.getByLabelText(/back/i), { target: { value: "Answer" } });

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

    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards"),
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const createCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/api/cards"))!;
    const [, request] = createCall as [string, RequestInit];
    expect(String(request.body)).toContain("![image](/api/assets/cards/drafts/draft_123/image.png)");
    expect(onCreated).toHaveBeenCalled();
  });
});
