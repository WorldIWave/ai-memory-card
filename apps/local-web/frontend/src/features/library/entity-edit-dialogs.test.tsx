import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DeckRead, FolderRead } from "../../api/types";
import { DeckEditDialog, FolderRenameDialog } from "./entity-edit-dialogs";

const folder: FolderRead = {
  id: 2,
  name: "Study",
};

const deck: DeckRead = {
  id: 3,
  name: "Algorithms",
  description: "Old description",
  default_scheduler_type: "sm2_basic",
  visibility: "normal",
  folder_id: 2,
  created_at: "2026-04-20T00:00:00Z",
};

describe("entity edit dialogs", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("FolderRenameDialog sends PUT to /api/folders/2 and calls onSaved with returned folder", async () => {
    await import("../../i18n");

    const onSaved = vi.fn();
    const onOpenChange = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 2, name: "Notes" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <FolderRenameDialog folder={folder} open onOpenChange={onOpenChange} onSaved={onSaved} />,
    );

    fireEvent.change(screen.getByLabelText(/folder name/i), { target: { value: "Notes" } });
    fireEvent.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/folders/2"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ name: "Notes" }),
        }),
      ),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith({ id: 2, name: "Notes" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("DeckEditDialog sends PUT to /api/decks/3 and calls onSaved with returned deck", async () => {
    await import("../../i18n");

    const onSaved = vi.fn();
    const onOpenChange = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ...deck,
        name: "Algorithms v2",
        description: "Updated description",
        folder_id: 1,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DeckEditDialog
        deck={deck}
        folders={[
          { id: 1, name: "Default" },
          { id: 2, name: "Study" },
        ]}
        open
        onOpenChange={onOpenChange}
        onSaved={onSaved}
      />,
    );

    fireEvent.change(screen.getByLabelText(/deck name/i), { target: { value: "Algorithms v2" } });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: "Updated description" },
    });
    fireEvent.change(screen.getByLabelText(/folder/i), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: /save deck/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/decks/3"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            name: "Algorithms v2",
            description: "Updated description",
            folder_id: 1,
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 3,
          name: "Algorithms v2",
          description: "Updated description",
          folder_id: 1,
        }),
      ),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
