import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProviderForm } from "./provider-form";

describe("ProviderForm", () => {
  beforeEach(async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "zh",
      setItem: vi.fn(),
    });
    await import("../../i18n");
  });

  afterEach(async () => {
    const i18n = (await import("../../i18n")).default;
    await i18n.changeLanguage("zh");
    vi.unstubAllGlobals();
  });

  it("renders the enable toggle and local plugin provider fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/settings")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                app_name: "AI Memory Card Backend",
                ai_provider: "remote_http",
                ai_provider_base_url: "http://127.0.0.1:8091",
              }),
            ),
          );
        }
        if (url.endsWith("/api/ai/plugins/rag-core")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                plugin_id: "rag-core",
                plugin_name: "RAG Card Generation",
                plugin_version: "0.1.0",
                protocol_version: "1",
                enabled: false,
                state: "installed_disabled",
                health: { status: "unavailable" },
                capabilities: [{ name: "rag.generate_cards" }],
                configuration: {
                  provider_profile: "openai_compatible",
                  base_url: null,
                  api_key_configured: false,
                  model: null,
                },
              }),
            ),
          );
        }
        return Promise.reject(new Error(`Unexpected fetch: ${url}`));
      }),
    );

    render(<ProviderForm />);

    expect(await screen.findByText(/rag-core/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "启用 AI 插件" })).toBeInTheDocument();
    expect(screen.getByLabelText("AI 服务地址")).toBeInTheDocument();
    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
    expect(screen.getByLabelText("模型名")).toBeInTheDocument();
    expect(screen.getByText(/openai_compatible/i).closest("p")).toHaveTextContent("已安装，未启用");
  });

  it("shows plugin capability readiness for card generation, understanding evaluation, and scheduling", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    const i18n = (await import("../../i18n")).default;
    await i18n.changeLanguage("en");
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/settings")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                app_name: "AI Memory Card Backend",
                ai_provider: "plugin",
                ai_provider_base_url: null,
              }),
            ),
          );
        }
        if (url.endsWith("/api/ai/plugins/rag-core")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                plugin_id: "rag-core",
                plugin_name: "AI Capability Plugin",
                plugin_version: "0.1.0",
                protocol_version: "1",
                enabled: true,
                state: "ready",
                health: { status: "ok" },
                capabilities: [
                  {
                    name: "rag.generate_cards",
                    modes: [{ name: "api", available: true }],
                  },
                  {
                    name: "evaluation.score_explanation",
                    modes: [{ name: "api", available: true }],
                  },
                  {
                    name: "scheduler.plan_review",
                    modes: [{ name: "local", available: true }],
                  },
                ],
                configuration: {
                  provider_profile: "openai_compatible",
                  base_url: "http://127.0.0.1:9000",
                  api_key_configured: true,
                  model: "gpt-4o-mini",
                },
              }),
            ),
          );
        }
        return Promise.reject(new Error(`Unexpected fetch: ${url}`));
      }),
    );

    render(<ProviderForm />);

    expect(await screen.findByText("Card generation")).toBeInTheDocument();
    expect(screen.getByText("Understanding evaluation")).toBeInTheDocument();
    expect(screen.getByText("Personalized scheduling")).toBeInTheDocument();
    expect(screen.getAllByText("Available")).toHaveLength(3);
    expect(screen.getByText("AI Capability Plugin")).toBeInTheDocument();
  });

  it("shows a helpful message when the configured provider model is unavailable", async () => {
    vi.stubGlobal("localStorage", {
      getItem: () => "en",
      setItem: vi.fn(),
    });
    const i18n = (await import("../../i18n")).default;
    await i18n.changeLanguage("en");

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_name: "AI Memory Card Backend",
              ai_provider: "plugin",
              ai_provider_base_url: null,
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              plugin_id: "rag-core",
              plugin_name: "AI Capability Plugin",
              plugin_version: "0.1.0",
              protocol_version: "1",
              enabled: true,
              state: "ready",
              health: { status: "ok" },
              capabilities: [{ name: "rag.generate_cards", modes: [{ name: "api", available: true }] }],
              configuration: {
                provider_profile: "openai_compatible",
                base_url: "https://api.example.com/v1",
                api_key_configured: true,
                model: "gpt-5.3-codex-xhigh",
              },
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/config")) {
        return Promise.resolve(new Response(JSON.stringify({ enabled: true })));
      }
      if (url.endsWith("/api/ai/plugins/rag-core/test")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: "provider_model_not_found: No available channel for model gpt-5.3-codex-xhigh",
            }),
            { status: 503 },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProviderForm />);

    const submitButton = await screen.findByRole("button", { name: "Test provider connection" });
    fireEvent.submit(submitButton.closest("form")!);

    expect(await screen.findByText(/configured model is not available/i)).toBeInTheDocument();
    expect(screen.queryByText(/provider_model_not_found/i)).not.toBeInTheDocument();
  });

  it("persists the new plugin config shape before testing plugin readiness", async () => {
    let pluginStatusCall = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_name: "AI Memory Card Backend",
              ai_provider: "remote_http",
              ai_provider_base_url: "http://127.0.0.1:8091",
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        pluginStatusCall += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              plugin_id: "rag-core",
              plugin_name: "RAG Card Generation",
              plugin_version: "0.1.0",
              protocol_version: "1",
              enabled: pluginStatusCall > 1,
              state: pluginStatusCall > 1 ? "ready" : "installed_disabled",
              health: { status: pluginStatusCall > 1 ? "ok" : "unavailable" },
              capabilities: [{ name: "rag.generate_cards" }],
              configuration: {
                provider_profile: "openai_compatible",
                base_url: "http://127.0.0.1:9000",
                api_key_configured: pluginStatusCall > 1,
                model: "gpt-4o-mini",
              },
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/test")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
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
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/config")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              provider_profile: "openai_compatible",
              base_url: "http://127.0.0.1:9000",
              model: "gpt-4o-mini",
            }),
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProviderForm />);

    const baseUrlInput = await screen.findByLabelText("AI 服务地址");
    const apiKeyInput = screen.getByLabelText(/api key/i);
    const modelInput = screen.getByLabelText("模型名");
    const enabledToggle = screen.getByRole("checkbox", { name: "启用 AI 插件" });
    const submitButton = screen.getByRole("button", { name: "测试服务连接" });
    const form = submitButton.closest("form");
    if (
      !(baseUrlInput instanceof HTMLInputElement) ||
      !(apiKeyInput instanceof HTMLInputElement) ||
      !(modelInput instanceof HTMLInputElement) ||
      !(enabledToggle instanceof HTMLInputElement) ||
      form === null
    ) {
      throw new Error("expected provider form controls");
    }

    fireEvent.click(enabledToggle);
    fireEvent.change(baseUrlInput, { target: { value: "http://127.0.0.1:9000" } });
    fireEvent.change(apiKeyInput, { target: { value: "sk-test" } });
    fireEvent.change(modelInput, { target: { value: "gpt-4o-mini" } });
    fireEvent.submit(form);

    expect(await screen.findByText("连接测试通过。")).toBeInTheDocument();
    const updateCall = fetchMock.mock.calls.find(([request]) =>
      String(request).includes("/api/ai/plugins/rag-core/config"),
    );
    expect(updateCall).toBeDefined();
    expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
      enabled: true,
      provider_profile: "openai_compatible",
      base_url: "http://127.0.0.1:9000",
      api_key: "sk-test",
      model: "gpt-4o-mini",
    });
  });

  it("preserves an already-configured api key when the input is left blank", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_name: "AI Memory Card Backend",
              ai_provider: "remote_http",
              ai_provider_base_url: "http://127.0.0.1:8091",
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core") || url.endsWith("/api/ai/plugins/rag-core/config")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
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
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/test")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
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
                base_url: "http://127.0.0.1:9001",
                api_key_configured: true,
                model: "gpt-4.1-mini",
              },
            }),
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProviderForm />);

    const baseUrlInput = await screen.findByLabelText("AI 服务地址");
    const modelInput = screen.getByLabelText("模型名");
    const submitButton = screen.getByRole("button", { name: "测试服务连接" });
    const form = submitButton.closest("form");
    if (!(baseUrlInput instanceof HTMLInputElement) || !(modelInput instanceof HTMLInputElement) || form === null) {
      throw new Error("expected provider form controls");
    }

    fireEvent.change(baseUrlInput, { target: { value: "http://127.0.0.1:9001" } });
    fireEvent.change(modelInput, { target: { value: "gpt-4.1-mini" } });
    fireEvent.submit(form);

    const updateCall = fetchMock.mock.calls.find(([request]) =>
      String(request).includes("/api/ai/plugins/rag-core/config"),
    );
    expect(updateCall).toBeDefined();
    expect(JSON.parse(String(updateCall?.[1]?.body))).toEqual({
      enabled: true,
      provider_profile: "openai_compatible",
      base_url: "http://127.0.0.1:9001",
      model: "gpt-4.1-mini",
    });
  });

  it("does not show a success message when connectivity passes but refreshed state is not ready", async () => {
    let pluginStatusCall = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              app_name: "AI Memory Card Backend",
              ai_provider: "remote_http",
              ai_provider_base_url: "http://127.0.0.1:8091",
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core")) {
        pluginStatusCall += 1;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              plugin_id: "rag-core",
              plugin_name: "RAG Card Generation",
              plugin_version: "0.1.0",
              protocol_version: "1",
              enabled: true,
              state: pluginStatusCall === 1 ? "ready" : "enabled_not_configured",
              health: { status: pluginStatusCall === 1 ? "ok" : "unavailable" },
              capabilities: [{ name: "rag.generate_cards" }],
              configuration: {
                provider_profile: "openai_compatible",
                base_url: "http://127.0.0.1:9000",
                api_key_configured: true,
                model: "gpt-4o-mini",
              },
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/test")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
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
                base_url: "http://127.0.0.1:9000",
                api_key_configured: true,
                model: "gpt-4o-mini",
              },
            }),
          ),
        );
      }
      if (url.endsWith("/api/ai/plugins/rag-core/config")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: true,
              provider_profile: "openai_compatible",
              base_url: "http://127.0.0.1:9000",
              model: "gpt-4o-mini",
            }),
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ProviderForm />);

    const submitButton = await screen.findByRole("button", { name: "测试服务连接" });
    fireEvent.submit(submitButton.closest("form")!);

    expect(await screen.findByText(/AI 插件尚未就绪。/i)).toBeInTheDocument();
    expect(screen.getByText(/openai_compatible/i).closest("p")).toHaveTextContent("已启用，待配置");
    expect(screen.queryByText("连接测试通过。")).not.toBeInTheDocument();
  });
});
