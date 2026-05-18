// Input: jsdom File objects, fetch mocks, and import callbacks | Output: AI RAG dialog assertions
// Role: Verifies selected text files are read and posted to /api/ai/rag/import-cards
// Note: The test mocks File.text so it remains stable outside a real browser
// Usage: npm run test -- src/features/library/rag-import-dialog.test.tsx
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RAGImportCardsResponse } from "../../api/types";
import { RAGImportDialog } from "./rag-import-dialog";

const importResponse: RAGImportCardsResponse = {
  deck: {
    id: 1,
    name: "Machine Learning",
    description: "",
    default_scheduler_type: "sm2_basic",
    visibility: "normal",
    folder_id: 1,
    created_at: "2026-04-24T00:00:00Z",
  },
  cards: [],
  imported_count: 3,
  knowledge_units: [{ unit_id: "ku_regularization", topic: "Regularization" }],
  warnings: [],
  provider_meta: { trace_id: "rag-test" },
};

describe("RAGImportDialog", () => {
  beforeEach(async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    await import("../../i18n");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reads selected text files and posts them to the local RAG import endpoint", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            plugin_id: "rag-core",
            plugin_name: "RAG Card Generation",
            plugin_version: "0.1.0",
            protocol_version: "1",
            enabled: true,
            state: "ready",
            health: { status: "ok" },
            capabilities: [{ name: "rag.generate_cards" }],
            configuration: {
              provider_profile: "openai_compatible",
              base_url: "http://127.0.0.1:9000",
              api_key_configured: true,
              model: "gpt-4o-mini",
            },
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => importResponse,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onImported = vi.fn();
    const file = new File(["Regularization reduces overfitting."], "regularization.md", { type: "text/markdown" });
    Object.defineProperty(file, "arrayBuffer", {
      value: vi.fn().mockResolvedValue(new TextEncoder().encode("Regularization reduces overfitting.").buffer),
    });

    render(<RAGImportDialog deckId={1} deckName="Machine Learning" onImported={onImported} />);

    fireEvent.click(screen.getByRole("button", { name: /ai import/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /generate and import/i })).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText(/files/i), {
      target: { files: [file] },
    });
    fireEvent.submit(screen.getByRole("button", { name: /generate and import/i }).closest("form")!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, options] = fetchMock.mock.calls[1];
    if (!options) {
      throw new Error("expected import request options");
    }
    const body = JSON.parse(String(options.body));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/ai/rag/import-cards"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(body).toMatchObject({
      deck_id: 1,
      documents: [
        {
          filename: "regularization.md",
          content_type: "text/markdown",
          text: "Regularization reduces overfitting.",
        },
      ],
      generation_prefs: {
        backend: "llm",
        card_types: ["recall", "understanding", "boundary"],
        max_cards_per_unit: 3,
        language: "en",
      },
    });
    expect(body).not.toHaveProperty("deck_name");
    expect(body).not.toHaveProperty("topics");
    expect(screen.queryByLabelText(/deck name/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/backend/i)).not.toBeInTheDocument();
    expect(onImported).toHaveBeenCalledWith(importResponse);
    expect(await screen.findByText(/imported 3 card/i)).toBeInTheDocument();
    expect(screen.getByText(/rag-core/i)).toBeInTheDocument();
    expect(screen.getAllByRole("status")[0]).toHaveTextContent("Ready");
  });

  it("disables import submission when the plugin is not ready", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            plugin_id: "rag-core",
            plugin_name: "RAG Card Generation",
            plugin_version: "0.1.0",
            protocol_version: "1",
            enabled: true,
            state: "enabled_not_configured",
            health: { status: "unavailable" },
            capabilities: [{ name: "rag.generate_cards" }],
            configuration: {
              provider_profile: "openai_compatible",
              base_url: null,
              api_key_configured: false,
              model: null,
            },
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => importResponse,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RAGImportDialog deckId={1} deckName="Machine Learning" onImported={vi.fn()} open onOpenChange={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Enabled, needs configuration");
    expect(screen.getByRole("button", { name: /generate and import/i })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps import submission disabled while plugin status is still loading", async () => {
    let resolveStatus: ((value: unknown) => void) | null = null;
    const statusPromise = new Promise((resolve) => {
      resolveStatus = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return statusPromise;
      }
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => importResponse,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RAGImportDialog deckId={1} deckName="Machine Learning" onImported={vi.fn()} open onOpenChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: /generate and import/i })).toBeDisabled();

    if (resolveStatus === null) {
      throw new Error("expected status resolver");
    }
    (resolveStatus as unknown as (value: unknown) => void)({
      ok: true,
      status: 200,
      json: async () => ({
        plugin_id: "rag-core",
        plugin_name: "RAG Card Generation",
        plugin_version: "0.1.0",
        protocol_version: "1",
        enabled: true,
        state: "ready",
        health: { status: "ok" },
        capabilities: [{ name: "rag.generate_cards" }],
        configuration: {
          provider_profile: "openai_compatible",
          base_url: "http://127.0.0.1:9000",
          api_key_configured: true,
          model: "gpt-4o-mini",
        },
      }),
    });

    await waitFor(() => expect(screen.getAllByRole("status")[0]).toHaveTextContent("Ready"));
    expect(screen.getByRole("button", { name: /generate and import/i })).not.toBeDisabled();
  });

  it("refuses submit while plugin status has not reached ready", async () => {
    let resolveStatus: ((value: unknown) => void) | null = null;
    const statusPromise = new Promise((resolve) => {
      resolveStatus = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return statusPromise;
      }
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => importResponse,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onImported = vi.fn();
    const file = new File(["Regularization reduces overfitting."], "regularization.md", { type: "text/markdown" });

    render(<RAGImportDialog deckId={1} deckName="Machine Learning" onImported={onImported} open onOpenChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/files/i), {
      target: { files: [file] },
    });
    fireEvent.submit(screen.getByRole("button", { name: /generate and import/i }).closest("form")!);

    expect(await screen.findByText(/AI plugin is not ready yet\./i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onImported).not.toHaveBeenCalled();
  });

  it("shows generation progress while a long RAG import is running", async () => {
    let resolveFileBuffer: ((value: ArrayBuffer) => void) | null = null;
    const fileBufferPromise = new Promise<ArrayBuffer>((resolve) => {
      resolveFileBuffer = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            plugin_id: "rag-core",
            plugin_name: "RAG Card Generation",
            plugin_version: "0.1.0",
            protocol_version: "1",
            enabled: true,
            state: "ready",
            health: { status: "ok" },
            capabilities: [{ name: "rag.generate_cards" }],
            configuration: {
              provider_profile: "openai_compatible",
              base_url: "http://127.0.0.1:9000",
              api_key_configured: true,
              model: "gpt-4o-mini",
            },
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 201,
        json: async () => importResponse,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["ignored"], "long-note.md", { type: "text/markdown" });
    Object.defineProperty(file, "arrayBuffer", {
      value: vi.fn(() => fileBufferPromise),
    });

    render(<RAGImportDialog deckId={1} deckName="Machine Learning" onImported={vi.fn()} open onOpenChange={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole("button", { name: /generate and import/i })).not.toBeDisabled());
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText(/files/i), {
      target: { files: [file] },
    });
    fireEvent.submit(screen.getByRole("button", { name: /generate and import/i }).closest("form")!);

    expect(screen.getByRole("progressbar", { name: /generation progress/i })).toBeInTheDocument();
    expect(screen.getByText(/preparing documents/i)).toBeInTheDocument();

    if (resolveFileBuffer === null) {
      throw new Error("expected file resolver");
    }
    await act(async () => {
      (resolveFileBuffer as unknown as (value: ArrayBuffer) => void)(new TextEncoder().encode("Long textbook note.").buffer);
    });
  });
});
