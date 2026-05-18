// Input: Tauri bridge or backend runtime API  |  Output: data-directory state and desktop migration commands
// Role: Keeps Settings UI independent from desktop command names and backend fallback details.
// Note: Browser fallback is read-only; directory picking and migration scheduling require the Tauri bridge.
// Usage: import { getDataDirectoryState } from "./data-directory";
import { apiRequest } from "./client";
import type { DataDirectoryStateRead, SystemRuntimeRead } from "./types";

type TauriGlobal = {
  invoke?: <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
  tauri?: {
    invoke?: <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
  };
};

type GlobalWithTauri = typeof globalThis & {
  __TAURI__?: TauriGlobal;
};

function tauriGlobal(): TauriGlobal | null {
  return (globalThis as GlobalWithTauri).__TAURI__ ?? null;
}

function desktopInvoke() {
  const tauri = tauriGlobal();
  return tauri?.invoke ?? tauri?.tauri?.invoke ?? null;
}

function hasDesktopBridge() {
  return typeof desktopInvoke() === "function";
}

export async function getDataDirectoryState(): Promise<DataDirectoryStateRead> {
  const invoke = desktopInvoke();
  if (hasDesktopBridge() && invoke) {
    return invoke<DataDirectoryStateRead>("lmca_get_data_directory_state");
  }

  const runtime = await apiRequest<SystemRuntimeRead>("/api/system/runtime");
  return {
    runtime_mode: runtime.runtime_mode,
    current_app_data_root: runtime.app_data_dir,
    default_app_data_root: runtime.app_data_dir,
    custom_app_data_root: null,
    migration_allowed: false,
    pending_target_app_data_root: null,
    desktop_bridge_available: false,
  };
}

export async function chooseDataDirectory(): Promise<string | null> {
  const invoke = desktopInvoke();
  if (!hasDesktopBridge() || !invoke) {
    throw new Error("Desktop data directory picker is unavailable.");
  }
  return invoke<string | null>("lmca_choose_data_directory");
}

export async function scheduleDataDirectoryMigration(
  targetAppDataRoot: string,
): Promise<DataDirectoryStateRead> {
  const invoke = desktopInvoke();
  if (!hasDesktopBridge() || !invoke) {
    throw new Error("Desktop data directory migration is unavailable.");
  }
  return invoke<DataDirectoryStateRead>("lmca_schedule_data_directory_migration", {
    targetAppDataRoot,
  });
}
