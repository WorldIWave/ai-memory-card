import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  ensureTauriResourcePlaceholders,
} from "./run-rust.mjs";

import {
  buildDesktopEnv,
  pickBackendPythonForDesktop,
  resolveCargoBinDirectory,
} from "./run-tauri.mjs";

function makeTempDir() {
  return fs.mkdtempSync(path.join(fs.realpathSync(process.env.TEMP || "."), "lmca-run-rust-"));
}

test("pickBackendPythonForDesktop prefers explicit LMCA_BACKEND_PYTHON", () => {
  const picked = pickBackendPythonForDesktop({
    configuredBackendPython: "D:/explicit/python.exe",
    backendPythonCandidates: [
      "D:/condaa/envs/ai-memory-card-backend/python.exe",
      "D:/repo/apps/local-web/backend/.venv/Scripts/python.exe",
    ],
  });

  assert.equal(picked, "D:/explicit/python.exe");
});

test("pickBackendPythonForDesktop falls back to detected candidate", () => {
  const picked = pickBackendPythonForDesktop({
    configuredBackendPython: "",
    backendPythonCandidates: ["D:/condaa/envs/ai-memory-card-backend/python.exe"],
  });

  assert.equal(picked, "D:/condaa/envs/ai-memory-card-backend/python.exe");
});

test("resolveCargoBinDirectory returns the directory containing cargo.exe", () => {
  const cargoBin = resolveCargoBinDirectory({
    configuredCargoCommand: "",
    cargoCandidates: ["C:/Users/test/.cargo/bin/cargo.exe"],
  });

  assert.equal(cargoBin, "C:/Users/test/.cargo/bin");
});

test("buildDesktopEnv injects backend python and cargo bin into the child environment", () => {
  const env = buildDesktopEnv({
    baseEnv: { PATH: "C:/Windows/System32" },
    backendPython: "D:/condaa/envs/ai-memory-card-backend/python.exe",
    configuredCargoCommand: "",
    cargoCandidates: ["C:/Users/test/.cargo/bin/cargo.exe"],
    pathDelimiter: ";",
  });

  assert.equal(env.LMCA_BACKEND_PYTHON, "D:/condaa/envs/ai-memory-card-backend/python.exe");
  assert.match(env.PATH, /C:\/Users\/test\/\.cargo\/bin/);
  assert.match(env.PATH, /C:\/Windows\/System32/);
});

test("ensureTauriResourcePlaceholders creates plugin resource placeholders for cargo tests", () => {
  const desktopRoot = makeTempDir();

  ensureTauriResourcePlaceholders({ desktopRoot });

  assert.equal(fs.existsSync(path.join(desktopRoot, ".release-staging", "runtime", "plugins")), true);
  assert.equal(fs.existsSync(path.join(desktopRoot, ".release-staging", "runtime", "plugins", ".keep")), true);
  assert.equal(fs.existsSync(path.join(desktopRoot, ".release-staging", "runtime", "backend")), true);
  assert.equal(fs.existsSync(path.join(desktopRoot, ".release-staging", "runtime", "python")), true);
  assert.equal(fs.existsSync(path.join(desktopRoot, ".release-staging", "runtime", "runtime-manifest.json")), true);
});

test("desktop crate declares the Tauri release custom-protocol feature contract", () => {
  const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const cargoToml = fs.readFileSync(path.join(desktopRoot, "src-tauri", "Cargo.toml"), "utf8");

  assert.match(
    cargoToml,
    /\[features\][\s\S]*^custom-protocol\s*=\s*\[\s*"tauri\/custom-protocol"\s*\]/m,
  );
});

test("desktop crate enables the Tauri window-data-url feature for startup failure windows", () => {
  const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const cargoToml = fs.readFileSync(path.join(desktopRoot, "src-tauri", "Cargo.toml"), "utf8");

  assert.match(cargoToml, /tauri\s*=\s*\{[^}]*features\s*=\s*\[[^\]]*"window-data-url"[^\]]*\][^}]*\}/m);
});
