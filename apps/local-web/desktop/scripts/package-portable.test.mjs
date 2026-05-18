import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assemblePortableAppDirectory,
  buildPortableLayout,
  buildZipCommand,
  packagePortable,
  readJsonFile,
  resolveTauriReleaseBinaryPath,
  TAURI_BUNDLE_RESOURCE_MAP,
} from "./package-portable.mjs";

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lmca-package-portable-"));
}

function writeFile(root, relativePath, contents = "") {
  const targetPath = path.join(root, relativePath);
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, contents);
}

test("buildPortableLayout targets one staged app directory and zip path", () => {
  const layout = buildPortableLayout("D:/repo/apps/local-web/desktop");

  assert.equal(layout.stagingRoot, path.join("D:/repo/apps/local-web/desktop", ".release-staging"));
  assert.equal(layout.appDir, path.join("D:/repo/apps/local-web/desktop", ".release-staging", "app"));
  assert.equal(layout.runtimeDir, path.join("D:/repo/apps/local-web/desktop", ".release-staging", "runtime"));
  assert.equal(
    layout.zipPath,
    path.join("D:/repo/apps/local-web/desktop", ".release-staging", "AIMemoryCard-portable.zip"),
  );
});

test("buildZipCommand uses Compress-Archive for the staged app directory", () => {
  const expectedAppDir = path.win32.join("D:/repo/apps/local-web/desktop/.release-staging/app", "*");
  const expectedZipPath = path.win32.normalize(
    "D:/repo/apps/local-web/desktop/.release-staging/AIMemoryCard-portable.zip",
  );
  const command = buildZipCommand({
    appDir: "D:/repo/apps/local-web/desktop/.release-staging/app",
    zipPath: "D:/repo/apps/local-web/desktop/.release-staging/AIMemoryCard-portable.zip",
  });

  assert.equal(command.executable, "powershell.exe");
  assert.deepEqual(command.args.slice(0, 2), ["-NoProfile", "-Command"]);
  assert.equal(
    command.args[2],
    `Compress-Archive -Path '${expectedAppDir}' -DestinationPath '${expectedZipPath}' -Force`,
  );
});

test("assemblePortableAppDirectory copies the built app and staged runtime into the portable layout", () => {
  const desktopRoot = makeTempDir();
  const layout = buildPortableLayout(desktopRoot);
  const binaryPath = path.join(desktopRoot, "src-tauri", "target", "release", "ai-memory-card-desktop.exe");

  writeFile(desktopRoot, "src-tauri/target/release/ai-memory-card-desktop.exe", "exe");
  writeFile(desktopRoot, ".release-staging/runtime/backend/app/main.py", "print('ok')");
  writeFile(desktopRoot, ".release-staging/runtime/plugins/rag-core/plugin.json", "{}");
  writeFile(desktopRoot, ".release-staging/runtime/python/python.exe", "python");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  const result = assemblePortableAppDirectory({
    binaryPath,
    layout,
    executableName: "AI Memory Card.exe",
  });

  assert.equal(result.appDir, layout.appDir);
  assert.equal(result.executablePath, path.join(layout.appDir, "AI Memory Card.exe"));
  assert.equal(fs.readFileSync(result.executablePath, "utf8"), "exe");
  assert.deepEqual(
    fs.readdirSync(layout.appDir).filter((entry) => entry !== "AI Memory Card.exe").sort(),
    Object.values(TAURI_BUNDLE_RESOURCE_MAP).sort(),
  );
  assert.equal(fs.readFileSync(path.join(layout.appDir, "backend", "app", "main.py"), "utf8"), "print('ok')");
  assert.equal(fs.readFileSync(path.join(layout.appDir, "plugins", "rag-core", "plugin.json"), "utf8"), "{}");
  assert.equal(fs.readFileSync(path.join(layout.appDir, "python", "python.exe"), "utf8"), "python");
  assert.equal(fs.readFileSync(path.join(layout.appDir, "runtime-manifest.json"), "utf8"), "{}");
});

test("assemblePortableAppDirectory fails clearly when the Tauri release binary is missing", () => {
  const desktopRoot = makeTempDir();
  const layout = buildPortableLayout(desktopRoot);

  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  assert.throws(
    () =>
      assemblePortableAppDirectory({
        binaryPath: path.join(desktopRoot, "src-tauri", "target", "release", "ai-memory-card-desktop.exe"),
        layout,
        executableName: "AI Memory Card.exe",
      }),
    /Expected Tauri release binary was not found/i,
  );
});

test("tauri bundle resources map staged runtime entries onto backend, python, and runtime-manifest.json", () => {
  const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const tauriConfig = readJsonFile(path.join(desktopRoot, "src-tauri", "tauri.conf.json"));

  assert.equal(tauriConfig.build.distDir, "../../frontend/dist");
  assert.deepEqual(tauriConfig.tauri.bundle.resources, TAURI_BUNDLE_RESOURCE_MAP);
});

test("packagePortable assembles the portable app and uses the injected zip runner", () => {
  const desktopRoot = makeTempDir();
  let zipInvocation = null;

  writeFile(
    desktopRoot,
    "src-tauri/Cargo.toml",
    '[package]\nname = "ai-memory-card-desktop"\nversion = "0.1.0"\n',
  );
  writeFile(desktopRoot, "src-tauri/target/release/ai-memory-card-desktop", "bin");
  writeFile(desktopRoot, ".release-staging/runtime/backend/app/main.py", "print('ok')");
  writeFile(desktopRoot, ".release-staging/runtime/plugins/rag-core/plugin.json", "{}");
  writeFile(desktopRoot, ".release-staging/runtime/python/python.exe", "python");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  const result = packagePortable({
    desktopRoot,
    productName: "AI Memory Card",
    platform: "linux",
    runZipCommand(command, options) {
      zipInvocation = { command, options };
      return { status: 0 };
    },
  });

  assert.ok(zipInvocation);
  assert.equal(zipInvocation.options.cwd, desktopRoot);
  assert.equal(zipInvocation.command.executable, "powershell.exe");
  assert.equal(result.executablePath, path.join(desktopRoot, ".release-staging", "app", "AI Memory Card.exe"));
  assert.equal(result.zipPath, path.join(desktopRoot, ".release-staging", "AIMemoryCard-portable.zip"));
  assert.deepEqual(
    fs.readdirSync(result.appDir).filter((entry) => entry !== "AI Memory Card.exe").sort(),
    Object.values(TAURI_BUNDLE_RESOURCE_MAP).sort(),
  );
});

