import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildRuntimeManifest,
  collectBackendPaths,
  validateEmbeddedPythonRoot,
  stageRuntimeAssets,
} from "./prepare-release.mjs";

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "lmca-prepare-release-"));
}

function writeFile(root, relativePath, contents = "") {
  const targetPath = path.join(root, relativePath);
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.writeFileSync(targetPath, contents);
}

test("collectBackendPaths keeps only explicit runtime roots and files", () => {
  const backendRoot = makeTempDir();
  writeFile(backendRoot, "app/main.py", "print('ok')");
  writeFile(backendRoot, "app/core/config.py", "value = 1");
  writeFile(backendRoot, "alembic/env.py", "# env");
  writeFile(backendRoot, "alembic/versions/0001_initial.py", "# migration");
  writeFile(backendRoot, "pyproject.toml", "[project]\nversion = '0.1.0'\n");
  writeFile(backendRoot, "alembic.ini", "[alembic]\n");
  writeFile(backendRoot, "environment.yml", "name: backend\n");
  writeFile(backendRoot, "tests/test_system_api.py", "assert True");
  writeFile(backendRoot, ".pytest_cache/state.json", "{}");
  writeFile(backendRoot, ".pytest-temp/log.txt", "tmp");
  writeFile(backendRoot, ".venv/Scripts/python.exe", "bin");
  writeFile(backendRoot, "app/__pycache__/main.cpython-311.pyc", "pyc");
  writeFile(backendRoot, "app/core/generated.pyc", "pyc");
  writeFile(backendRoot, "migration_smoke.db", "db");
  writeFile(backendRoot, ".env", "SECRET=local");
  writeFile(backendRoot, "pyproject.toml.bak", "oops");
  writeFile(backendRoot, "notes.dump", "scratch");
  writeFile(backendRoot, "exports/latest.json", "{}");

  const collected = collectBackendPaths({ backendRoot });

  assert.deepEqual(collected, [
    "alembic.ini",
    "alembic/env.py",
    "alembic/versions/0001_initial.py",
    "app/core/config.py",
    "app/main.py",
    "environment.yml",
    "pyproject.toml",
  ]);
});

test("buildRuntimeManifest returns the required release metadata", () => {
  const manifest = buildRuntimeManifest({
    appVersion: "0.2.0",
    backendVersion: "0.3.0",
    pythonVersion: "3.11.9",
    releaseChannelUrl: "https://updates.example.test/stable.json",
    resourceLayoutVersion: "desktop-runtime-v1",
    generatedAt: "2026-04-23T12:00:00.000Z",
  });

  assert.deepEqual(manifest, {
    appVersion: "0.2.0",
    backendVersion: "0.3.0",
    pythonVersion: "3.11.9",
    releaseChannelUrl: "https://updates.example.test/stable.json",
    resourceLayoutVersion: "desktop-runtime-v1",
    generatedAt: "2026-04-23T12:00:00.000Z",
  });
});

test("stageRuntimeAssets creates the runtime layout and writes the manifest", () => {
  const backendRoot = makeTempDir();
  const pluginsRoot = makeTempDir();
  const pythonRoot = makeTempDir();
  const stagingRoot = makeTempDir();

  writeFile(backendRoot, "app/main.py", "print('ok')");
  writeFile(backendRoot, "pyproject.toml", "[project]\nversion='0.1.0'\n");
  writeFile(pluginsRoot, "rag-core/plugin.json", '{"id":"rag-core"}');
  writeFile(pluginsRoot, "rag-core/runtime/app/main.py", "print('plugin')");
  writeFile(pluginsRoot, "rag-core/runtime/app/__pycache__/main.pyc", "pyc");
  writeFile(pythonRoot, "python.exe", "binary");
  writeFile(pythonRoot, "Lib/os.py", "# stdlib");

  const runtimeManifest = buildRuntimeManifest({
    appVersion: "0.1.0",
    backendVersion: "0.1.0",
    pythonVersion: "3.11.9",
    releaseChannelUrl: "https://updates.example.test/stable.json",
    resourceLayoutVersion: "desktop-runtime-v1",
    generatedAt: "2026-04-23T12:00:00.000Z",
  });

  const runtimeRoot = stageRuntimeAssets({
    stagingRoot,
    backendRoot,
    backendPaths: ["app/main.py", "pyproject.toml"],
    pluginsRoot,
    embeddedPythonRoot: pythonRoot,
    runtimeManifest,
  });

  assert.equal(runtimeRoot, path.join(stagingRoot, "runtime"));
  assert.equal(fs.existsSync(path.join(runtimeRoot, "backend", "app", "main.py")), true);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "backend", "pyproject.toml")), true);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "plugins", "rag-core", "plugin.json")), true);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "plugins", "rag-core", "runtime", "app", "main.py")), true);
  assert.equal(
    fs.existsSync(path.join(runtimeRoot, "plugins", "rag-core", "runtime", "app", "__pycache__", "main.pyc")),
    false,
  );
  assert.equal(fs.existsSync(path.join(runtimeRoot, "python", "python.exe")), true);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "python", "Lib", "os.py")), true);

  const manifestPath = path.join(runtimeRoot, "runtime-manifest.json");
  assert.equal(fs.existsSync(manifestPath), true);
  assert.deepEqual(JSON.parse(fs.readFileSync(manifestPath, "utf8")), runtimeManifest);
});

