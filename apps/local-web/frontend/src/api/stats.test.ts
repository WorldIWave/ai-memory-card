import { afterEach, describe, expect, it, vi } from "vitest";

import { getStatsAnalytics } from "./stats";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getStatsAnalytics", () => {
  it("forwards an abort signal to the request", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        summary: {
          total_cards: 1,
          today_reviewed: 1,
          daily_new_avg: 1,
          daily_review_avg: 1,
        },
        trend: { range_days: 7, points: [] },
        grade_distribution: { total_reviews: 0, items: [] },
        deck_activity: { range_days: 7, items: [] },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getStatsAnalytics(30, { signal: controller.signal } as any);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/stats/analytics?range_days=30",
      expect.objectContaining({ signal: controller.signal }),
    );
  });
});
