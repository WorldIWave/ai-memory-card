/**
 * Input: localStorage ?? UI ????  |  Output: ???????????????
 * Output: ??????????????? UI ????????
 * Role: ?????????????????????
 * Use: ??????? UI ???????????????????
 */
export type UiAccent = "mint" | "orange" | "blue";
export type UiCardFontSize = "compact" | "comfortable" | "large";

export interface UiPreferences {
  accent: UiAccent;
  cardFontSize: UiCardFontSize;
  flipAnimation: boolean;
}

const STORAGE_KEY = "lmca.uiPreferences";

export const DEFAULT_UI_PREFERENCES: UiPreferences = {
  accent: "mint",
  cardFontSize: "comfortable",
  flipAnimation: true,
};

const accentValues = new Set<UiAccent>(["mint", "orange", "blue"]);
const cardFontSizeValues = new Set<UiCardFontSize>(["compact", "comfortable", "large"]);

function getStorage(): Storage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function normalizePreferences(value: unknown): UiPreferences {
  if (!isRecord(value)) {
    return DEFAULT_UI_PREFERENCES;
  }

  return {
    accent: accentValues.has(value.accent as UiAccent) ? (value.accent as UiAccent) : DEFAULT_UI_PREFERENCES.accent,
    cardFontSize: cardFontSizeValues.has(value.cardFontSize as UiCardFontSize)
      ? (value.cardFontSize as UiCardFontSize)
      : DEFAULT_UI_PREFERENCES.cardFontSize,
    flipAnimation:
      typeof value.flipAnimation === "boolean" ? value.flipAnimation : DEFAULT_UI_PREFERENCES.flipAnimation,
  };
}

function applyPreferenceDataset(preferences: UiPreferences) {
  const root = globalThis.document?.documentElement;
  if (!root) return;

  root.dataset.accent = preferences.accent;
  root.dataset.cardFontSize = preferences.cardFontSize;
  root.dataset.flipAnimation = preferences.flipAnimation ? "on" : "off";
}

export function readUiPreferences(): UiPreferences {
  const storage = getStorage();
  let raw: string | null = null;
  try {
    raw = storage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    raw = null;
  }

  if (!raw) {
    applyPreferenceDataset(DEFAULT_UI_PREFERENCES);
    return DEFAULT_UI_PREFERENCES;
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    const preferences = normalizePreferences(parsed);
    applyPreferenceDataset(preferences);
    return preferences;
  } catch {
    applyPreferenceDataset(DEFAULT_UI_PREFERENCES);
    return DEFAULT_UI_PREFERENCES;
  }
}

export function writeUiPreferences(preferences: UiPreferences) {
  const normalized = normalizePreferences(preferences);
  const storage = getStorage();

  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // Settings still apply for the current session when browser storage is unavailable.
  } finally {
    applyPreferenceDataset(normalized);
  }

  return normalized;
}
