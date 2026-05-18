import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chooseDataDirectory,
  getDataDirectoryState,
  scheduleDataDirectoryMigration,
} from "./data-directory";

const runtimePayload = {
  app_name: "AI Memory Card Backend",
  app_version: "0.1.0",
  backend_version: "0.1.0",
  backend_root: "D:/app/backend",
  app_data_dir: "C:/Users/alice/AppData/Local/AIMemoryCard/stable",
  database_path: "C:/Users/alice/AppData/Local/AIMemoryCard/stable/data/ai_memory_card.db",
  backup_dir: "C:/Users/alice/AppData/Local/AIMemoryCard/stable/backups",
  log_dir: "C:/Users/alice/AppData/Local/AIMemoryCard/stable/logs",
  cache_dir: "C:/Users/alice/AppData/Local/AIMemoryCard/stable/cache",
  runtime_mode: "bundled",
  backend_port: 8000,
};

describe("data directory API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to backend runtime info when desktop bridge is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => runtimePayload,
        }),
      ),
    );

    const state = await getDataDirectoryState();

    expect(state.current_app_data_root).toBe(runtimePayload.app_data_dir);
    expect(state.default_app_data_root).toBe(runtimePayload.app_data_dir);
    expect(state.custom_app_data_root).toBeNull();
    expect(state.desktop_bridge_available).toBe(false);
    expect(state.migration_allowed).toBe(false);
    expect(state.pending_target_app_data_root).toBeNull();
  });

  it("uses desktop invoke when available", async () => {
    const invoke = vi.fn().mockResolvedValue({
      runtime_mode: "bundled",
      current_app_data_root: "D:/Cards",
      default_app_data_root: "C:/Default",
      custom_app_data_root: "D:/Cards",
      migration_allowed: false,
      pending_target_app_data_root: null,
      desktop_bridge_available: true,
    });
    vi.stubGlobal("__TAURI__", { tauri: { invoke } });

    const state = await getDataDirectoryState();

    expect(invoke).toHaveBeenCalledWith("lmca_get_data_directory_state");
    expect(state.current_app_data_root).toBe("D:/Cards");
  });

  it("uses top-level desktop invoke when available", async () => {
    const invoke = vi.fn().mockResolvedValue({
      runtime_mode: "bundled",
      current_app_data_root: "E:/Cards",
      default_app_data_root: "C:/Default",
      custom_app_data_root: "E:/Cards",
      migration_allowed: false,
      pending_target_app_data_root: null,
      desktop_bridge_available: true,
    });
    vi.stubGlobal("__TAURI__", { invoke });

    const state = await getDataDirectoryState();

    expect(invoke).toHaveBeenCalledWith("lmca_get_data_directory_state");
    expect(state.current_app_data_root).toBe("E:/Cards");
  });

  it("schedules migration through desktop invoke", async () => {
    const invoke = vi.fn().mockResolvedValue({
      runtime_mode: "bundled",
      current_app_data_root: "C:/Default",
      default_app_data_root: "C:/Default",
      custom_app_data_root: null,
      migration_allowed: true,
      pending_target_app_data_root: "D:/Cards",
      desktop_bridge_available: true,
    });
    vi.stubGlobal("__TAURI__", { tauri: { invoke } });

    await scheduleDataDirectoryMigration("D:/Cards");

    expect(invoke).toHaveBeenCalledWith("lmca_schedule_data_directory_migration", {
      targetAppDataRoot: "D:/Cards",
    });
  });

  it("returns null when desktop picker is cancelled", async () => {
    const invoke = vi.fn().mockResolvedValue(null);
    vi.stubGlobal("__TAURI__", { tauri: { invoke } });

    await expect(chooseDataDirectory()).resolves.toBeNull();
  });
});
