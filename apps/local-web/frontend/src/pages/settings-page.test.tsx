import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("../features/settings/provider-form", () => ({
  ProviderForm: () => (
    <section>
      <h3>Provider settings</h3>
      <label>
        <span>AI base URL</span>
        <input aria-label="AI base URL" />
      </label>
    </section>
  ),
}));

vi.mock("../features/system/backup-panel", () => ({
  BackupPanel: () => (
    <section>
      <h3>Backup and restore</h3>
      <p>No backups yet. Create one before restoring a snapshot.</p>
    </section>
  ),
}));

vi.mock("../features/system/diagnostics-panel", () => ({
  DiagnosticsPanel: () => (
    <section>
      <h3>Diagnostics</h3>
      <p>No log files were found.</p>
      <p>C:/data/logs</p>
    </section>
  ),
}));

vi.mock("../features/system/data-directory-panel", () => ({
  DataDirectoryPanel: () => (
    <section>
      <h3>Data directory</h3>
      <p>C:/Users/alice/AppData/Local/AIMemoryCard/stable</p>
    </section>
  ),
}));

let SettingsPage: typeof import("./settings-page").SettingsPage;
let i18nInstance: typeof import("../i18n").default;
let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

const storageState = new Map<string, string>();
const localStorageMock = {
  getItem: vi.fn((key: string) => {
    if (key === "lmca-lang") {
      return "en";
    }
    return storageState.get(key) ?? null;
  }),
  setItem: vi.fn((key: string, value: string) => {
    storageState.set(key, value);
  }),
  removeItem: vi.fn(),
  clear: vi.fn(() => {
    storageState.clear();
  }),
};

function okJson(payload: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: async () => payload,
  });
}

function studySettingsJson() {
  return okJson({
    daily_new_limit: 12,
    daily_review_limit: 44,
    scheduler_mode: "traditional",
    updated_at: "2026-04-21T00:00:00.000Z",
  });
}

function pause(ms: number) {
  return act(async () => {
    await new Promise((resolve) => {
      setTimeout(resolve, ms);
    });
  });
}

beforeAll(async () => {
  consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("localStorage", localStorageMock as unknown as Storage);
  ({ default: i18nInstance } = await import("../i18n"));
  ({ SettingsPage } = await import("./settings-page"));
});

