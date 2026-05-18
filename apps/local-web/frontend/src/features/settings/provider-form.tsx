/**
 * Input: AI provider settings state and local plugin status | Output: editable provider config form
 * Output: lets the user enable the plugin and configure local provider access
 * Role: manages the settings UI for the rag-core plugin configuration
 * Use: settings page provider section and /settings/test-ai-provider connectivity checks
 */
import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getRagPluginStatus, testRagPlugin, updateRagPluginConfig } from "../../api/ai-plugin";
import { apiRequest } from "../../api/client";
import type { PluginConfigUpdateInput, PluginStatusRead, SettingsRead } from "../../api/types";
import { Badge, Button, FieldShell, Skeleton, StatusMessage, TextField } from "../../components/ui";

function capabilityLabelKey(name: string): string {
  if (name === "rag.generate_cards") {
    return "plugin_capability_rag_generate_cards";
  }
  if (name === "evaluation.score_explanation") {
    return "plugin_capability_evaluation_score_explanation";
  }
  if (name === "scheduler.plan_review") {
    return "plugin_capability_scheduler_plan_review";
  }
  return "plugin_capability_unknown";
}

function capabilityIsAvailable(capability: Record<string, unknown>): boolean {
  const modes = capability.modes;
  if (Array.isArray(modes)) {
    return modes.some((mode) => {
      if (typeof mode === "string") {
        return true;
      }
      return Boolean(mode && typeof mode === "object" && "available" in mode && mode.available);
    });
  }
  return false;
}

function providerErrorMessage(error: unknown, t: (key: string) => string): string {
  const rawMessage = error instanceof Error ? error.message : "";
  const stableCode = rawMessage.split(":", 1)[0].trim();
  const knownCodes = new Set([
    "provider_model_not_found",
    "provider_auth_failed",
    "provider_unreachable",
    "provider_request_timeout",
    "provider_request_failed",
  ]);
  if (knownCodes.has(stableCode)) {
    return t(`provider_test_error_${stableCode}`);
  }
  return rawMessage || t("provider_test_error");
}

export function ProviderForm() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<SettingsRead | null>(null);
  const [pluginStatus, setPluginStatus] = useState<PluginStatusRead | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);

  const pluginStateLabel = pluginStatus ? t(`plugin_state_${pluginStatus.state}`) : t("plugin_state_unknown");
  const pluginHealthLabel = t(`plugin_health_${String(pluginStatus?.health?.status ?? "unknown")}`);

  useEffect(() => {
    let ignore = false;
    async function loadSettings() {
      try {
        const [data, plugin] = await Promise.all([
          apiRequest<SettingsRead>("/api/settings"),
          getRagPluginStatus(),
        ]);
        if (!ignore) {
          setSettings(data);
          setPluginStatus(plugin);
          setEnabled(plugin.enabled);
          setBaseUrl(String(plugin.configuration.base_url ?? data.ai_provider_base_url ?? ""));
          setApiKey("");
          setModel(String(plugin.configuration.model ?? ""));
        }
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("provider_load_error"));
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void loadSettings();
    return () => {
      ignore = true;
    };
  }, [t]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorText("");
    setStatusText("");
    setIsTesting(true);
    try {
      const body: PluginConfigUpdateInput = {
        enabled,
        provider_profile: "openai_compatible",
        base_url: baseUrl.trim() || null,
        model: model.trim() || null,
      };

      const nextApiKey = apiKey.trim();
      if (nextApiKey) {
        body.api_key = nextApiKey;
      } else if (!pluginStatus?.configuration.api_key_configured) {
        body.api_key = null;
      }

      await updateRagPluginConfig(body);
      const plugin = await testRagPlugin();
      setPluginStatus(plugin);
      if (plugin.state === "ready") {
        setStatusText(t("provider_test_ok"));
      } else {
        setErrorText(t("plugin_not_ready"));
      }
    } catch (error) {
      setErrorText(providerErrorMessage(error, t));
    } finally {
      setIsTesting(false);
    }
  }

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>{t("settings_provider_section")}</h3>
          <p>{t("settings_provider_hint")}</p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {pluginStatus?.plugin_name ? <Badge tone="primary">{pluginStatus.plugin_name}</Badge> : null}
          <Badge tone="primary">{pluginStatus?.plugin_id ?? "rag-core"}</Badge>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-3">
          <Skeleton className="h-4 w-44" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <form className="grid gap-4" onSubmit={onSubmit}>
          <p className="text-sm text-[var(--text-muted)]">
            {t("provider_current", { provider: settings?.ai_provider ?? "unknown" })}
          </p>
          <p className="text-sm text-[var(--text-muted)]">
            {String(pluginStatus?.configuration.provider_profile ?? "openai_compatible")} ·{" "}
            {pluginStateLabel} · {pluginHealthLabel}
          </p>
          {pluginStatus?.capabilities?.length ? (
            <div className="grid gap-2 rounded-[var(--radius-sm)] border border-[var(--border-light)] bg-white p-3">
              <span className="text-xs font-semibold uppercase text-[var(--text-muted)]">
                {t("plugin_capabilities_label")}
              </span>
              <div className="flex flex-wrap gap-2">
                {pluginStatus.capabilities.map((capability) => {
                  const name = String(capability.name ?? "");
                  const available = capabilityIsAvailable(capability);
                  return (
                    <span
                      key={name}
                      className="inline-flex items-center gap-2 rounded-full bg-[var(--primary-soft)] px-3 py-1 text-sm text-[var(--text-main)]"
                    >
                      <span>{t(capabilityLabelKey(name), { defaultValue: name })}</span>
                      <Badge tone={available ? "primary" : "neutral"}>
                        {available ? t("plugin_capability_available") : t("plugin_capability_unavailable")}
                      </Badge>
                    </span>
                  );
                })}
              </div>
            </div>
          ) : null}
          <FieldShell label={t("provider_enable_label")}>
            <input
              aria-label={t("provider_enable_label")}
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
          </FieldShell>
          <FieldShell label={t("provider_base_url")}>
            <TextField
              aria-label={t("provider_base_url")}
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={t("provider_base_url_placeholder")}
            />
          </FieldShell>
          <FieldShell label={t("provider_api_key_label")}>
            <TextField
              aria-label={t("provider_api_key_label")}
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                pluginStatus?.configuration.api_key_configured ? t("provider_api_key_configured_placeholder") : ""
              }
            />
          </FieldShell>
          <FieldShell label={t("provider_model_label")}>
            <TextField
              aria-label={t("provider_model_label")}
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder={t("provider_model_placeholder")}
            />
          </FieldShell>
          <Button type="submit" disabled={isTesting}>
            {isTesting ? t("saving") : t("provider_test_button")}
          </Button>
        </form>
      )}

      {statusText ? <StatusMessage tone="success">{statusText}</StatusMessage> : null}
      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}
    </section>
  );
}
