import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/data-directory", () => ({
  chooseDataDirectory: vi.fn(),
  getDataDirectoryState: vi.fn(),
  scheduleDataDirectoryMigration: vi.fn(),
}));

import {
  chooseDataDirectory,
  getDataDirectoryState,
  scheduleDataDirectoryMigration,
} from "../../api/data-directory";
import { DataDirectoryPanel } from "./data-directory-panel";

const desktopState = {
  runtime_mode: "bundled",
  current_app_data_root: "C:/Users/alice/AppData/Local/AIMemoryCard/stable",
  default_app_data_root: "C:/Users/alice/AppData/Local/AIMemoryCard/default",
  custom_app_data_root: null,
  migration_allowed: true,
  pending_target_app_data_root: null,
  desktop_bridge_available: true,
};

describe("DataDirectoryPanel", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows read-only fallback when desktop bridge is unavailable", async () => {
    vi.mocked(getDataDirectoryState).mockResolvedValue({
      ...desktopState,
      desktop_bridge_available: false,
      migration_allowed: false,
    });

    render(<DataDirectoryPanel />);

    expect((await screen.findAllByText(desktopState.current_app_data_root)).length).toBeGreaterThan(0);
    expect(screen.queryByText(desktopState.default_app_data_root)).not.toBeInTheDocument();
    expect(screen.getByText(/available in the desktop app/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /current data directory/i })).not.toBeInTheDocument();
  });

  it("opens the directory picker from the current directory field and schedules migration after confirmation", async () => {
    vi.mocked(getDataDirectoryState).mockResolvedValue(desktopState);
    vi.mocked(chooseDataDirectory).mockResolvedValue("D:/AIMemoryCardData");
    vi.mocked(scheduleDataDirectoryMigration).mockResolvedValue({
      ...desktopState,
      migration_allowed: false,
      pending_target_app_data_root: "D:/AIMemoryCardData",
    });

    render(<DataDirectoryPanel />);

    fireEvent.click(await screen.findByRole("button", { name: /current data directory/i }));
    expect(await screen.findByRole("dialog", { name: /schedule data migration/i })).toBeInTheDocument();
    expect(screen.getByText(/D:\/AIMemoryCardData/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^schedule migration$/i }));

    await waitFor(() => {
      expect(scheduleDataDirectoryMigration).toHaveBeenCalledWith("D:/AIMemoryCardData");
    });
    expect(await screen.findByText(/restart required/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /schedule data migration/i })).not.toBeInTheDocument();
  });

  it("closes the confirmation dialog and shows scheduling errors in the card", async () => {
    vi.mocked(getDataDirectoryState).mockResolvedValue(desktopState);
    vi.mocked(chooseDataDirectory).mockResolvedValue("D:/ExistingData");
    vi.mocked(scheduleDataDirectoryMigration).mockRejectedValue(
      new Error("Target directory already contains an AI Memory Card database"),
    );

    render(<DataDirectoryPanel />);

    fireEvent.click(await screen.findByRole("button", { name: /current data directory/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^schedule migration$/i }));

    expect(await screen.findByText(/already contains an AI Memory Card database/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: /schedule data migration/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/D:\/ExistingData/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(desktopState.current_app_data_root).length).toBeGreaterThan(0);
  });

  it("shows a status message when the picker is cancelled", async () => {
    vi.mocked(getDataDirectoryState).mockResolvedValue(desktopState);
    vi.mocked(chooseDataDirectory).mockResolvedValue(null);

    render(<DataDirectoryPanel />);

    fireEvent.click(await screen.findByRole("button", { name: /current data directory/i }));

    expect(await screen.findByText(/no directory selected/i)).toBeInTheDocument();
    expect(scheduleDataDirectoryMigration).not.toHaveBeenCalled();
  });

  it("does not open the picker while a migration is already pending", async () => {
    vi.mocked(getDataDirectoryState).mockResolvedValue({
      ...desktopState,
      migration_allowed: false,
      pending_target_app_data_root: "D:/AIMemoryCardData",
    });

    render(<DataDirectoryPanel />);

    expect(await screen.findByRole("button", { name: /current data directory/i })).toBeDisabled();
    expect(chooseDataDirectory).not.toHaveBeenCalled();
  });
});
