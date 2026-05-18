/**
 * Input: release ?????doctor/test/build ??? staging ??  |  Output: .release-output/<version>/ ??????
 * Output: ????????Tauri ????????????????????
 * Role: ?? Windows ???? ritual ?? orchestrator
 * Use: ??????????????? prepare-release ????? npm ?????
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { validateEmbeddedPythonRoot } from "./prepare-release.mjs";

function ensureDirectory(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
  return targetPath;
}

export function readJsonFile(targetPath) {
  return JSON.parse(fs.readFileSync(targetPath, "utf8"));
}

export function buildReleaseAssetNames(version) {
  return {
    msi: `AIMemoryCard-${version}-x64-setup.msi`,
    zip: `AIMemoryCard-${version}-x64-portable.zip`,
    manifest: `AIMemoryCard-${version}-runtime-manifest.json`,
    checksums: `AIMemoryCard-${version}-SHA256SUMS.txt`,
  };
}

export function buildReleaseOutputLayout(desktopRoot, version) {
  const outputDir = path.join(desktopRoot, ".release-output", version);

  return {
    version,
    outputDir,
    msiSourceDir: path.join(desktopRoot, "src-tauri", "target", "release", "bundle", "msi"),
    portableZipPath: path.join(desktopRoot, ".release-staging", "AIMemoryCard-portable.zip"),
    runtimeManifestPath: path.join(desktopRoot, ".release-staging", "runtime", "runtime-manifest.json"),
  };
}

function requireFile(filePath, description) {
  let stats;
  try {
    stats = fs.statSync(filePath);
  } catch {
    throw new Error(`Expected ${description} was not found at ${filePath}.`);
  }

  if (!stats.isFile()) {
    throw new Error(`Expected ${description} was not found at ${filePath}.`);
  }

  return filePath;
}

function findSingleMsiFile(msiSourceDir) {
  const msiCandidates = fs
    .readdirSync(msiSourceDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".msi"));

  if (msiCandidates.length !== 1) {
    throw new Error(`Expected exactly one MSI artifact in ${msiSourceDir}, found ${msiCandidates.length}.`);
  }

  return path.join(msiSourceDir, msiCandidates[0].name);
}

function sha256File(filePath) {
  return createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function writeChecksumFile(outputDir, checksumFileName, fileNames) {
  const contents = fileNames
    .map((fileName) => `${sha256File(path.join(outputDir, fileName))}  ${fileName}`)
    .join("\n");

  fs.writeFileSync(path.join(outputDir, checksumFileName), `${contents}\n`);
}

export function collectReleaseArtifacts({ desktopRoot }) {
  const version = readJsonFile(path.join(desktopRoot, "package.json")).version;
  const assetNames = buildReleaseAssetNames(version);
  const layout = buildReleaseOutputLayout(desktopRoot, version);
  const msiSourcePath = findSingleMsiFile(layout.msiSourceDir);
  const portableZipPath = requireFile(layout.portableZipPath, "portable ZIP artifact");
  const runtimeManifestPath = requireFile(layout.runtimeManifestPath, "runtime manifest");

  fs.rmSync(layout.outputDir, { recursive: true, force: true });
  ensureDirectory(layout.outputDir);

  fs.copyFileSync(msiSourcePath, path.join(layout.outputDir, assetNames.msi));
  fs.copyFileSync(portableZipPath, path.join(layout.outputDir, assetNames.zip));
  fs.copyFileSync(runtimeManifestPath, path.join(layout.outputDir, assetNames.manifest));
  writeChecksumFile(layout.outputDir, assetNames.checksums, [assetNames.msi, assetNames.zip, assetNames.manifest]);

  return {
    outputDir: layout.outputDir,
    version,
    assetNames,
  };
}

export function runScript(scriptName, { desktopRoot, env = process.env, spawn = spawnSync, platform = process.platform } = {}) {
  const mergedEnv = { ...process.env, ...env };
  const result =
    platform === "win32"
      ? spawn(mergedEnv.ComSpec || "cmd.exe", ["/d", "/s", "/c", `npm.cmd run ${scriptName}`], {
          cwd: desktopRoot,
          stdio: "inherit",
          env: mergedEnv,
        })
      : spawn("npm", ["run", scriptName], {
          cwd: desktopRoot,
          stdio: "inherit",
          env: mergedEnv,
        });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    throw new Error(`npm run ${scriptName} failed with exit code ${result.status ?? 1}`);
  }
}

export function releaseLocal({
  desktopRoot,
  env = process.env,
  validateEmbeddedPythonRoot: validatePythonRoot = validateEmbeddedPythonRoot,
  runScript: executeScript = runScript,
  collectReleaseArtifacts: collectArtifacts = collectReleaseArtifacts,
} = {}) {
  validatePythonRoot(env.LMCA_EMBEDDED_PYTHON_ROOT || "");
  executeScript("doctor", { desktopRoot, env });
  executeScript("test:prepare-release", { desktopRoot, env });
  executeScript("test:portable", { desktopRoot, env });
  executeScript("build", { desktopRoot, env });
  return collectArtifacts({ desktopRoot });
}

export function run() {
  const desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..");
  const result = releaseLocal({ desktopRoot });
  console.log(`Release output prepared at ${result.outputDir}`);
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  run();
}
