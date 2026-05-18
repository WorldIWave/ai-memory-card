import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ImportForm } from "./import-form";

describe("ImportForm", () => {
  it("submits the selected format, deck name, and payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        deck: {
          id: 1,
          name: "ML",
          description: "",
          default_scheduler_type: "sm2_basic",
          visibility: "normal",
          created_at: "2026-04-03T00:00:00Z",
        },
        cards: [],
        imported_count: 1,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ImportForm onImported={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/format/i), {
      target: { value: "json" },
    });
    fireEvent.change(screen.getByLabelText(/deck name/i), {
      target: { value: "ML Deck" },
    });
    fireEvent.change(screen.getByLabelText(/payload/i), {
      target: { value: '{"deck":{"name":"ML"},"cards":[]}' },
    });
    fireEvent.submit(screen.getByRole("button", { name: /import cards/i }).closest("form")!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/imports/cards"),
      expect.objectContaining({
        method: "POST",
      }),
    );
    vi.unstubAllGlobals();
  });
});
