import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildReleaseAssetNames,
  buildReleaseOutputLayout,
  collectReleaseArtifacts,
  releaseLocal,
  runScript,
} from "./release-local.mjs";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lmca-release-local-"));
}

function writeFile(root, relativePath, contents = "") {
  const targetPath = path.join(root, relativePath);
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, contents);
}

function sha256(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

test("buildReleaseAssetNames returns the user-facing MSI, ZIP, manifest, and checksum file names", () => {
  assert.deepEqual(buildReleaseAssetNames("0.1.0"), {
    msi: "AIMemoryCard-0.1.0-x64-setup.msi",
    zip: "AIMemoryCard-0.1.0-x64-portable.zip",
    manifest: "AIMemoryCard-0.1.0-runtime-manifest.json",
    checksums: "AIMemoryCard-0.1.0-SHA256SUMS.txt",
  });
});

test("buildReleaseOutputLayout targets the versioned release output and staging sources", () => {
  const layout = buildReleaseOutputLayout("D:/repo/apps/local-web/desktop", "0.1.0");

  assert.deepEqual(layout, {
    version: "0.1.0",
    outputDir: path.join("D:/repo/apps/local-web/desktop", ".release-output", "0.1.0"),
    msiSourceDir: path.join("D:/repo/apps/local-web/desktop", "src-tauri", "target", "release", "bundle", "msi"),
    portableZipPath: path.join("D:/repo/apps/local-web/desktop", ".release-staging", "AIMemoryCard-portable.zip"),
    runtimeManifestPath: path.join(
      "D:/repo/apps/local-web/desktop",
      ".release-staging",
      "runtime",
      "runtime-manifest.json",
    ),
  });
});

test("tauri bundle config declares the Windows .ico icon used by release builds", () => {
  const tauriConfigPath = path.join(desktopRoot, "src-tauri", "tauri.conf.json");
  const tauriConfig = JSON.parse(fs.readFileSync(tauriConfigPath, "utf8"));
  const iconPath = path.join(desktopRoot, "src-tauri", "icons", "icon.ico");

  assert.equal(Array.isArray(tauriConfig.tauri.bundle.icon), true);
  assert.equal(tauriConfig.tauri.bundle.icon.includes("icons/icon.ico"), true);
  assert.equal(fs.existsSync(iconPath), true);
});

test("tauri bundle config uses a custom current-user WiX template for MSI installs", () => {
  const tauriConfigPath = path.join(desktopRoot, "src-tauri", "tauri.conf.json");
  const tauriConfig = JSON.parse(fs.readFileSync(tauriConfigPath, "utf8"));
  const wixTemplateRelativePath = tauriConfig.tauri.bundle.windows?.wix?.template;
  const wixTemplatePath = wixTemplateRelativePath
    ? path.join(desktopRoot, "src-tauri", wixTemplateRelativePath.replace(/^\.\//, ""))
    : null;
  const wixTemplateContents = wixTemplatePath ? fs.readFileSync(wixTemplatePath, "utf8") : "";

  assert.equal(wixTemplateRelativePath, "./windows/current-user.wxs");
  assert.equal(fs.existsSync(wixTemplatePath), true);
  assert.match(wixTemplateContents, /InstallScope="perUser"/);
  assert.match(wixTemplateContents, /InstallPrivileges="limited"/);
  assert.match(wixTemplateContents, /PlatformProgramFilesFolder/);
  assert.doesNotMatch(wixTemplateContents, /<Directory Id="LocalAppDataFolder">/);
  assert.match(
    wixTemplateContents,
    /<SetDirectory[^>]+Id="INSTALLDIR"[^>]+Value="\[LocalAppDataFolder\][^"]+"/,
  );
  assert.match(wixTemplateContents, /Programs\\\\\{\{product_name\}\}/);
});

test("collectReleaseArtifacts copies MSI, ZIP, and runtime manifest into one versioned directory", () => {
  const desktopRoot = makeTempDir();
  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  writeFile(
    desktopRoot,
    "src-tauri/target/release/bundle/msi/ai-memory-card_0.1.0_x64_en-US.msi",
    "msi",
  );
  writeFile(desktopRoot, ".release-staging/AIMemoryCard-portable.zip", "zip");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", '{"appVersion":"0.1.0"}');

  const result = collectReleaseArtifacts({ desktopRoot });

  assert.equal(result.outputDir, path.join(desktopRoot, ".release-output", "0.1.0"));
  assert.equal(
    fs.readFileSync(path.join(result.outputDir, "AIMemoryCard-0.1.0-x64-setup.msi"), "utf8"),
    "msi",
  );
  assert.equal(
    fs.readFileSync(path.join(result.outputDir, "AIMemoryCard-0.1.0-x64-portable.zip"), "utf8"),
    "zip",
  );
  assert.equal(
    fs.readFileSync(path.join(result.outputDir, "AIMemoryCard-0.1.0-runtime-manifest.json"), "utf8"),
    '{"appVersion":"0.1.0"}',
  );
  assert.equal(
    fs.existsSync(path.join(result.outputDir, "AIMemoryCard-0.1.0-SHA256SUMS.txt")),
    true,
  );
});

test("collectReleaseArtifacts writes SHA-256 checksums using the renamed output file names", () => {
  const desktopRoot = makeTempDir();
  const manifestContents = '{"appVersion":"0.1.0"}';

  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  writeFile(desktopRoot, "src-tauri/target/release/bundle/msi/ai-memory-card_0.1.0_x64_en-US.msi", "msi");
  writeFile(desktopRoot, ".release-staging/AIMemoryCard-portable.zip", "zip");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", manifestContents);

  const result = collectReleaseArtifacts({ desktopRoot });
  const checksumPath = path.join(result.outputDir, result.assetNames.checksums);

  assert.equal(
    fs.readFileSync(checksumPath, "utf8"),
    [
      `${sha256("msi")}  ${result.assetNames.msi}`,
      `${sha256("zip")}  ${result.assetNames.zip}`,
      `${sha256(manifestContents)}  ${result.assetNames.manifest}`,
      "",
    ].join("\n"),
  );
});

test("collectReleaseArtifacts throws clearly when no MSI artifact exists", () => {
  const desktopRoot = makeTempDir();

  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  fs.mkdirSync(path.join(desktopRoot, "src-tauri", "target", "release", "bundle", "msi"), { recursive: true });
  writeFile(desktopRoot, ".release-staging/AIMemoryCard-portable.zip", "zip");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", '{"appVersion":"0.1.0"}');

  assert.throws(
    () => collectReleaseArtifacts({ desktopRoot }),
    /Expected exactly one MSI artifact.*found 0/i,
  );
});

test("collectReleaseArtifacts throws clearly when multiple MSI artifacts exist", () => {
  const desktopRoot = makeTempDir();

  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  writeFile(desktopRoot, "src-tauri/target/release/bundle/msi/first.msi", "first");
  writeFile(desktopRoot, "src-tauri/target/release/bundle/msi/second.msi", "second");
  writeFile(desktopRoot, ".release-staging/AIMemoryCard-portable.zip", "zip");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", '{"appVersion":"0.1.0"}');

  assert.throws(
    () => collectReleaseArtifacts({ desktopRoot }),
    /Expected exactly one MSI artifact.*found 2/i,
  );
});

test("collectReleaseArtifacts removes stale files from an existing output directory on success", () => {
  const desktopRoot = makeTempDir();
  const outputDir = path.join(desktopRoot, ".release-output", "0.1.0");

  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  writeFile(desktopRoot, "src-tauri/target/release/bundle/msi/ai-memory-card_0.1.0_x64_en-US.msi", "msi");
  writeFile(desktopRoot, ".release-staging/AIMemoryCard-portable.zip", "zip");
  writeFile(desktopRoot, ".release-staging/runtime/runtime-manifest.json", '{"appVersion":"0.1.0"}');
  writeFile(desktopRoot, ".release-output/0.1.0/stale.txt", "stale");

  collectReleaseArtifacts({ desktopRoot });

  assert.equal(fs.existsSync(path.join(outputDir, "stale.txt")), false);
});

test("collectReleaseArtifacts preserves an existing output directory when required inputs are missing", () => {
  const desktopRoot = makeTempDir();
  const outputDir = path.join(desktopRoot, ".release-output", "0.1.0");
  const preservedPath = path.join(outputDir, "preserved.txt");

  writeFile(desktopRoot, "package.json", JSON.stringify({ version: "0.1.0" }));
  writeFile(desktopRoot, "src-tauri/target/release/bundle/msi/ai-memory-card_0.1.0_x64_en-US.msi", "msi");
  writeFile(desktopRoot, ".release-output/0.1.0/preserved.txt", "keep me");

  assert.throws(
    () => collectReleaseArtifacts({ desktopRoot }),
    /portable zip/i,
  );
  assert.equal(fs.readFileSync(preservedPath, "utf8"), "keep me");
});

test("runScript invokes npm run with the desktop root and provided environment", () => {
  const calls = [];
  const originalValue = process.env.LMCA_TEST_BASE_ENV;
  process.env.LMCA_TEST_BASE_ENV = "from-process-env";

  try {
    runScript("doctor", {
      desktopRoot: "D:/repo/apps/local-web/desktop",
      env: { LMCA_EMBEDDED_PYTHON_ROOT: "D:/runtime/python-3.11.9-embed-amd64" },
      platform: "linux",
      spawn(command, args, options) {
        calls.push({ command, args, options });
        return { status: 0 };
      },
    });
  } finally {
    if (originalValue === undefined) {
      delete process.env.LMCA_TEST_BASE_ENV;
    } else {
      process.env.LMCA_TEST_BASE_ENV = originalValue;
    }
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "npm");
  assert.deepEqual(calls[0].args, ["run", "doctor"]);
  assert.equal(calls[0].options.cwd, "D:/repo/apps/local-web/desktop");
  assert.equal(calls[0].options.env.LMCA_EMBEDDED_PYTHON_ROOT, "D:/runtime/python-3.11.9-embed-amd64");
  assert.equal(calls[0].options.env.LMCA_TEST_BASE_ENV, "from-process-env");
  assert.equal(calls[0].options.stdio, "inherit");
});

test("runScript uses ComSpec and cmd.exe syntax on Windows", () => {
  const calls = [];

  runScript("doctor", {
    desktopRoot: "D:/repo/apps/local-web/desktop",
    env: { ComSpec: "C:/Windows/System32/cmd.exe" },
    platform: "win32",
    spawn(command, args, options) {
      calls.push({ command, args, options });
      return { status: 0 };
    },
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "C:/Windows/System32/cmd.exe");
  assert.deepEqual(calls[0].args, ["/d", "/s", "/c", "npm.cmd run doctor"]);
  assert.equal(calls[0].options.cwd, "D:/repo/apps/local-web/desktop");
  assert.equal(calls[0].options.stdio, "inherit");
});

test("runScript falls back to cmd.exe on Windows when ComSpec is unset", () => {
  const calls = [];

  runScript("build", {
    desktopRoot: "D:/repo/apps/local-web/desktop",
    env: { ComSpec: "" },
    platform: "win32",
    spawn(command, args) {
      calls.push({ command, args });
      return { status: 0 };
    },
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "cmd.exe");
  assert.deepEqual(calls[0].args, ["/d", "/s", "/c", "npm.cmd run build"]);
});

test("runScript throws the documented error when npm exits non-zero", () => {
  assert.throws(
    () =>
      runScript("build", {
        desktopRoot: "D:/repo/apps/local-web/desktop",
        spawn() {
          return { status: 7 };
        },
      }),
    /npm run build failed with exit code 7/i,
  );
});

test("runScript rethrows spawn errors", () => {
  const expected = new Error("spawn failed");

  assert.throws(
    () =>
      runScript("build", {
        desktopRoot: "D:/repo/apps/local-web/desktop",
        spawn() {
          return { error: expected };
        },
      }),
    expected,
  );
});

test("releaseLocal validates embedded python, runs the expected scripts with context, and then collects artifacts", () => {
  const scriptCalls = [];
  const collectedCalls = [];
  const env = { LMCA_EMBEDDED_PYTHON_ROOT: "D:/runtime/python-3.11.9-embed-amd64" };

  const result = releaseLocal({
    desktopRoot: "D:/repo/apps/local-web/desktop",
    env,
    validateEmbeddedPythonRoot(root) {
      assert.equal(root, "D:/runtime/python-3.11.9-embed-amd64");
    },
    runScript(scriptName, context) {
      scriptCalls.push({ scriptName, context });
    },
    collectReleaseArtifacts(context) {
      collectedCalls.push(context);
      return { outputDir: "D:/repo/apps/local-web/desktop/.release-output/0.1.0", version: "0.1.0" };
    },
  });

  assert.deepEqual(
    scriptCalls.map(({ scriptName }) => scriptName),
    ["doctor", "test:prepare-release", "test:portable", "build"],
  );
  assert.deepEqual(
    scriptCalls.map(({ context }) => context),
    [
      { desktopRoot: "D:/repo/apps/local-web/desktop", env },
      { desktopRoot: "D:/repo/apps/local-web/desktop", env },
      { desktopRoot: "D:/repo/apps/local-web/desktop", env },
      { desktopRoot: "D:/repo/apps/local-web/desktop", env },
    ],
  );
  assert.deepEqual(collectedCalls, [{ desktopRoot: "D:/repo/apps/local-web/desktop" }]);
  assert.equal(result.outputDir, "D:/repo/apps/local-web/desktop/.release-output/0.1.0");
});

test("releaseLocal stops immediately when embedded python validation fails", () => {
  const failure = new Error("bad embedded python");
  const scriptCalls = [];
  let collected = false;

  assert.throws(
    () =>
      releaseLocal({
        desktopRoot: "D:/repo/apps/local-web/desktop",
        env: { LMCA_EMBEDDED_PYTHON_ROOT: "D:/runtime/bad-python" },
        validateEmbeddedPythonRoot() {
          throw failure;
        },
        runScript(scriptName) {
          scriptCalls.push(scriptName);
        },
        collectReleaseArtifacts() {
          collected = true;
        },
      }),
    failure,
  );

  assert.deepEqual(scriptCalls, []);
  assert.equal(collected, false);
});

test("releaseLocal stops immediately when a script fails and does not collect artifacts", () => {
  const failure = new Error("portable failed");
  const scriptCalls = [];
  let collected = false;

  assert.throws(
    () =>
      releaseLocal({
        desktopRoot: "D:/repo/apps/local-web/desktop",
        env: { LMCA_EMBEDDED_PYTHON_ROOT: "D:/runtime/python-3.11.9-embed-amd64" },
        validateEmbeddedPythonRoot() {},
        runScript(scriptName) {
          scriptCalls.push(scriptName);
          if (scriptName === "test:portable") {
            throw failure;
          }
        },
        collectReleaseArtifacts() {
          collected = true;
        },
      }),
    failure,
  );

  assert.deepEqual(scriptCalls, ["doctor", "test:prepare-release", "test:portable"]);
  assert.equal(collected, false);
});
