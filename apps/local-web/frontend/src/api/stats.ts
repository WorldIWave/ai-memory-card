/**
 * Input: range_days ???????  |  Output: Promise<StatsSummaryRead/StatsAnalyticsRead>
 * Output: ???????? summary ? analytics ??
 * Role: ?? Data ????????????? API ?
 * Use: ??????????????????????? typed response
 */
import { apiRequest } from "./client";
import type { StatsAnalyticsRead, StatsAnalyticsRangeDays } from "./types";

export function getStatsAnalytics(
  rangeDays: StatsAnalyticsRangeDays = 7,
  options?: { signal?: AbortSignal },
) {
  const params = new URLSearchParams({ range_days: String(rangeDays) });
  return apiRequest<StatsAnalyticsRead>(`/api/stats/analytics?${params.toString()}`, {
    signal: options?.signal,
  });
}
