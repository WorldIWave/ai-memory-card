import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiagnosticsPanel } from "./diagnostics-panel";

describe("DiagnosticsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders runtime diagnostics and exports logs", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          app_name: "AI Memory Card Backend",
          app_version: "0.1.0",
          backend_version: "0.1.0",
          backend_root: "C:/bundle/resources/backend",
          app_data_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable",
          database_path: "C:/Users/test/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db",
          backup_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/backups",
          log_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/logs",
          cache_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/cache",
          runtime_mode: "bundled",
          release_channel_url: "https://github.com/ai-memory-card/ai-memory-card/releases",
          backend_port: 8765,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          app_name: "AI Memory Card Backend",
          app_version: "0.1.0",
          backend_version: "0.1.0",
          backend_root: "C:/bundle/resources/backend",
          app_data_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable",
          database_path: "C:/Users/test/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db",
          backup_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/backups",
          log_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/logs",
          cache_dir: "C:/Users/test/AppData/Local/AIMemoryCard/stable/cache",
          runtime_mode: "bundled",
          release_channel_url: "https://github.com/ai-memory-card/ai-memory-card/releases",
          backend_port: 8765,
          database_exists: true,
          database_size_bytes: 8192,
          backup_count: 2,
          backups: [],
          log_files: [
            {
              name: "app.log",
              path: "C:/Users/test/AppData/Local/AIMemoryCard/stable/logs/app.log",
              size_bytes: 128,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          "content-disposition": 'attachment; filename="ai-memory-card-logs.txt"',
          "content-type": "text/plain; charset=utf-8",
        }),
        text: async () => "startup ok",
      });

    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:logs");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<DiagnosticsPanel />);

    expect(await screen.findByText(/AI Memory Card Backend/i)).toBeInTheDocument();
    expect(await screen.findByText(/c:\/users\/test\/appdata\/local\/aimemorycard\/stable\/data\/ai_memory_card\.db/i)).toBeInTheDocument();
    expect(screen.getByText("App data:")).toBeInTheDocument();
    expect(await screen.findByText("C:/Users/test/AppData/Local/AIMemoryCard/stable")).toBeInTheDocument();
    expect(screen.getByText("Cache:")).toBeInTheDocument();
    expect(screen.getByText("C:/Users/test/AppData/Local/AIMemoryCard/stable/cache")).toBeInTheDocument();
    expect(screen.getByText("Runtime mode:")).toBeInTheDocument();
    expect(screen.getByText(/^bundled$/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download latest release/i })).toHaveAttribute(
      "href",
      "https://github.com/ai-memory-card/ai-memory-card/releases",
    );
    expect(screen.getByText(/2 backups available/i)).toBeInTheDocument();
    expect(screen.getByText(/c:\/users\/test\/appdata\/local\/aimemorycard\/stable\/logs\/app\.log/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /export logs/i }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByText(/downloaded log export/i)).toBeInTheDocument());

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining("/api/system/runtime"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/system/diagnostics"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      expect.stringContaining("/api/system/logs/export"),
      expect.objectContaining({ method: "GET" }),
    );
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:logs");
  });
});
