/**
 * Input: Tauri release ???? .release-staging/runtime ??  |  Output: .release-staging/app ? portable ZIP
 * Output: ??????????????????????? ZIP
 * Role: ?? Windows ???????????
 * Use: runtime ?????? tauri.conf ? runtime_layout ??????
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const PORTABLE_ZIP_NAME = "AIMemoryCard-portable.zip";
const DEFAULT_EXECUTABLE_NAME = "AI Memory Card.exe";
const RUNTIME_RESOURCE_NAMES = Object.freeze(["backend", "plugins", "python", "runtime-manifest.json"]);

export const TAURI_BUNDLE_RESOURCE_MAP = Object.freeze({
  "../.release-staging/runtime/backend": "backend",
  "../.release-staging/runtime/plugins": "plugins",
  "../.release-staging/runtime/python": "python",
  "../.release-staging/runtime/runtime-manifest.json": "runtime-manifest.json",
});

function ensureDirectory(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
  return targetPath;
}

function copyDirectoryContents(sourceRoot, destinationRoot) {
  ensureDirectory(destinationRoot);
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    const sourcePath = path.join(sourceRoot, entry.name);
    const destinationPath = path.join(destinationRoot, entry.name);

    if (entry.isDirectory()) {
      copyDirectoryContents(sourcePath, destinationPath);
      continue;
    }

    if (entry.isFile()) {
      ensureDirectory(path.dirname(destinationPath));
      fs.copyFileSync(sourcePath, destinationPath);
    }
  }
}

function copyRuntimeResourceEntry(sourcePath, destinationPath) {
  const sourceStats = fs.statSync(sourcePath);
  if (sourceStats.isDirectory()) {
    copyDirectoryContents(sourcePath, destinationPath);
    return;
  }

  ensureDirectory(path.dirname(destinationPath));
  fs.copyFileSync(sourcePath, destinationPath);
}

function quoteForPowerShell(value) {
  return `'${value.replaceAll("'", "''")}'`;
}

function normalizeExecutableBaseName(name) {
  const candidate = typeof name === "string" && name ? name : DEFAULT_EXECUTABLE_NAME;
  return candidate.replace(/(\.exe)+$/i, "");
}

export function buildPortableLayout(desktopRoot) {
  const stagingRoot = path.join(desktopRoot, ".release-staging");

  return {
    stagingRoot,
    runtimeDir: path.join(stagingRoot, "runtime"),
    appDir: path.join(stagingRoot, "app"),
    zipPath: path.join(stagingRoot, PORTABLE_ZIP_NAME),
  };
}

export function buildZipCommand({ appDir, zipPath }) {
  const archiveSource = path.win32.join(appDir, "*");
  const archiveDestination = path.win32.normalize(zipPath);

  return {
    executable: "powershell.exe",
    args: [
      "-NoProfile",
      "-Command",
      `Compress-Archive -Path ${quoteForPowerShell(archiveSource)} -DestinationPath ${quoteForPowerShell(archiveDestination)} -Force`,
    ],
  };
}

export function assemblePortableAppDirectory({
  binaryPath,
  layout,
  executableName = DEFAULT_EXECUTABLE_NAME,
}) {
  if (!fs.existsSync(binaryPath) || !fs.statSync(binaryPath).isFile()) {
    throw new Error(`Expected Tauri release binary was not found at ${binaryPath}`);
  }

  if (!fs.existsSync(layout.runtimeDir) || !fs.statSync(layout.runtimeDir).isDirectory()) {
    throw new Error(`Expected staged runtime directory was not found at ${layout.runtimeDir}`);
  }

  fs.rmSync(layout.appDir, { recursive: true, force: true });
  ensureDirectory(layout.appDir);

  const executablePath = path.join(layout.appDir, executableName);
  fs.copyFileSync(binaryPath, executablePath);

  for (const resourceName of RUNTIME_RESOURCE_NAMES) {
    const sourcePath = path.join(layout.runtimeDir, resourceName);
    if (!fs.existsSync(sourcePath)) {
      throw new Error(`Expected staged runtime resource was not found at ${sourcePath}`);
    }

    copyRuntimeResourceEntry(sourcePath, path.join(layout.appDir, resourceName));
  }

  return {
    appDir: layout.appDir,
    executablePath,
  };
}

export function readJsonFile(targetPath) {
  return JSON.parse(fs.readFileSync(targetPath, "utf8"));
}

export function readCargoPackageName(cargoTomlPath) {
  const contents = fs.readFileSync(cargoTomlPath, "utf8");
  const packageNameMatch = contents.match(/^\s*name\s*=\s*"([^"]+)"/m);
  if (!packageNameMatch) {
    throw new Error(`Could not find package name in ${cargoTomlPath}`);
  }

  return packageNameMatch[1];
}

export function resolveTauriReleaseBinaryPath({
  desktopRoot,
  cargoPackageName,
  productName,
  platform = process.platform,
}) {
  const releaseDir = path.join(desktopRoot, "src-tauri", "target", "release");

  if (platform !== "win32") {
    return path.join(releaseDir, cargoPackageName);
  }

  const candidateFileNames = [
    `${normalizeExecutableBaseName(productName || cargoPackageName)}.exe`,
    `${normalizeExecutableBaseName(cargoPackageName)}.exe`,
  ];

  for (const executableFileName of candidateFileNames) {
    const candidatePath = path.join(releaseDir, executableFileName);
    if (fs.existsSync(candidatePath)) {
      return candidatePath;
    }
  }

  return path.join(releaseDir, candidateFileNames[0]);
}

export function runZipCommand(command, { cwd, stdio = "inherit", spawn = spawnSync } = {}) {
  return spawn(command.executable, command.args, {
    cwd,
    stdio,
  });
}

export function packagePortable({
  desktopRoot,
  productName = DEFAULT_EXECUTABLE_NAME.replace(/\.exe$/i, ""),
  platform = process.platform,
  runZipCommand: executeZipCommand = runZipCommand,
}) {
  const layout = buildPortableLayout(desktopRoot);
  const cargoPackageName = readCargoPackageName(path.join(desktopRoot, "src-tauri", "Cargo.toml"));
  const binaryPath = resolveTauriReleaseBinaryPath({
    desktopRoot,
    cargoPackageName,
    productName,
    platform,
  });
  const executableName = `${normalizeExecutableBaseName(productName)}.exe`;
  const assembledLayout = assemblePortableAppDirectory({
    binaryPath,
    layout,
    executableName,
  });

  fs.rmSync(layout.zipPath, { force: true });
  const zipCommand = buildZipCommand({
    appDir: assembledLayout.appDir,
    zipPath: layout.zipPath,
  });
  const result = executeZipCommand(zipCommand, {
    cwd: desktopRoot,
    stdio: "inherit",
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    throw new Error(`Portable ZIP packaging failed with exit code ${result.status ?? 1}`);
  }

  return {
    ...assembledLayout,
    binaryPath,
    zipPath: layout.zipPath,
  };
}

function run() {
  const desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..");
  const tauriConfig = readJsonFile(path.join(desktopRoot, "src-tauri", "tauri.conf.json"));
  const productName = tauriConfig?.package?.productName || tauriConfig?.tauri?.bundle?.productName || "AI Memory Card";
  const result = packagePortable({
    desktopRoot,
    productName,
  });

  console.log(`Portable app staged at ${result.appDir}`);
  console.log(`Portable ZIP written to ${result.zipPath}`);
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  run();
}
