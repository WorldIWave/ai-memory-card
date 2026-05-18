import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackupPanel } from "./backup-panel";

const baselineBackup = {
  filename: "baseline.sqlite3",
  path: "C:/data/backups/baseline.sqlite3",
  size_bytes: 2048,
  modified_at: "2026-04-05T10:00:00Z",
};

const freshBackup = {
  filename: "fresh.sqlite3",
  path: "C:/data/backups/fresh.sqlite3",
  size_bytes: 4096,
  modified_at: "2026-04-05T10:05:00Z",
};

describe("BackupPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not restore when the confirm dialog is cancelled", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [baselineBackup],
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<BackupPanel />);

    expect(await screen.findByLabelText(/available backups/i)).toHaveValue("baseline.sqlite3");

    fireEvent.click(screen.getByRole("button", { name: /restore selected backup/i }));
    expect(screen.getByRole("dialog", { name: /restore backup/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a backup and restores the selected snapshot after confirmation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [baselineBackup],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => freshBackup,
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [freshBackup, baselineBackup],
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          restored_from: "fresh.sqlite3",
          database_path: "C:/data/ai-memory-card.sqlite3",
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    render(<BackupPanel />);

    expect(await screen.findByLabelText(/available backups/i)).toHaveValue("baseline.sqlite3");

    fireEvent.click(screen.getByRole("button", { name: /create backup/i }));

    await waitFor(() =>
      expect(screen.getByText(/created backup fresh\.sqlite3/i)).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText(/available backups/i), {
      target: { value: "fresh.sqlite3" },
    });
    fireEvent.click(screen.getByRole("button", { name: /restore selected backup/i }));
    fireEvent.click(screen.getByRole("button", { name: /confirm/i }));

    await waitFor(() =>
      expect(screen.getByText(/restored from fresh\.sqlite3/i)).toBeInTheDocument(),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/system/backups"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/system/backup"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/api/system/backups"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      expect.stringContaining("/api/system/restore"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ filename: "fresh.sqlite3" }),
      }),
    );
  });
});
