import { describe, expect, it } from "vitest";

import en from "./locales/en.json";
import zh from "./locales/zh.json";

function flattenKeys(value: unknown, prefix = ""): string[] {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, nested]) =>
      flattenKeys(nested, prefix ? `${prefix}.${key}` : key),
    );
  }

  return [prefix];
}

function containsMojibake(value: unknown): boolean {
  if (typeof value === "string") {
    return /[�]|æ|é|ç|å|è|ã|î|Ð|Ñ/.test(value);
  }

  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.values(value as Record<string, unknown>).some(containsMojibake);
  }

  return false;
}

describe("i18n locale files", () => {
  it("keeps English and Chinese locale keys aligned", () => {
    expect(flattenKeys(zh).sort()).toEqual(flattenKeys(en).sort());
  });

  it("does not expose mojibake in visible locale strings", () => {
    expect(containsMojibake(en)).toBe(false);
    expect(containsMojibake(zh)).toBe(false);
  });
});