test("packagePortable resolves the Windows release binary from the Tauri product name", () => {
  const desktopRoot = makeTempDir();
  let zipInvocation = null;

  writeFile(
    desktopRoot,
    "src-tauri/Cargo.toml",
    '[package]\nname = "ai-memory-card-desktop"\nversion = "0.1.0"\n',
  );
  writeFile(desktopRoot, "src-tauri/target/release/AI Memory Card.exe", "exe");
  writeFile(desktopRoot, ".release-staging/runtime/backend/app/main.py", "print('ok')");
  writeFile(desktopRoot, ".release-staging/runtime/plugins/rag-core/plugin.json", "{}");
  writeFile(desktopRoot, ".release-staging/runtime/python/python.exe", "python");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  const result = packagePortable({
    desktopRoot,
    productName: "AI Memory Card",
    platform: "win32",
    runZipCommand(command, options) {
      zipInvocation = { command, options };
      return { status: 0 };
    },
  });

  assert.ok(zipInvocation);
  assert.equal(result.binaryPath, path.join(desktopRoot, "src-tauri", "target", "release", "AI Memory Card.exe"));
  assert.equal(fs.readFileSync(path.join(result.appDir, "AI Memory Card.exe"), "utf8"), "exe");
});

test("resolveTauriReleaseBinaryPath prefers the Windows product-name binary when it exists", () => {
  const desktopRoot = makeTempDir();
  const productBinaryPath = path.join(desktopRoot, "src-tauri", "target", "release", "AI Memory Card.exe");

  writeFile(desktopRoot, "src-tauri/target/release/AI Memory Card.exe", "product");
  writeFile(desktopRoot, "src-tauri/target/release/ai-memory-card-desktop.exe", "cargo");

  const resolvedPath = resolveTauriReleaseBinaryPath({
    desktopRoot,
    cargoPackageName: "ai-memory-card-desktop",
    productName: "AI Memory Card",
    platform: "win32",
  });

  assert.equal(resolvedPath, productBinaryPath);
});

test("resolveTauriReleaseBinaryPath falls back to the cargo-package binary when the Windows product-name binary is missing", () => {
  const desktopRoot = makeTempDir();
  const cargoBinaryPath = path.join(desktopRoot, "src-tauri", "target", "release", "ai-memory-card-desktop.exe");

  writeFile(desktopRoot, "src-tauri/target/release/ai-memory-card-desktop.exe", "cargo");

  const resolvedPath = resolveTauriReleaseBinaryPath({
    desktopRoot,
    cargoPackageName: "ai-memory-card-desktop",
    productName: "AI Memory Card",
    platform: "win32",
  });

  assert.equal(resolvedPath, cargoBinaryPath);
});

test("packagePortable strips a trailing .exe from productName when naming the staged executable", () => {
  const desktopRoot = makeTempDir();

  writeFile(
    desktopRoot,
    "src-tauri/Cargo.toml",
    '[package]\nname = "ai-memory-card-desktop"\nversion = "0.1.0"\n',
  );
  writeFile(desktopRoot, "src-tauri/target/release/AI Memory Card.exe", "exe");
  writeFile(desktopRoot, ".release-staging/runtime/backend/app/main.py", "print('ok')");
  writeFile(desktopRoot, ".release-staging/runtime/plugins/rag-core/plugin.json", "{}");
  writeFile(desktopRoot, ".release-staging/runtime/python/python.exe", "python");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  const result = packagePortable({
    desktopRoot,
    productName: "AI Memory Card.exe",
    platform: "win32",
    runZipCommand() {
      return { status: 0 };
    },
  });

  assert.equal(result.binaryPath, path.join(desktopRoot, "src-tauri", "target", "release", "AI Memory Card.exe"));
  assert.equal(result.executablePath, path.join(desktopRoot, ".release-staging", "app", "AI Memory Card.exe"));
});

test("packagePortable falls back to the default executable name when productName is null", () => {
  const desktopRoot = makeTempDir();

  writeFile(
    desktopRoot,
    "src-tauri/Cargo.toml",
    '[package]\nname = "ai-memory-card-desktop"\nversion = "0.1.0"\n',
  );
  writeFile(desktopRoot, "src-tauri/target/release/ai-memory-card-desktop.exe", "exe");
  writeFile(desktopRoot, ".release-staging/runtime/backend/app/main.py", "print('ok')");
  writeFile(desktopRoot, ".release-staging/runtime/plugins/rag-core/plugin.json", "{}");
  writeFile(desktopRoot, ".release-staging/runtime/python/python.exe", "python");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", "{}");

  const result = packagePortable({
    desktopRoot,
    productName: null,
    platform: "win32",
    runZipCommand() {
      return { status: 0 };
    },
  });

  assert.equal(result.binaryPath, path.join(desktopRoot, "src-tauri", "target", "release", "ai-memory-card-desktop.exe"));
  assert.equal(result.executablePath, path.join(desktopRoot, ".release-staging", "app", "AI Memory Card.exe"));
});
