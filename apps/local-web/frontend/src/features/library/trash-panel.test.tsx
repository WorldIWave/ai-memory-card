import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CardRead } from "../../api/types";
import { TrashPanel } from "./trash-panel";

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });

  return { promise, resolve };
}

const archivedCard: CardRead = {
  id: 7,
  deck_id: 3,
  card_type: "recall",
  front: "What is soft delete?",
  back: "A logical delete that marks rows as archived.",
  render_format: "markdown",
  tags: [],
  status: "archived",
  created_at: "2026-04-05T00:00:00Z",
};

const restoredCard: CardRead = {
  ...archivedCard,
  status: "active",
};

describe("TrashPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("restores a trashed card and refreshes the trash list", async () => {
    const onRestored = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => restoredCard,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<TrashPanel refreshToken={0} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /restore what is soft delete\?/i }));

    await waitFor(() =>
      expect(onRestored).toHaveBeenCalledWith(expect.objectContaining({ id: 7, status: "active" })),
    );
    await waitFor(() => expect(screen.getByText(/trash is empty/i)).toBeInTheDocument());

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/trash"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/cards/7/restore"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/api/trash"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("reconciles hidden cards when refreshed trash data includes the card again", async () => {
    const onRestored = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => restoredCard,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      });

    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<TrashPanel refreshToken={0} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /restore what is soft delete\?/i }));

    await waitFor(() =>
      expect(onRestored).toHaveBeenCalledWith(expect.objectContaining({ id: 7, status: "active" })),
    );
    await waitFor(() => expect(screen.getByText(/trash is empty/i)).toBeInTheDocument());

    rerender(<TrashPanel refreshToken={1} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();
  });

  it("prevents a second restore click before the trash list refreshes", async () => {
    const onRestored = vi.fn();
    const restoreResponse = createDeferred<CardRead>();
    const reloadResponse = createDeferred<CardRead[]>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => restoreResponse.promise,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => reloadResponse.promise,
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<TrashPanel refreshToken={0} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /restore what is soft delete\?/i }));

    await act(async () => {
      restoreResponse.resolve(restoredCard);
    });

    await waitFor(() => expect(onRestored).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("button", { name: /restore what is soft delete\?/i })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);

    await act(async () => {
      reloadResponse.resolve([]);
    });

    await waitFor(() => expect(screen.getByText(/trash is empty/i)).toBeInTheDocument());
  });

  it("permanently deletes one trashed card after confirmation", async () => {
    const onRestored = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        json: async () => undefined,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<TrashPanel refreshToken={0} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /permanently delete what is soft delete\?/i }));

    expect(await screen.findByRole("dialog", { name: /permanently delete card\?/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(screen.getByText(/trash is empty/i)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/trash/7"),
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("clears all trashed cards after confirmation", async () => {
    const onRestored = vi.fn();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [archivedCard],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ deleted_count: 1 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<TrashPanel refreshToken={0} onRestored={onRestored} />);

    expect(await screen.findByText(/what is soft delete\?/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /clear trash/i }));

    expect(await screen.findByRole("dialog", { name: /empty trash\?/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => expect(screen.getByText(/trash is empty/i)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/trash"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
