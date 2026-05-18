import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StatsAnalyticsRangeDays, StatsAnalyticsRead } from "../api/types";
import { DataPage } from "./data-page";

function buildAnalyticsResponse(rangeDays: StatsAnalyticsRangeDays): StatsAnalyticsRead {
  if (rangeDays === 30) {
    return {
      summary: {
        total_cards: 42,
        today_reviewed: 11,
        daily_new_avg: 1.9,
        daily_review_avg: 8.4,
      },
      trend: {
        range_days: 30,
        points: [
          { date: "2026-03-23", review_count: 2 },
          { date: "2026-04-01", review_count: 5 },
          { date: "2026-04-10", review_count: 7 },
          { date: "2026-04-21", review_count: 11 },
        ],
      },
      grade_distribution: {
        total_reviews: 20,
        items: [
          { grade: "again", count: 2, ratio: 0.1 },
          { grade: "hard", count: 4, ratio: 0.2 },
          { grade: "good", count: 8, ratio: 0.4 },
          { grade: "easy", count: 6, ratio: 0.3 },
        ],
      },
      deck_activity: {
        range_days: 30,
        items: [
          { deck_id: 8, deck_name: "History", review_count: 12, unique_cards: 10 },
          { deck_id: 3, deck_name: "Biology", review_count: 8, unique_cards: 6 },
        ],
      },
    };
  }

  return {
    summary: {
      total_cards: 42,
      today_reviewed: 7,
      daily_new_avg: 1.4,
      daily_review_avg: 5.7,
    },
    trend: {
      range_days: 7,
      points: [
        { date: "2026-04-15", review_count: 1 },
        { date: "2026-04-16", review_count: 4 },
        { date: "2026-04-17", review_count: 3 },
        { date: "2026-04-18", review_count: 6 },
        { date: "2026-04-19", review_count: 2 },
        { date: "2026-04-20", review_count: 5 },
        { date: "2026-04-21", review_count: 7 },
      ],
    },
    grade_distribution: {
      total_reviews: 10,
      items: [
        { grade: "again", count: 1, ratio: 0.1 },
        { grade: "hard", count: 2, ratio: 0.2 },
        { grade: "good", count: 4, ratio: 0.4 },
        { grade: "easy", count: 3, ratio: 0.3 },
      ],
    },
    deck_activity: {
      range_days: 7,
      items: [
        { deck_id: 3, deck_name: "Biology", review_count: 6, unique_cards: 5 },
        { deck_id: 5, deck_name: "Chemistry", review_count: 4, unique_cards: 3 },
      ],
    },
  };
}

describe("DataPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads 7-day analytics by default and renders analytics sections", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildAnalyticsResponse(7),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <DataPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: /analytics range/i })).toHaveClass("segmented-control");
    expect(screen.getByRole("radiogroup", { name: /analytics range/i })).toHaveStyle("--active-index: 0");
    expect(screen.getByRole("radio", { name: /7/i })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Learning trend")).toBeInTheDocument();
    expect(screen.getByText("Grade distribution")).toBeInTheDocument();
    expect(screen.getByText("Deck activity")).toBeInTheDocument();
    expect(screen.getByText("Biology")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /review history/i })).toHaveAttribute("href", "/history");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/stats/analytics?range_days=7"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("switches to 30-day analytics and updates the range selection", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      const rangeDays = url.includes("range_days=30") ? 30 : 7;

      return {
        ok: true,
        status: 200,
        json: async () => buildAnalyticsResponse(rangeDays as StatsAnalyticsRangeDays),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <DataPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Biology")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /30/i }));

    await screen.findByText("History");

    const sevenDayOption = screen.getByRole("radio", { name: /7/i });
    const thirtyDayOption = screen.getByRole("radio", { name: /30/i });

    expect(sevenDayOption).toHaveAttribute("aria-checked", "false");
    expect(thirtyDayOption).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radiogroup", { name: /analytics range/i })).toHaveStyle("--active-index: 1");
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/stats/analytics?range_days=30"),
        expect.objectContaining({ method: "GET" }),
      );
    });
  });

  it("keeps the current chart visible while loading the next range", async () => {
    let resolveThirtyDay: ((value: {
      ok: true;
      status: 200;
      json: () => Promise<StatsAnalyticsRead>;
    }) => void) | undefined;
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("range_days=30")) {
        return new Promise((resolve) => {
          resolveThirtyDay = resolve;
        });
      }

      return {
        ok: true,
        status: 200,
        json: async () => buildAnalyticsResponse(7),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <DataPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Apr 15")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /30/i }));

    expect(screen.getByText("Apr 15")).toBeInTheDocument();
    expect(screen.queryByLabelText(/loading/i)).not.toBeInTheDocument();

    resolveThirtyDay?.({
      ok: true,
      status: 200,
      json: async () => buildAnalyticsResponse(30),
    });

    expect(await screen.findByText("History")).toBeInTheDocument();
    expect(await screen.findByText("Mar 23")).toBeInTheDocument();
  });
});
