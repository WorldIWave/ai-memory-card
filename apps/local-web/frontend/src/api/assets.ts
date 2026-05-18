import { apiRequest } from "./client";
import type { CardAssetDraftResponse, CardAssetUploadResponse } from "./types";

interface UploadCardImageOptions {
  file: File;
  cardId?: number;
  draftId?: string;
}

export async function createCardAssetDraft(): Promise<CardAssetDraftResponse> {
  return apiRequest<CardAssetDraftResponse>("/api/assets/cards/drafts", {
    method: "POST",
  });
}

export async function uploadCardImage({
  file,
  cardId,
  draftId,
}: UploadCardImageOptions): Promise<CardAssetUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  if (cardId !== undefined) {
    form.append("card_id", String(cardId));
  }
  if (draftId) {
    form.append("draft_id", draftId);
  }

  return apiRequest<CardAssetUploadResponse>("/api/assets/cards/upload", {
    method: "POST",
    body: form,
  });
}
