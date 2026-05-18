/**
 * Input: session scope?deck_id?????? undo ??  |  Output: Promise<ReviewSessionRead/...>
 * Output: ?? review session v3 ????????? API
 * Role: ?? review ????? /api/review/session ?????????
 * Use: ?????????????????????? legacy submit URL
 */
import { apiRequest } from "./client";
import type {
  ReviewSessionRead,
  ReviewSessionScope,
  ReviewSessionSubmitInput,
  ReviewSessionSubmitResponse,
  ReviewSessionUndoResponse,
} from "./types";

export function getReviewSession(scope: ReviewSessionScope, deckId?: number) {
  const params = new URLSearchParams({ scope });
  if (deckId !== undefined) {
    params.set("deck_id", String(deckId));
  }

  return apiRequest<ReviewSessionRead>(`/api/review/session?${params.toString()}`);
}

export function submitReviewSession(sessionId: string, payload: ReviewSessionSubmitInput) {
  const encodedSessionId = encodeURIComponent(sessionId);
  return apiRequest<ReviewSessionSubmitResponse>(`/api/review/session/${encodedSessionId}/submit`, {
    method: "POST",
    body: payload,
  });
}

export function undoReviewSession(sessionId: string) {
  const encodedSessionId = encodeURIComponent(sessionId);
  return apiRequest<ReviewSessionUndoResponse>(`/api/review/session/${encodedSessionId}/undo`, {
    method: "POST",
  });
}
