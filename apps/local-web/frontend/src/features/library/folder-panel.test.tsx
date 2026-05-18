// Input: mocked folder rows and HTTP delete responses | Output: folder panel deletion confirmation behavior
// Role: Protects Library folder deletion from accidental context-menu actions
// Usage: npm run test -- src/features/library/folder-panel.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FolderRead } from "../../api/types";
import { FolderPanel } from "./folder-panel";

const folders: FolderRead[] = [
  { id: 1, name: "Default" },
  { id: 2, name: "Work" },
];

describe("FolderPanel", () => {
  beforeEach(async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    await import("../../i18n");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("asks for confirmation before deleting a folder from the context menu", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => ({}),
    });
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FolderPanel
        folders={folders}
        selectedId={2}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: /^work$/i }));
    fireEvent.click(await screen.findByText(/delete folder/i));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(await screen.findByRole("dialog", { name: /delete folder\?/i })).toBeInTheDocument();
    expect(screen.getByText(/deleting a folder also deletes its decks and cards/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/folders/2"),
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("keeps the delete confirmation open and shows an error when deletion fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Folder delete failed" }),
    });
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FolderPanel
        folders={folders}
        selectedId={2}
        onSelect={vi.fn()}
        onRename={vi.fn()}
        onChanged={onChanged}
      />,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: /^work$/i }));
    fireEvent.click(await screen.findByText(/delete folder/i));
    fireEvent.click(await screen.findByRole("button", { name: /^confirm$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Folder delete failed");
    expect(screen.getByRole("dialog", { name: /delete folder\?/i })).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
