import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewHistoryPage } from "./review-history-page";

describe("ReviewHistoryPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders recent scheduled reviews and opens card editing from a history row", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 14,
            card_id: 9,
            deck_id: 1,
            card_front: "What is overfitting?",
            deck_name: "Algorithms",
            grade: "good",
            interval_days: 4,
            reviewed_at: "2026-04-21T08:00:00Z",
            session_id: "2026-04-21:deck:1",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 9,
            deck_id: 1,
            card_type: "recall",
            front: "What is overfitting?",
            back: "Memorizing noise",
            render_format: "markdown",
            tags: ["ml"],
            status: "active",
            created_at: "2026-04-20T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [
          {
            id: 1,
            name: "Algorithms",
            description: "",
            default_scheduler_type: "sm2_basic",
            visibility: "normal",
            folder_id: 1,
            created_at: "2026-04-20T00:00:00Z",
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewHistoryPage />);

    expect(await screen.findByText("What is overfitting?")).toBeInTheDocument();
    expect(screen.getByText(/Algorithms/i)).toBeInTheDocument();
    expect(screen.getByText(/good/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /edit card/i }));

    expect(await screen.findByText(/edit the card fields below/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/cards/9/activity"),
        expect.anything(),
      ),
    );
  });

  it("shows an empty state when there is no recent review history", async () => {
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
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReviewHistoryPage />);

    expect(await screen.findByText(/no recent reviews yet/i)).toBeInTheDocument();
  });
});
