/**
 * Input: backend ???? LMCA_EMBEDDED_PYTHON_ROOT ??  |  Output: .release-staging/runtime ? runtime-manifest
 * Output: ?????????????? Python?????? runtime staging ??
 * Role: ???? release ??????? runtime ????
 * Use: ?????????? python.exe ?????????? exe ??????? staging ??
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

const DEFAULT_RESOURCE_LAYOUT_VERSION = "desktop-runtime-v1";
const BACKEND_ALLOWED_DIRECTORIES = ["app", "alembic"];
const BACKEND_ALLOWED_ROOT_FILES = ["pyproject.toml", "alembic.ini", "environment.yml"];
const SKIPPED_DIRECTORY_NAMES = new Set(["__pycache__", ".pytest_cache", ".pytest-temp"]);
const SKIPPED_FILE_EXTENSIONS = new Set([".pyc", ".pyo"]);
const WINDOWS_RUNTIME_MARKER_PATTERNS = [
  /^python\d{2,3}\.dll$/i,
  /^python\d{2,3}\.zip$/i,
  /^vcruntime[\w-]*\.dll$/i,
];

function embeddedPythonRootError() {
  return new Error(
    "LMCA_EMBEDDED_PYTHON_ROOT must point to an existing embedded Python directory containing python.exe and at least one runtime marker (pythonXY.dll, pythonXY.zip, vcruntime*.dll, or Lib/).",
  );
}

function toPosixPath(targetPath) {
  return targetPath.split(path.sep).join("/");
}

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
      if (SKIPPED_DIRECTORY_NAMES.has(entry.name)) {
        continue;
      }
      copyDirectoryContents(sourcePath, destinationPath);
      continue;
    }

    if (entry.isFile()) {
      if (SKIPPED_FILE_EXTENSIONS.has(path.extname(entry.name))) {
        continue;
      }
      ensureDirectory(path.dirname(destinationPath));
      fs.copyFileSync(sourcePath, destinationPath);
    }
  }
}

function listRuntimeMarkers(embeddedPythonRoot) {
  const markers = [];
  for (const entry of fs.readdirSync(embeddedPythonRoot, { withFileTypes: true })) {
    if (entry.isDirectory() && entry.name === "Lib") {
      markers.push("Lib");
      continue;
    }

    if (entry.isFile() && WINDOWS_RUNTIME_MARKER_PATTERNS.some((pattern) => pattern.test(entry.name))) {
      markers.push(entry.name);
    }
  }

  return markers;
}

export function collectBackendPaths({ backendRoot }) {
  const collectedPaths = [];

  function walk(currentRoot, relativeRoot) {
    for (const entry of fs.readdirSync(currentRoot, { withFileTypes: true })) {
      const relativePath = path.join(relativeRoot, entry.name);
      const absolutePath = path.join(currentRoot, entry.name);

      if (entry.isDirectory()) {
        if (SKIPPED_DIRECTORY_NAMES.has(entry.name)) {
          continue;
        }
        walk(absolutePath, relativePath);
        continue;
      }

      if (!entry.isFile()) {
        continue;
      }

      if (SKIPPED_FILE_EXTENSIONS.has(path.extname(entry.name))) {
        continue;
      }

      collectedPaths.push(toPosixPath(relativePath));
    }
  }

  for (const directoryName of BACKEND_ALLOWED_DIRECTORIES) {
    const directoryPath = path.join(backendRoot, directoryName);
    if (fs.existsSync(directoryPath) && fs.statSync(directoryPath).isDirectory()) {
      walk(directoryPath, directoryName);
    }
  }

  for (const fileName of BACKEND_ALLOWED_ROOT_FILES) {
    const filePath = path.join(backendRoot, fileName);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      collectedPaths.push(fileName);
    }
  }

  return collectedPaths.sort();
}

export function buildRuntimeManifest({
  appVersion,
  backendVersion,
  pythonVersion,
  releaseChannelUrl,
  resourceLayoutVersion,
  generatedAt,
}) {
  return {
    appVersion,
    backendVersion,
    pythonVersion,
    releaseChannelUrl,
    resourceLayoutVersion,
    generatedAt,
  };
}

export function stageRuntimeAssets({
  stagingRoot,
  backendRoot,
  backendPaths,
  pluginsRoot,
  embeddedPythonRoot,
  runtimeManifest,
}) {
  const runtimeRoot = path.join(stagingRoot, "runtime");
  fs.rmSync(runtimeRoot, { recursive: true, force: true });
  ensureDirectory(runtimeRoot);
  const runtimeBackendRoot = ensureDirectory(path.join(runtimeRoot, "backend"));
  const runtimePluginsRoot = ensureDirectory(path.join(runtimeRoot, "plugins"));
  const runtimePythonRoot = ensureDirectory(path.join(runtimeRoot, "python"));

  for (const backendPath of backendPaths) {
    const sourcePath = path.join(backendRoot, backendPath);
    const destinationPath = path.join(runtimeBackendRoot, backendPath);
    ensureDirectory(path.dirname(destinationPath));
    fs.copyFileSync(sourcePath, destinationPath);
  }

  if (pluginsRoot && fs.existsSync(pluginsRoot) && fs.statSync(pluginsRoot).isDirectory()) {
    copyDirectoryContents(pluginsRoot, runtimePluginsRoot);
  }

  copyDirectoryContents(embeddedPythonRoot, runtimePythonRoot);
  fs.writeFileSync(path.join(runtimeRoot, "runtime-manifest.json"), `${JSON.stringify(runtimeManifest, null, 2)}\n`);

  return runtimeRoot;
}

export function validateEmbeddedPythonRoot(embeddedPythonRoot) {
  if (!embeddedPythonRoot) {
    throw embeddedPythonRootError();
  }

  let stats;
  try {
    stats = fs.statSync(embeddedPythonRoot);
  } catch {
    throw embeddedPythonRootError();
  }

  if (!stats.isDirectory()) {
    throw embeddedPythonRootError();
  }

  const pythonExecutablePath = path.join(embeddedPythonRoot, "python.exe");
  if (!fs.existsSync(pythonExecutablePath) || !fs.statSync(pythonExecutablePath).isFile()) {
    throw embeddedPythonRootError();
  }

  if (listRuntimeMarkers(embeddedPythonRoot).length === 0) {
    throw embeddedPythonRootError();
  }

  return embeddedPythonRoot;
}

export function readJsonFile(targetPath) {
  return JSON.parse(fs.readFileSync(targetPath, "utf8"));
}

export function readPyprojectVersion(pyprojectPath) {
  const contents = fs.readFileSync(pyprojectPath, "utf8");
  const versionMatch = contents.match(/^\s*version\s*=\s*["']([^"']+)["']/m);
  if (!versionMatch) {
    throw new Error(`Could not find project version in ${pyprojectPath}`);
  }

  return versionMatch[1];
}

export function prepareRelease({
  desktopRoot,
  embeddedPythonRoot,
  releaseChannelUrl = "",
  resourceLayoutVersion = DEFAULT_RESOURCE_LAYOUT_VERSION,
  generatedAt = new Date().toISOString(),
}) {
  const backendRoot = path.resolve(desktopRoot, "..", "backend");
  const pluginsRoot = path.resolve(desktopRoot, "..", "plugins");
  const stagingRoot = path.join(desktopRoot, ".release-staging");
  const packageJson = readJsonFile(path.join(desktopRoot, "package.json"));
  const backendVersion = readPyprojectVersion(path.join(backendRoot, "pyproject.toml"));
  const pythonVersion = path.basename(embeddedPythonRoot);
  const backendPaths = collectBackendPaths({ backendRoot });
  const runtimeManifest = buildRuntimeManifest({
    appVersion: packageJson.version,
    backendVersion,
    pythonVersion,
    releaseChannelUrl,
    resourceLayoutVersion,
    generatedAt,
  });

  const runtimeRoot = stageRuntimeAssets({
    stagingRoot,
    backendRoot,
    backendPaths,
    pluginsRoot,
    embeddedPythonRoot,
    runtimeManifest,
  });

  return {
    runtimeRoot,
    runtimeManifest,
    backendPaths,
    stagingRoot,
  };
}

function run() {
  const desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..");
  const embeddedPythonRoot = validateEmbeddedPythonRoot(process.env.LMCA_EMBEDDED_PYTHON_ROOT || "");

  const result = prepareRelease({
    desktopRoot,
    embeddedPythonRoot,
    releaseChannelUrl: process.env.LMCA_RELEASE_CHANNEL_URL || "",
  });

  console.log(`Prepared runtime staging at ${result.runtimeRoot}`);
  console.log(`Collected ${result.backendPaths.length} backend files.`);
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  run();
}
