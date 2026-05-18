/**
 * Input: card_id?note?report/evaluation payload ?????  |  Output: Promise<CardActivityItem/...>
 * Output: ????????????????????? API ??
 * Role: ?? review/library ???? activity ??????????
 * Use: ? activity ??? DTO ????????????????? URL
 */
import { apiRequest } from "./client";
import type {
  CardActivityItem,
  CardNoteCreateInput,
  EvaluationRecordInput,
  EvaluationRead,
  EvaluationSubmitInput,
  ReviewHistoryItem,
  ReportCardInput,
} from "./types";

export function listCardActivity(cardId: number) {
  return apiRequest<CardActivityItem[]>(`/api/cards/${cardId}/activity`);
}

export function listReviewHistory(limit = 50) {
  return apiRequest<ReviewHistoryItem[]>(`/api/review/history?limit=${limit}`);
}

export function reportCard(cardId: number, payload: ReportCardInput) {
  return apiRequest<CardActivityItem>(`/api/cards/${cardId}/report`, {
    method: "POST",
    body: payload,
  });
}

export function createCardNote(
  cardId: number,
  payload: CardNoteCreateInput,
  options?: { signal?: AbortSignal },
) {
  return apiRequest<CardActivityItem>(`/api/cards/${cardId}/notes`, {
    method: "POST",
    body: payload,
    signal: options?.signal,
  });
}

export function submitEvaluation(payload: EvaluationSubmitInput, options?: { signal?: AbortSignal }) {
  return apiRequest<EvaluationRead>("/api/evaluations", {
    method: "POST",
    body: payload,
    signal: options?.signal,
  });
}

export function saveEvaluationRecord(payload: EvaluationRecordInput, options?: { signal?: AbortSignal }) {
  return apiRequest<CardActivityItem>("/api/evaluations/records", {
    method: "POST",
    body: payload,
    signal: options?.signal,
  });
}
