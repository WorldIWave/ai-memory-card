/**
 * Input: UI ??????????/???????  |  Output: ?????????????
 * Output: ??????????????????????
 * Role: ????????????????/???????
 * Use: ??????????? UI ???????????????????
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FieldShell, PageHeader, SelectField, StatusMessage, TextField } from "../components/ui";
import { ProviderForm } from "../features/settings/provider-form";
import { SettingsSection } from "../features/settings/settings-section";
import {
  type UiAccent,
  type UiCardFontSize,
  type UiPreferences,
  readUiPreferences,
  writeUiPreferences,
} from "../features/settings/ui-preferences";
import { getStudySettings, updateStudySettings } from "../api/study-settings";
import type { SchedulerMode, StudySettingsRead } from "../api/types";
import { BackupPanel } from "../features/system/backup-panel";
import { DataDirectoryPanel } from "../features/system/data-directory-panel";
import { DiagnosticsPanel } from "../features/system/diagnostics-panel";
import { cn } from "../lib/utils";

type SectionId = "general" | "study" | "shortcuts" | "notifications" | "data" | "about";

interface SectionDefinition {
  id: SectionId;
  title: string;
  description: string;
  keywords: string[];
}

function SettingsRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="settings-control-row">
      <FieldShell label={label}>{children}</FieldShell>
    </div>
  );
}

function optionLabel(language: string, labels: { en: string; zh: string }) {
  return language.startsWith("zh") ? labels.zh : labels.en;
}

function clampNonNegativeInteger(value: number, fallback: number) {
  if (!Number.isFinite(value) || value < 0) return fallback;
  return Math.round(value);
}

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const [activeSection, setActiveSection] = useState<SectionId>("general");
  const [mountedSections, setMountedSections] = useState<Set<SectionId>>(() => new Set(["general"]));
  const [searchText, setSearchText] = useState("");
  const [savedNotice, setSavedNotice] = useState("");
  const [studySettings, setStudySettings] = useState<StudySettingsRead | null>(null);
  const [studyError, setStudyError] = useState("");
  const [preferences, setPreferences] = useState<UiPreferences>(() => readUiPreferences());

  useEffect(() => {
    if (!savedNotice) return;
    const timer = globalThis.setTimeout(() => setSavedNotice(""), 1200);
    return () => globalThis.clearTimeout(timer);
  }, [savedNotice]);

  useEffect(() => {
    let ignore = false;

    async function loadStudySettings() {
      try {
        const data = await getStudySettings();
        if (!ignore) {
          setStudySettings(data);
        }
      } catch (error) {
        if (!ignore) {
          setStudyError(error instanceof Error ? error.message : "Failed to load study settings.");
        }
      }
    }

    void loadStudySettings();
    return () => {
      ignore = true;
    };
  }, []);

  const sections = useMemo<SectionDefinition[]>(
    () => [
      {
        id: "general",
        title: t("settings_general"),
        description: t("settings_theme"),
        keywords: [t("settings_theme"), t("settings_accent"), t("settings_card_font_size")],
      },
      {
        id: "study",
        title: t("settings_study"),
        description: t("settings_daily_new_limit"),
        keywords: [t("settings_daily_new_limit"), t("settings_daily_review_limit"), t("settings_local_only")],
      },
      {
        id: "shortcuts",
        title: t("settings_shortcuts"),
        description: t("settings_shortcut_space"),
        keywords: [t("settings_shortcut_space"), t("settings_shortcut_grades")],
      },
      {
        id: "notifications",
        title: t("settings_notifications"),
        description: t("settings_notifications_planned"),
        keywords: [t("settings_notifications_planned")],
      },
      {
        id: "data",
        title: t("settings_data"),
        description: t("settings_local_only"),
        keywords: [t("data_directory_heading"), t("data_directory_hint"), t("backup_heading"), t("diagnostics_heading")],
      },
      {
        id: "about",
        title: t("settings_about"),
        description: t("settings_local_only"),
        keywords: [t("settings_provider_section"), t("profile_docs_link"), t("profile_feedback_link")],
      },
    ],
    [t],
  );

  const filteredSections = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    if (!query) return sections;

    return sections.filter((section) => {
      const haystack = [section.title, section.description, ...section.keywords].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [searchText, sections]);

  useEffect(() => {
    if (filteredSections.length === 0) {
      return;
    }

    if (!filteredSections.some((section) => section.id === activeSection)) {
      setActiveSection(filteredSections[0].id);
    }
  }, [activeSection, filteredSections]);

  function updatePreferences(patch: Partial<UiPreferences>) {
    setPreferences((current) =>
      writeUiPreferences({
        ...current,
        ...patch,
      }),
    );
    setSavedNotice(t("settings_saved"));
  }

  async function updateStudySetting(key: "daily_new_limit" | "daily_review_limit", value: string) {
    const current = studySettings ?? {
      daily_new_limit: 0,
      daily_review_limit: 0,
      scheduler_mode: "traditional" as SchedulerMode,
      updated_at: "",
    };
    const parsed = clampNonNegativeInteger(Number(value), current[key]);
    const nextSettings: StudySettingsRead = {
      ...current,
      [key]: parsed,
    };

    setStudySettings(nextSettings);
    setStudyError("");

    try {
      const saved = await updateStudySettings({
        daily_new_limit: nextSettings.daily_new_limit,
        daily_review_limit: nextSettings.daily_review_limit,
        scheduler_mode: nextSettings.scheduler_mode,
      });
      setStudySettings(saved);
      setSavedNotice(t("settings_saved"));
    } catch (error) {
      setStudyError(error instanceof Error ? error.message : "Failed to save study settings.");
    }
  }

  async function updateSchedulerMode(value: SchedulerMode) {
    const current = studySettings ?? {
      daily_new_limit: 0,
      daily_review_limit: 0,
      scheduler_mode: "traditional" as SchedulerMode,
      updated_at: "",
    };
    const nextSettings: StudySettingsRead = {
      ...current,
      scheduler_mode: value,
    };

    setStudySettings(nextSettings);
    setStudyError("");

    try {
      const saved = await updateStudySettings({
        daily_new_limit: nextSettings.daily_new_limit,
        daily_review_limit: nextSettings.daily_review_limit,
        scheduler_mode: nextSettings.scheduler_mode,
      });
      setStudySettings(saved);
      setSavedNotice(t("settings_saved"));
    } catch (error) {
      setStudyError(error instanceof Error ? error.message : "Failed to save study settings.");
    }
  }

  function updateLanguage(language: "en" | "zh") {
    void i18n.changeLanguage(language);
    localStorage.setItem("lmca-lang", language);
    setSavedNotice(t("settings_saved"));
  }

  const accentOptions: { value: UiAccent; label: string }[] = [
    {
      value: "mint",
      label: optionLabel(i18n.language, { en: "Mint", zh: "\u8584\u8377\u7eff" }),
    },
    {
      value: "orange",
      label: optionLabel(i18n.language, { en: "Orange", zh: "\u6d3b\u529b\u6a59" }),
    },
    {
      value: "blue",
      label: optionLabel(i18n.language, { en: "Blue", zh: "\u62a4\u773c\u84dd" }),
    },
  ];

  const fontSizeOptions: { value: UiCardFontSize; label: string }[] = [
    {
      value: "compact",
      label: optionLabel(i18n.language, { en: "Compact", zh: "\u7d27\u51d1" }),
    },
    {
      value: "comfortable",
      label: optionLabel(i18n.language, { en: "Comfortable", zh: "\u6807\u51c6" }),
    },
    {
      value: "large",
      label: optionLabel(i18n.language, { en: "Large", zh: "\u5927\u5b57\u53f7" }),
    },
  ];

  const languageOptions = [
    { value: "zh", label: t("settings_language_zh") },
    { value: "en", label: t("settings_language_en") },
  ];

  const schedulerModeOptions: { value: SchedulerMode; label: string }[] = [
    { value: "traditional", label: t("settings_scheduler_mode_traditional") },
    { value: "ai_rl", label: t("settings_scheduler_mode_ai_rl") },
  ];

  const activeDefinition = filteredSections.find((section) => section.id === activeSection) ?? filteredSections[0];
  const activeId = activeDefinition?.id;

  useEffect(() => {
    if (!activeId) return;
    setMountedSections((current) => {
      if (current.has(activeId)) return current;
      const next = new Set(current);
      next.add(activeId);
      return next;
    });
  }, [activeId]);

  function shouldMountSection(id: SectionId) {
    return mountedSections.has(id) || activeId === id;
  }

  return (
    <div className="settings-page">
      <PageHeader title={t("settings_heading")} description={t("settings_subtitle")} />

      <div className="settings-center">
        <aside className="settings-nav">
          <FieldShell label={t("settings_search")}>
            <TextField
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder={t("settings_search")}
              aria-label={t("settings_search")}
            />
          </FieldShell>

          <nav className="settings-nav-list" aria-label={t("settings_heading")}>
            {filteredSections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={cn("settings-nav-item", activeSection === section.id && "is-active")}
                onClick={() => setActiveSection(section.id)}
                aria-pressed={activeSection === section.id}
              >
                <span>{section.title}</span>
              </button>
            ))}
          </nav>
        </aside>

        <main className="settings-pane">
          {savedNotice ? <StatusMessage tone="success">{savedNotice}</StatusMessage> : null}
          {studyError ? <StatusMessage tone="error">{studyError}</StatusMessage> : null}

          {shouldMountSection("general") ? (
            <SettingsSection title={t("settings_general")} description={t("settings_local_only")} hidden={activeId !== "general"}>
              <div className="settings-controls">
                <SettingsRow label={t("settings_language")}>
                  <SelectField
                    value={i18n.language.startsWith("zh") ? "zh" : "en"}
                    onChange={(event) => updateLanguage(event.target.value as "en" | "zh")}
                    aria-label={t("settings_language")}
                  >
                    {languageOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </SelectField>
                </SettingsRow>

                <SettingsRow label={t("settings_accent")}>
                  <SelectField
                    value={preferences.accent}
                    onChange={(event) => updatePreferences({ accent: event.target.value as UiAccent })}
                    aria-label={t("settings_accent")}
                  >
                    {accentOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </SelectField>
                </SettingsRow>

                <SettingsRow label={t("settings_card_font_size")}>
                  <SelectField
                    value={preferences.cardFontSize}
                    onChange={(event) =>
                      updatePreferences({ cardFontSize: event.target.value as UiCardFontSize })
                    }
                    aria-label={t("settings_card_font_size")}
                  >
                    {fontSizeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </SelectField>
                </SettingsRow>

                <label className="settings-toggle-row">
                  <span>{t("settings_flip_animation")}</span>
                  <button
                    type="button"
                    className={cn("settings-toggle", preferences.flipAnimation && "is-on")}
                    aria-pressed={preferences.flipAnimation}
                    aria-label={t("settings_flip_animation")}
                    onClick={() => updatePreferences({ flipAnimation: !preferences.flipAnimation })}
                  >
                    <span className="settings-toggle-knob" />
                  </button>
                </label>
              </div>
            </SettingsSection>
          ) : null}

          {shouldMountSection("study") ? (
            <SettingsSection title={t("settings_study")} description={t("settings_local_only")} hidden={activeId !== "study"}>
              <div className="settings-controls">
                <SettingsRow label={t("settings_daily_new_limit")}>
                  <TextField
                    type="number"
                    min={0}
                    step={1}
                    value={studySettings?.daily_new_limit ?? ""}
                    onChange={(event) => void updateStudySetting("daily_new_limit", event.target.value)}
                    aria-label={t("settings_daily_new_limit")}
                  />
                </SettingsRow>

                <SettingsRow label={t("settings_daily_review_limit")}>
                  <TextField
                    type="number"
                    min={0}
                    step={1}
                    value={studySettings?.daily_review_limit ?? ""}
                    onChange={(event) => void updateStudySetting("daily_review_limit", event.target.value)}
                    aria-label={t("settings_daily_review_limit")}
                  />
                </SettingsRow>

                <SettingsRow label={t("settings_scheduler_mode")}>
                  <SelectField
                    value={studySettings?.scheduler_mode ?? "traditional"}
                    onChange={(event) => void updateSchedulerMode(event.target.value as SchedulerMode)}
                    aria-label={t("settings_scheduler_mode")}
                  >
                    {schedulerModeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </SelectField>
                </SettingsRow>
              </div>
            </SettingsSection>
          ) : null}

          {shouldMountSection("shortcuts") ? (
            <SettingsSection title={t("settings_shortcuts")} description={t("settings_local_only")} hidden={activeId !== "shortcuts"}>
              <ul className="settings-detail-list">
                <li>{t("settings_shortcut_space")}</li>
                <li>{t("settings_shortcut_grades")}</li>
              </ul>
            </SettingsSection>
          ) : null}

          {shouldMountSection("notifications") ? (
            <SettingsSection title={t("settings_notifications")} description={t("settings_local_only")} hidden={activeId !== "notifications"}>
              <p className="settings-note">{t("settings_notifications_planned")}</p>
            </SettingsSection>
          ) : null}

          {shouldMountSection("data") ? (
            <div className="settings-section-stack" hidden={activeId !== "data"}>
              <DataDirectoryPanel />
              <BackupPanel />
              <DiagnosticsPanel />
            </div>
          ) : null}

          {shouldMountSection("about") ? (
            <div className="settings-section-stack" hidden={activeId !== "about"}>
              <ProviderForm />
              <SettingsSection title={t("settings_about")} description={t("settings_local_only")}>
                <div className="settings-link-row">
                  <a href="#" className="app-nav-item">
                    {t("profile_docs_link")}
                  </a>
                  <a href="#" className="app-nav-item">
                    {t("profile_feedback_link")}
                  </a>
                </div>
              </SettingsSection>
            </div>
          ) : null}

          {!activeDefinition ? (
            <SettingsSection title={t("settings_heading")} description={t("settings_subtitle")}>
              <p className="settings-note">
                {i18n.language.startsWith("zh") ? "\u6ca1\u6709\u5339\u914d\u7684\u8bbe\u7f6e\u9879\u3002" : "No matching settings."}
              </p>
            </SettingsSection>
          ) : null}
        </main>
      </div>
    </div>
  );
}
