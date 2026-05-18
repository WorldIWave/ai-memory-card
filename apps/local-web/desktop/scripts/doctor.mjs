/**
 * doctor.mjs - 环境检查工具
 *
 * 职责: 检查桌面端构建所需的依赖和环境是否满足
 * 输入: 无
 * 输出: 检查结果报告
 * 位置: 桌面端构建脚本
 * 关联: run-tauri.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

export function checkTool({ name, command, args = [], required = true }) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
  });

  if (result.error) {
    return {
      name,
      ok: false,
      required,
      detail: result.error.message,
    };
  }

  if (result.status === 0) {
    const detail = `${result.stdout || result.stderr}`.trim() || "available";
    return { name, ok: true, required, detail };
  }

  const stderr = `${result.stderr || result.stdout}`.trim();
  return {
    name,
    ok: false,
    required,
    detail: stderr || "not installed or not available on PATH",
  };
}

export function checkPathExists({ name, path: targetPath, required = true }) {
  const exists = fs.existsSync(targetPath);
  return {
    name,
    ok: exists,
    required,
    detail: exists ? targetPath : `missing: ${targetPath}`,
  };
}

export function checkPythonModule({
  name,
  moduleName,
  pythonCommand,
  importCommand = `import ${moduleName}; print(${JSON.stringify(moduleName)})`,
  required = true,
}) {
  return checkTool({
    name,
    command: pythonCommand,
    args: ["-c", importCommand],
    required,
  });
}

export function resolveEffectiveBackendPython({
  configuredBackendPython,
  fallbackPythonCommand,
  backendPythonCandidates,
}) {
  return configuredBackendPython || backendPythonCandidates.find(Boolean) || fallbackPythonCommand;
}

export function resolveCargoCommand({
  configuredCargoCommand,
  cargoCandidates,
}) {
  return configuredCargoCommand || cargoCandidates.find(Boolean) || "cargo";
}

export function summarizeChecks(checks) {
  return {
    ok: checks.every((check) => check.ok || !check.required),
    blocked: checks.filter((check) => !check.ok && check.required),
    warnings: checks.filter((check) => !check.ok && !check.required),
    passing: checks.filter((check) => check.ok),
  };
}

export function collectSetupHints({
  checks,
  pythonCommand,
  backendPythonCandidates,
  configuredBackendPython,
}) {
  const hints = [];
  const uvicornCheck = checks.find((check) => check.name === "Python uvicorn module");
  const multipartCheck = checks.find((check) => check.name === "Python multipart module");
  const cargoCheck = checks.find((check) => check.name === "Cargo");
  const suggestedBackendPython = backendPythonCandidates.find(Boolean);

  if (uvicornCheck && !uvicornCheck.ok) {
    if (configuredBackendPython) {
      hints.push(
        `The configured backend Python (${configuredBackendPython}) could not import uvicorn. Reinstall backend dependencies in that environment or point LMCA_BACKEND_PYTHON to a Python that already has uvicorn.`,
      );
    } else if (suggestedBackendPython) {
      hints.push(
        `Desktop dev/build scripts will automatically use ${suggestedBackendPython} as the backend Python. Set LMCA_BACKEND_PYTHON only if you want to override that choice.`,
      );
    } else {
      hints.push(
        `Install uvicorn into the backend Python (${pythonCommand}) or set LMCA_BACKEND_PYTHON to the Python executable from your prepared backend environment.`,
      );
    }
  }

  if (multipartCheck && !multipartCheck.ok) {
    hints.push(
      `Install python-multipart into the backend Python (${pythonCommand}) so FastAPI can start routes that accept file uploads.`,
    );
  }

  if (cargoCheck && !cargoCheck.ok) {
    hints.push("Install Rust/Cargo, then rerun `npm run doctor` before starting the desktop shell.");
  }

  return hints;
}

export function formatDoctorReport(summary, setupHints = []) {
  const lines = [
    `Desktop environment check: ${summary.ok ? "ready" : "blocked"}`,
    "",
  ];

  if (summary.passing.length > 0) {
    lines.push("Passing checks:");
    for (const check of summary.passing) {
      lines.push(`- ${check.name}: ${check.detail}`);
    }
    lines.push("");
  }

  if (summary.blocked.length > 0) {
    lines.push("Missing required tools:");
    for (const check of summary.blocked) {
      lines.push(`- ${check.name}: ${check.detail}`);
    }
    lines.push("");
    lines.push("Next step: install the missing required tools, then rerun `npm run doctor`.");
    lines.push("");
  }

  if (summary.warnings.length > 0) {
    lines.push("Optional warnings:");
    for (const check of summary.warnings) {
      lines.push(`- ${check.name}: ${check.detail}`);
    }
    lines.push("");
  }

  if (setupHints.length > 0) {
    lines.push("Suggested fixes:");
    for (const hint of setupHints) {
      lines.push(`- ${hint}`);
    }
    lines.push("");
  }

  lines.push("Expected desktop dev flow:");
  lines.push("- npm run doctor");
  lines.push("- npm run test:rust");
  lines.push("- npm run dev");

  return lines.join("\n");
}

export function runDoctor() {
  const desktopRoot = path.resolve(path.dirname(process.argv[1] ?? "."), "..");
  const repoRoot = path.resolve(desktopRoot, "..", "..", "..");
  const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
  const fallbackPythonCommand = "python";
  const configuredBackendPython = process.env.LMCA_BACKEND_PYTHON || "";
  const configuredCargoCommand = process.env.LMCA_CARGO_BIN || "";
  const backendPythonCandidates = [
    configuredBackendPython,
    path.join("D:", "condaa", "envs", "ai-memory-card-backend", "python.exe"),
    path.join(repoRoot, "apps", "local-web", "backend", ".venv", "Scripts", "python.exe"),
  ].filter((candidate) => candidate && fs.existsSync(candidate));
  const cargoCandidates = [
    configuredCargoCommand,
    path.join(process.env.USERPROFILE || "", ".cargo", "bin", "cargo.exe"),
  ].filter((candidate) => candidate && fs.existsSync(candidate));
  const pythonCommand = resolveEffectiveBackendPython({
    configuredBackendPython,
    fallbackPythonCommand,
    backendPythonCandidates,
  });
  const cargoCommand = resolveCargoCommand({
    configuredCargoCommand,
    cargoCandidates,
  });
  const npmCheck = process.env.npm_execpath
    ? {
        name: "npm",
        ok: true,
        required: true,
        detail: process.env.npm_execpath,
      }
    : checkTool({ name: "npm", command: npmCommand, args: ["--version"] });

  const checks = [
    checkTool({ name: "Node.js", command: "node", args: ["--version"] }),
    npmCheck,
    checkTool({ name: "Python", command: pythonCommand, args: ["--version"] }),
    checkPythonModule({
      name: "Python uvicorn module",
      moduleName: "uvicorn",
      pythonCommand,
      importCommand: "import uvicorn; print(uvicorn.__version__)",
    }),
    checkPythonModule({
      name: "Python multipart module",
      moduleName: "python_multipart",
      pythonCommand,
      importCommand: "import python_multipart; print(python_multipart.__version__)",
    }),
    checkTool({ name: "Cargo", command: cargoCommand, args: ["--version"] }),
    checkPathExists({
      name: "Backend entry",
      path: path.join(repoRoot, "apps", "local-web", "backend", "app", "main.py"),
    }),
    checkPathExists({
      name: "Frontend package",
      path: path.join(repoRoot, "apps", "local-web", "frontend", "package.json"),
    }),
    checkPathExists({
      name: "Tauri CLI package",
      path: path.join(desktopRoot, "node_modules", "@tauri-apps", "cli", "package.json"),
    }),
  ];
  const summary = summarizeChecks(checks);
  const setupHints = collectSetupHints({
    checks,
    pythonCommand,
    backendPythonCandidates,
    configuredBackendPython,
  });
  const report = formatDoctorReport(summary, setupHints);

  return { checks, summary, report, setupHints };
}

const isEntrypoint = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isEntrypoint) {
  const { summary, report } = runDoctor();
  console.log(report);
  process.exitCode = summary.ok ? 0 : 1;
}