describe("SettingsPage", () => {
  afterEach(async () => {
    vi.clearAllMocks();
    storageState.clear();
    await i18nInstance.changeLanguage("en");
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", localStorageMock as unknown as Storage);
  });

  it("renders the settings center and writes local preferences", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        return studySettingsJson();
      }
      throw new Error(`Unhandled request: ${url}`);
    }));

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();
    const studySection = screen.getByRole("heading", { name: /study/i }).closest(".settings-section-card");
    expect(studySection).not.toBeNull();
    expect(within(studySection as HTMLElement).queryByLabelText(/flip animation/i)).not.toBeInTheDocument();

    expect(screen.getByRole("navigation", { name: /settings/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /general/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /study/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/search settings/i)).toBeInTheDocument();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/accent/i), { target: { value: "orange" } });
    });

    await screen.findByText(/saved\./i);
    expect(document.documentElement.dataset.accent).toBe("orange");
    expect(localStorageMock.setItem).toHaveBeenCalled();
    await pause(1300);
    expect(screen.queryByText(/saved\./i)).not.toBeInTheDocument();
  });

  it("moves language selection into General settings and persists it", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        return studySettingsJson();
      }
      throw new Error(`Unhandled request: ${url}`);
    }));

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/language/i), { target: { value: "zh" } });
    });

    await screen.findByText(/saved/i);
    expect(localStorageMock.setItem).toHaveBeenCalledWith("lmca-lang", "zh");
    await pause(1300);
    expect(screen.queryByText(/saved/i)).not.toBeInTheDocument();
  });

  it("loads study limits from the backend and saves them separately from local preferences", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        if (init?.method === "PUT") {
          return okJson({
            daily_new_limit: 15,
            daily_review_limit: 44,
            scheduler_mode: "traditional",
            updated_at: "2026-04-21T00:00:01.000Z",
          });
        }
        return okJson({
          daily_new_limit: 12,
          daily_review_limit: 44,
          scheduler_mode: "traditional",
          updated_at: "2026-04-21T00:00:00.000Z",
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();
    expect(screen.getByDisplayValue("44")).toBeInTheDocument();

    const newLimitInput = screen.getByLabelText(/daily new limit/i);
    await act(async () => {
      fireEvent.change(newLimitInput, { target: { value: "15" } });
    });

    await screen.findByText(/saved\./i);

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/settings/study"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          daily_new_limit: 15,
          daily_review_limit: 44,
          scheduler_mode: "traditional",
        }),
      }),
    );
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith(
      "lmca.uiPreferences",
      expect.stringContaining('"dailyNewLimit":15'),
    );
    await pause(1300);
    expect(screen.queryByText(/saved\./i)).not.toBeInTheDocument();
  });

  it("loads and saves the study scheduler mode", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        if (init?.method === "PUT") {
          return okJson({
            daily_new_limit: 12,
            daily_review_limit: 44,
            scheduler_mode: "ai_rl",
            updated_at: "2026-04-21T00:00:01.000Z",
          });
        }
        return studySettingsJson();
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    const schedulerModeSelect = await screen.findByLabelText(/scheduler mode/i);
    expect(schedulerModeSelect).toHaveValue("traditional");

    await act(async () => {
      fireEvent.change(schedulerModeSelect, { target: { value: "ai_rl" } });
    });

    await screen.findByText(/saved\./i);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/settings/study"),
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          daily_new_limit: 12,
          daily_review_limit: 44,
          scheduler_mode: "ai_rl",
        }),
      }),
    );
  });

  it("preserves AI RL scheduler mode when saving study limits", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        if (init?.method === "PUT") {
          return okJson({
            daily_new_limit: 16,
            daily_review_limit: 44,
            scheduler_mode: "ai_rl",
            updated_at: "2026-04-21T00:00:01.000Z",
          });
        }
        return okJson({
          daily_new_limit: 12,
          daily_review_limit: 44,
          scheduler_mode: "ai_rl",
          updated_at: "2026-04-21T00:00:00.000Z",
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    const newLimitInput = await screen.findByLabelText(/daily new limit/i);
    expect(newLimitInput).toHaveValue(12);
    expect(screen.getByLabelText(/daily review limit/i)).toHaveValue(44);
    expect(screen.getByLabelText(/scheduler mode/i)).toHaveValue("ai_rl");

    await act(async () => {
      fireEvent.change(newLimitInput, { target: { value: "16" } });
    });

    await screen.findByText(/saved\./i);
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(putCall).toBeDefined();
    const requestBody = JSON.parse(String(putCall?.[1]?.body));
    expect(requestBody).toEqual({
      daily_new_limit: 16,
      daily_review_limit: 44,
      scheduler_mode: "ai_rl",
    });
  });

  it("switches to Data and shows data directory and backup content", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        return studySettingsJson();
      }
      if (url.includes("/api/system/backups")) {
        return okJson([]);
      }
      if (url.includes("/api/system/runtime")) {
        return okJson({
          app_name: "AI Memory Card Backend",
          app_version: "0.1.0",
          backend_version: "0.1.0",
          backend_root: "C:/code/apps/local-web/backend",
          database_path: "C:/data/ai-memory-card.sqlite3",
          backup_dir: "C:/data/backups",
          log_dir: "C:/data/logs",
          backend_port: 8765,
        });
      }
      if (url.includes("/api/system/diagnostics")) {
        return okJson({
          app_name: "AI Memory Card Backend",
          app_version: "0.1.0",
          backend_version: "0.1.0",
          backend_root: "C:/code/apps/local-web/backend",
          database_path: "C:/data/ai-memory-card.sqlite3",
          backup_dir: "C:/data/backups",
          log_dir: "C:/data/logs",
          backend_port: 8765,
          database_exists: true,
          database_size_bytes: 8192,
          backup_count: 0,
          backups: [],
          log_files: [],
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /data/i }));
    });

    const dataDirectoryHeading = screen.getByRole("heading", { name: /data directory/i });
    const backupHeading = screen.getByRole("heading", { name: /backup and restore/i });
    const diagnosticsHeading = screen.getByRole("heading", { name: /diagnostics/i });
    expect(dataDirectoryHeading).toBeInTheDocument();
    expect(await screen.findByText("C:/Users/alice/AppData/Local/AIMemoryCard/stable")).toBeInTheDocument();
    expect(backupHeading).toBeInTheDocument();
    expect(dataDirectoryHeading.compareDocumentPosition(backupHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(backupHeading.compareDocumentPosition(diagnosticsHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(await screen.findByText(/no backups yet/i)).toBeInTheDocument();
    expect(await screen.findByText(/no log files were found/i)).toBeInTheDocument();
    expect(await screen.findByText(/C:\/data\/logs/i)).toBeInTheDocument();
  });

  it("finds the Data section when searching for data directory", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        return studySettingsJson();
      }
      throw new Error(`Unhandled request: ${url}`);
    }));

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/search settings/i), { target: { value: "data directory" } });
    });

    expect(screen.getByRole("button", { name: /data/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /data directory/i })).toBeInTheDocument();
  });

  it("switches to About and shows provider and help links", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/settings/study")) {
        return studySettingsJson();
      }
      if (url.includes("/api/settings")) {
        return okJson({
          ai_provider: "noop",
          ai_provider_base_url: null,
        });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await act(async () => {
      render(<SettingsPage />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /study/i }));
    });

    expect(await screen.findByDisplayValue("12")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /about/i }));
    });

    expect(await screen.findByLabelText(/AI base URL/i)).toBeInTheDocument();
    expect(await screen.findByText(/provider settings/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /documentation/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /submit feedback/i })).toBeInTheDocument();
    const aboutSection = screen.getByRole("heading", { name: /^about$/i }).closest(".settings-section-card");
    expect(aboutSection).not.toBeNull();
    expect(within(aboutSection as HTMLElement).getAllByText(/saved locally on this device/i)).toHaveLength(1);
  });

  afterAll(() => {
    consoleErrorSpy.mockRestore();
  });
});
