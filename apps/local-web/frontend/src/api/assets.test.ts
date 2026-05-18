import { afterEach, describe, expect, it, vi } from "vitest";

import { createCardAssetDraft, uploadCardImage } from "./assets";

describe("card asset api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates a card asset draft namespace", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ draft_id: "draft_123" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await createCardAssetDraft();

    expect(result.draft_id).toBe("draft_123");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/assets/cards/drafts"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("uploads image files as multipart form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
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
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["png"], "image.png", { type: "image/png" });
    const result = await uploadCardImage({ file, draftId: "draft_123" });

    expect(result.markdown).toContain("image.png");
    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(request.body).toBeInstanceOf(FormData);
    expect((request.body as FormData).get("file")).toBe(file);
    expect((request.body as FormData).get("draft_id")).toBe("draft_123");
    expect(new Headers(request.headers).has("Content-Type")).toBe(false);
  });
});
