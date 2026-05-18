/**
 * run-rust.mjs - Rust 开发服务器启动脚本
 *
 * 职责: 在开发模式下启动 Tauri Rust 进程
 * 输入: 命令行参数
 * 输出: 子进程
 * 位置: 桌面端构建脚本
 * 关联: run-tauri.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import {
  buildDesktopEnv,
  detectCargoCandidates,
} from "./run-tauri.mjs";

export function ensureTauriResourcePlaceholders({ desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..") } = {}) {
  const runtimeRoot = path.join(desktopRoot, ".release-staging", "runtime");
  for (const directoryName of ["backend", "plugins", "python"]) {
    const directoryPath = path.join(runtimeRoot, directoryName);
    fs.mkdirSync(directoryPath, { recursive: true });
    const keepPath = path.join(directoryPath, ".keep");
    if (!fs.existsSync(keepPath) && fs.readdirSync(directoryPath).length === 0) {
      fs.writeFileSync(keepPath, "");
    }
  }
  const manifestPath = path.join(runtimeRoot, "runtime-manifest.json");
  if (!fs.existsSync(manifestPath)) {
    fs.writeFileSync(
      manifestPath,
      `${JSON.stringify({ resourceLayoutVersion: "desktop-runtime-dev-placeholder" }, null, 2)}\n`,
    );
  }
}

function run() {
  const rustArgs = process.argv.slice(2);
  if (rustArgs.length === 0) {
    console.error("Usage: node scripts/run-rust.mjs <cargo args...>");
    process.exit(1);
  }

  const env = buildDesktopEnv({
    baseEnv: process.env,
    backendPython: process.env.LMCA_BACKEND_PYTHON || "",
    configuredCargoCommand: process.env.LMCA_CARGO_BIN || "",
    cargoCandidates: detectCargoCandidates(),
  });

  ensureTauriResourcePlaceholders();

  const result = spawnSync("cargo", rustArgs, {
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
