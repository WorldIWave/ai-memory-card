import test from "node:test";
import assert from "node:assert/strict";

import {
  collectSetupHints,
  checkPathExists,
  checkPythonModule,
  formatDoctorReport,
  resolveCargoCommand,
  resolveEffectiveBackendPython,
  summarizeChecks,
} from "./doctor.mjs";

test("summarizeChecks marks overall status as blocked when required tools are missing", () => {
  const summary = summarizeChecks([
    { name: "Node.js", ok: true, required: true, detail: "v22.0.0" },
    { name: "Cargo", ok: false, required: true, detail: "not installed" },
    { name: "Python", ok: true, required: true, detail: "3.11.0" },
  ]);

  assert.equal(summary.ok, false);
  assert.equal(summary.blocked.length, 1);
  assert.equal(summary.blocked[0].name, "Cargo");
});

test("formatDoctorReport includes actionable next steps for missing required tools", () => {
  const report = formatDoctorReport({
    ok: false,
    blocked: [{ name: "Cargo", ok: false, required: true, detail: "not installed" }],
    warnings: [],
    passing: [{ name: "Node.js", ok: true, required: true, detail: "v22.0.0" }],
  });

  assert.match(report, /Desktop environment check: blocked/i);
  assert.match(report, /Cargo/i);
  assert.match(report, /install the missing required tools/i);
});

test("checkPathExists reports missing required paths as blocked", () => {
  const check = checkPathExists({
    name: "Backend entry",
    path: "Z:/missing/app/main.py",
  });

  assert.equal(check.ok, false);
  assert.equal(check.required, true);
  assert.match(check.detail, /missing/i);
});

test("checkPythonModule reports import success and failure clearly", () => {
  const okCheck = checkPythonModule({
    name: "JSON module",
    moduleName: "json",
    pythonCommand: "python",
    importCommand: "import json; print('ok')",
  });
  const missingCheck = checkPythonModule({
    name: "Missing module",
    moduleName: "module_that_should_not_exist_for_lmca_tests",
    pythonCommand: "python",
    importCommand: "import module_that_should_not_exist_for_lmca_tests",
  });

  assert.equal(okCheck.ok, true);
  assert.match(okCheck.detail, /ok/i);
  assert.equal(missingCheck.ok, false);
  assert.match(missingCheck.detail, /module_that_should_not_exist_for_lmca_tests/i);
});

test("collectSetupHints explains that desktop scripts can auto-use a detected backend env", () => {
  const hints = collectSetupHints({
    checks: [
      { name: "Python uvicorn module", ok: false, required: true, detail: "ModuleNotFoundError" },
      { name: "Cargo", ok: false, required: true, detail: "ENOENT" },
    ],
    pythonCommand: "python",
    backendPythonCandidates: ["D:/condaa/envs/ai-memory-card-backend/python.exe"],
    configuredBackendPython: "",
  });

  assert.match(hints.join("\n"), /automatically use/i);
  assert.match(hints.join("\n"), /ai-memory-card-backend\/python\.exe/i);
});

test("collectSetupHints explains missing multipart dependency for backend uploads", () => {
  const hints = collectSetupHints({
    checks: [
      { name: "Python multipart module", ok: false, required: true, detail: "ModuleNotFoundError" },
    ],
    pythonCommand: "D:/condaa/envs/ai-memory-card-backend/python.exe",
    backendPythonCandidates: ["D:/condaa/envs/ai-memory-card-backend/python.exe"],
    configuredBackendPython: "",
  });

  assert.match(hints.join("\n"), /python-multipart/i);
  assert.match(hints.join("\n"), /backend Python/i);
});

test("resolveEffectiveBackendPython prefers configured or detected backend Python over bare python", () => {
  const configured = resolveEffectiveBackendPython({
    configuredBackendPython: "D:/explicit/python.exe",
    fallbackPythonCommand: "python",
    backendPythonCandidates: ["D:/condaa/envs/ai-memory-card-backend/python.exe"],
  });
  const detected = resolveEffectiveBackendPython({
    configuredBackendPython: "",
    fallbackPythonCommand: "python",
    backendPythonCandidates: ["D:/condaa/envs/ai-memory-card-backend/python.exe"],
  });

  assert.equal(configured, "D:/explicit/python.exe");
  assert.equal(detected, "D:/condaa/envs/ai-memory-card-backend/python.exe");
});

test("resolveCargoCommand falls back to the standard cargo bin path when PATH is stale", () => {
  const configured = resolveCargoCommand({
    configuredCargoCommand: "D:/custom/cargo.exe",
    cargoCandidates: ["C:/Users/test/.cargo/bin/cargo.exe"],
  });
  const detected = resolveCargoCommand({
    configuredCargoCommand: "",
    cargoCandidates: ["C:/Users/test/.cargo/bin/cargo.exe"],
  });

  assert.equal(configured, "D:/custom/cargo.exe");
  assert.equal(detected, "C:/Users/test/.cargo/bin/cargo.exe");
});
