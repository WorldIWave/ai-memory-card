/**
 * run-tauri.mjs - Tauri 应用启动脚本
 *
 * 职责: 协调前端和 Rust 进程，启动完整的桌面开发环境
 * 输入: 命令行参数
 * 输出: 子进程组
 * 位置: 桌面端构建脚本
 * 关联: run-rust.mjs, doctor.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

export function pickBackendPythonForDesktop({
  configuredBackendPython,
  backendPythonCandidates,
}) {
  return configuredBackendPython || backendPythonCandidates.find(Boolean) || "";
}

export function detectBackendPythonCandidates(desktopRoot) {
  const repoRoot = path.resolve(desktopRoot, "..", "..", "..");
  return [
    path.join("D:", "condaa", "envs", "ai-memory-card-backend", "python.exe"),
    path.join(repoRoot, "apps", "local-web", "backend", ".venv", "Scripts", "python.exe"),
  ].filter((candidate) => fs.existsSync(candidate));
}

export function detectCargoCandidates() {
  return [path.join(process.env.USERPROFILE || "", ".cargo", "bin", "cargo.exe")].filter((candidate) =>
    candidate && fs.existsSync(candidate),
  );
}

export function resolveCargoBinDirectory({
  configuredCargoCommand,
  cargoCandidates,
}) {
  const cargoCommand = configuredCargoCommand || cargoCandidates.find(Boolean) || "";
  return cargoCommand ? path.dirname(cargoCommand) : "";
}

export function buildDesktopEnv({
  baseEnv,
  backendPython,
  configuredCargoCommand,
  cargoCandidates,
  pathDelimiter = path.delimiter,
}) {
  const env = { ...baseEnv };
  if (backendPython) {
    env.LMCA_BACKEND_PYTHON = backendPython;
  }

  const cargoBinDirectory = resolveCargoBinDirectory({
    configuredCargoCommand,
    cargoCandidates,
  });
  if (cargoBinDirectory) {
    const currentPath = env.PATH || env.Path || "";
    const segments = currentPath ? currentPath.split(pathDelimiter) : [];
    if (!segments.includes(cargoBinDirectory)) {
      env.PATH = currentPath ? `${cargoBinDirectory}${pathDelimiter}${currentPath}` : cargoBinDirectory;
    }
  }

  return env;
}

function run() {
  const desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..");
  const tauriScript = process.argv[2];

  if (!tauriScript) {
    console.error("Usage: node scripts/run-tauri.mjs <dev:tauri|build:tauri>");
    process.exit(1);
  }

  const configuredBackendPython = process.env.LMCA_BACKEND_PYTHON || "";
  const configuredCargoCommand = process.env.LMCA_CARGO_BIN || "";
  const backendPythonCandidates = detectBackendPythonCandidates(desktopRoot);
  const cargoCandidates = detectCargoCandidates();
  const backendPython = pickBackendPythonForDesktop({
    configuredBackendPython,
    backendPythonCandidates,
  });

  const env = buildDesktopEnv({
    baseEnv: process.env,
    backendPython,
    configuredCargoCommand,
    cargoCandidates,
  });

  const result =
    process.platform === "win32"
      ? spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", `npm.cmd run ${tauriScript}`], {
          cwd: desktopRoot,
          env,
          stdio: "inherit",
        })
      : spawnSync("npm", ["run", tauriScript], {
          cwd: desktopRoot,
          env,
          stdio: "inherit",
        });

  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }

  process.exit(result.status ?? 1);
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  run();
}