test("stageRuntimeAssets removes stale files before restaging", () => {
  const backendRoot = makeTempDir();
  const pythonRootA = makeTempDir();
  const pythonRootB = makeTempDir();
  const stagingRoot = makeTempDir();

  writeFile(backendRoot, "app/main.py", "print('ok')");
  writeFile(backendRoot, "pyproject.toml", "[project]\nversion='0.1.0'\n");
  writeFile(backendRoot, "app/obsolete.py", "old");
  writeFile(pythonRootA, "python.exe", "binary-a");
  writeFile(pythonRootA, "Lib/old.py", "# old");
  writeFile(pythonRootB, "python.exe", "binary-b");
  writeFile(pythonRootB, "Lib/new.py", "# new");

  const runtimeManifest = buildRuntimeManifest({
    appVersion: "0.1.0",
    backendVersion: "0.1.0",
    pythonVersion: "3.11.9",
    releaseChannelUrl: "https://updates.example.test/stable.json",
    resourceLayoutVersion: "desktop-runtime-v1",
    generatedAt: "2026-04-23T12:00:00.000Z",
  });

  stageRuntimeAssets({
    stagingRoot,
    backendRoot,
    backendPaths: ["app/main.py", "app/obsolete.py", "pyproject.toml"],
    embeddedPythonRoot: pythonRootA,
    runtimeManifest,
  });

  const runtimeRoot = stageRuntimeAssets({
    stagingRoot,
    backendRoot,
    backendPaths: ["app/main.py", "pyproject.toml"],
    embeddedPythonRoot: pythonRootB,
    runtimeManifest,
  });

  assert.equal(fs.existsSync(path.join(runtimeRoot, "backend", "app", "obsolete.py")), false);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "python", "Lib", "old.py")), false);
  assert.equal(fs.existsSync(path.join(runtimeRoot, "python", "Lib", "new.py")), true);
});

test("validateEmbeddedPythonRoot rejects empty, missing, and file paths", () => {
  const missingPath = path.join(makeTempDir(), "missing-python");
  const fileRoot = makeTempDir();
  const validRoot = makeTempDir();
  writeFile(validRoot, "python.exe", "binary");
  writeFile(validRoot, "python311.zip", "stdlib");

  assert.throws(
    () => validateEmbeddedPythonRoot(""),
    /LMCA_EMBEDDED_PYTHON_ROOT must point to an existing embedded Python directory/i,
  );
  assert.throws(
    () => validateEmbeddedPythonRoot(missingPath),
    /LMCA_EMBEDDED_PYTHON_ROOT must point to an existing embedded Python directory/i,
  );
  assert.throws(
    () => validateEmbeddedPythonRoot(path.join(fileRoot, "python.exe")),
    /LMCA_EMBEDDED_PYTHON_ROOT must point to an existing embedded Python directory/i,
  );
  assert.equal(validateEmbeddedPythonRoot(validRoot), validRoot);
});

test("validateEmbeddedPythonRoot rejects directories without python.exe", () => {
  const pythonRoot = makeTempDir();
  writeFile(pythonRoot, "python311.dll", "runtime");

  assert.throws(
    () => validateEmbeddedPythonRoot(pythonRoot),
    /LMCA_EMBEDDED_PYTHON_ROOT.*python\.exe.*runtime marker/i,
  );
});

test("validateEmbeddedPythonRoot rejects directories that do not look like embedded Python", () => {
  const pythonRoot = makeTempDir();
  writeFile(pythonRoot, "python.exe", "binary");
  writeFile(pythonRoot, "README.txt", "hello");
  writeFile(pythonRoot, "Scripts/pip.exe", "tool");

  assert.throws(
    () => validateEmbeddedPythonRoot(pythonRoot),
    /LMCA_EMBEDDED_PYTHON_ROOT.*python\.exe.*runtime marker/i,
  );
});

test("validateEmbeddedPythonRoot accepts python.exe with embedded runtime markers", () => {
  const dllRoot = makeTempDir();
  writeFile(dllRoot, "python.exe", "binary");
  writeFile(dllRoot, "python311.dll", "runtime");

  const vcruntimeRoot = makeTempDir();
  writeFile(vcruntimeRoot, "python.exe", "binary");
  writeFile(vcruntimeRoot, "vcruntime140_1.dll", "runtime");

  const libRoot = makeTempDir();
  writeFile(libRoot, "python.exe", "binary");
  writeFile(libRoot, "Lib/os.py", "# stdlib");

  assert.equal(validateEmbeddedPythonRoot(dllRoot), dllRoot);
  assert.equal(validateEmbeddedPythonRoot(vcruntimeRoot), vcruntimeRoot);
  assert.equal(validateEmbeddedPythonRoot(libRoot), libRoot);
});
