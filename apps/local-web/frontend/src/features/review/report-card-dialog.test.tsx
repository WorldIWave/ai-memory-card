import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportCardDialog } from "./report-card-dialog";

describe("ReportCardDialog", () => {
  it("records a report through the card report endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "report:1",
        event_type: "report_error",
        created_at: "2026-04-21T09:00:00Z",
        summary: "Content issue",
        payload: { reason: "content", note: "needs example" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onRecorded = vi.fn();
    const onOpenChange = vi.fn();

    render(
      <ReportCardDialog
        cardId={9}
        open
        onOpenChange={onOpenChange}
        onRecorded={onRecorded}
        onFixNow={vi.fn()}
      />,
    );

    expect(screen.getByText(/records a note on the card/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/issue type/i), { target: { value: "content" } });
    fireEvent.change(screen.getByLabelText(/note/i), { target: { value: "  needs example  " } });
    fireEvent.click(screen.getByRole("button", { name: /record issue/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [, request] = fetchMock.mock.calls[0] as [string, { body?: string }];
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/cards/9/report"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(request.body).toContain('"reason":"content"');
    expect(request.body).toContain('"note":"needs example"');
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(onRecorded).toHaveBeenCalledWith({
      id: "report:1",
      event_type: "report_error",
      created_at: "2026-04-21T09:00:00Z",
      summary: "Content issue",
      payload: { reason: "content", note: "needs example" },
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    vi.unstubAllGlobals();
  });

  it("records and then asks to fix the card", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "report:2",
        event_type: "report_error",
        created_at: "2026-04-21T09:05:00Z",
        summary: "Answer issue",
        payload: { reason: "answer", note: "needs a citation" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const onFixNow = vi.fn();
    const onOpenChange = vi.fn();
    const onRecorded = vi.fn();

    render(
      <ReportCardDialog
        cardId={9}
        open
        onOpenChange={onOpenChange}
        onRecorded={onRecorded}
        onFixNow={onFixNow}
      />,
    );

    fireEvent.change(screen.getByLabelText(/issue type/i), { target: { value: "answer" } });
    fireEvent.change(screen.getByLabelText(/note/i), { target: { value: "  needs a citation  " } });
    fireEvent.click(screen.getByRole("button", { name: /record and fix now/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/cards/9/report"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(onRecorded).toHaveBeenCalledTimes(1);
    expect(onRecorded).toHaveBeenCalledWith({
      id: "report:2",
      event_type: "report_error",
      created_at: "2026-04-21T09:05:00Z",
      summary: "Answer issue",
      payload: { reason: "answer", note: "needs a citation" },
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onFixNow).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
