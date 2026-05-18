/**
 * Input: runtime?diagnostics?log export ??? API ??  |  Output: ???????????
 * Output: ??????????????????????
 * Role: ????????????????????????
 * Use: ???? runtime/release ?????????????????????
 */
import { Download, HardDrive, Server } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type {
  SystemBackupRead,
  SystemDiagnosticsRead,
  SystemLogFileRead,
  SystemRuntimeRead,
} from "../../api/types";
import { Button, EmptyState, MetricCard, Skeleton, StatusMessage } from "../../components/ui";
import { formatBytes } from "../../utils/format";

function getDownloadFilename(contentDisposition: string | null) {
  const match = /filename="([^"]+)"/.exec(contentDisposition ?? "");
  return match?.[1] ?? "ai-memory-card-logs.txt";
}

async function exportLogArchive() {
  const response = await fetch("/api/system/logs/export", { method: "GET" });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const payload = await response.text();
  const blob = new Blob([payload], {
    type: response.headers.get("content-type") ?? "text/plain",
  });
  const downloadUrl = globalThis.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = getDownloadFilename(response.headers.get("content-disposition"));
  document.body.append(link);
  link.click();
  link.remove();
  globalThis.URL.revokeObjectURL(downloadUrl);
}

interface RuntimeDetailsProps {
  runtime: SystemRuntimeRead;
}

function RuntimeDetails({ runtime }: RuntimeDetailsProps) {
  const { t } = useTranslation();
  return (
    <ul className="settings-path-list">
      <li>
        <strong>{t("diagnostics_path_app")}</strong>
        <span>{runtime.app_name}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_app_data")}</strong>
        <span>{runtime.app_data_dir}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_db")}</strong>
        <span>{runtime.database_path}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_backups")}</strong>
        <span>{runtime.backup_dir}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_logs")}</strong>
        <span>{runtime.log_dir}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_cache")}</strong>
        <span>{runtime.cache_dir}</span>
      </li>
      <li>
        <strong>{t("diagnostics_path_backend_root")}</strong>
        <span>{runtime.backend_root}</span>
      </li>
      <li>
        <strong>{t("diagnostics_runtime_mode")}</strong>
        <span>{runtime.runtime_mode}</span>
      </li>
      {runtime.release_channel_url ? (
        <li>
          <strong>{t("diagnostics_release_link")}</strong>
          <a href={runtime.release_channel_url} target="_blank" rel="noreferrer">
            {t("diagnostics_release_link")}
          </a>
        </li>
      ) : null}
    </ul>
  );
}

interface DiagnosticsSummaryProps {
  diagnostics: SystemDiagnosticsRead;
  runtime: SystemRuntimeRead;
}

function DiagnosticsSummary({ diagnostics, runtime }: DiagnosticsSummaryProps) {
  const { t } = useTranslation();
  return (
    <div className="data-metric-grid">
      <MetricCard
        label={t("diagnostics_backend_port")}
        value={runtime.backend_port ?? "auto"}
        hint={`${t("diagnostics_backend_version")} ${runtime.backend_version}`}
        icon={<Server size={18} aria-hidden="true" />}
      />
      <MetricCard
        label={t("diagnostics_db_present")}
        value={diagnostics.database_exists ? t("diagnostics_db_present_yes") : t("diagnostics_db_present_no")}
        hint={t("diagnostics_db_size", { size: formatBytes(diagnostics.database_size_bytes) })}
        icon={<HardDrive size={18} aria-hidden="true" />}
      />
      <MetricCard
        label={t("diagnostics_backups_count", { count: diagnostics.backup_count })}
        value={diagnostics.backup_count}
        hint={t("diagnostics_logs_count", { count: diagnostics.log_files.length })}
        icon={<Download size={18} aria-hidden="true" />}
      />
    </div>
  );
}

interface BackupSnapshotListProps {
  backups: SystemBackupRead[];
}

function BackupSnapshotList({ backups }: BackupSnapshotListProps) {
  const { t } = useTranslation();
  if (backups.length === 0) {
    return <p className="hint-text">{t("diagnostics_no_backups")}</p>;
  }

  return (
    <ul className="settings-list">
      {backups.map((backup) => (
        <li key={backup.filename} className="settings-list-row">
          <p className="settings-list-title">{backup.filename}</p>
          <p className="settings-list-meta">{formatBytes(backup.size_bytes)}</p>
        </li>
      ))}
    </ul>
  );
}

interface LogFileListProps {
  logFiles: SystemLogFileRead[];
}

function LogFileList({ logFiles }: LogFileListProps) {
  const { t } = useTranslation();
  if (logFiles.length === 0) {
    return <p className="hint-text">{t("diagnostics_no_logs")}</p>;
  }

  return (
    <ul className="settings-list">
      {logFiles.map((logFile) => (
        <li key={logFile.path} className="settings-list-row">
          <p className="settings-list-title">{logFile.name}</p>
          <p className="settings-list-meta">
            {logFile.path} | {formatBytes(logFile.size_bytes)}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function DiagnosticsPanel() {
  const { t } = useTranslation();
  const [runtime, setRuntime] = useState<SystemRuntimeRead | null>(null);
  const [diagnostics, setDiagnostics] = useState<SystemDiagnosticsRead | null>(null);
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadDiagnostics() {
      setErrorText("");

      try {
        const [runtimeSnapshot, diagnosticsSnapshot] = await Promise.all([
          apiRequest<SystemRuntimeRead>("/api/system/runtime"),
          apiRequest<SystemDiagnosticsRead>("/api/system/diagnostics"),
        ]);

        if (!ignore) {
          setRuntime(runtimeSnapshot);
          setDiagnostics(diagnosticsSnapshot);
        }
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("diagnostics_load_error"));
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void loadDiagnostics();
    return () => {
      ignore = true;
    };
  }, [t]);

  async function onExportLogs() {
    setIsExporting(true);
    setErrorText("");
    setStatusText("");

    try {
      await exportLogArchive();
      setStatusText(t("diagnostics_export_success"));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("diagnostics_export_error"));
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>{t("diagnostics_heading")}</h3>
          <p>{t("diagnostics_hint")}</p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void onExportLogs()} disabled={isExporting}>
          <Download size={16} aria-hidden="true" />
          {isExporting ? t("diagnostics_export_loading") : t("diagnostics_export_logs")}
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : null}

      {!isLoading && runtime && diagnostics ? (
        <>
          <DiagnosticsSummary diagnostics={diagnostics} runtime={runtime} />
          <RuntimeDetails runtime={runtime} />
          <div className="settings-card-header">
            <div>
              <h3>{t("diagnostics_known_backups")}</h3>
            </div>
          </div>
          <BackupSnapshotList backups={diagnostics.backups} />
          <div className="settings-card-header">
            <div>
              <h3>{t("diagnostics_log_files")}</h3>
            </div>
          </div>
          <LogFileList logFiles={diagnostics.log_files} />
        </>
      ) : null}

      {!isLoading && !runtime && !diagnostics && !errorText ? (
        <EmptyState
          icon={Server}
          title={t("diagnostics_heading")}
          description={t("diagnostics_no_logs")}
          className="min-h-36"
        />
      ) : null}

      {statusText ? <StatusMessage tone="success">{statusText}</StatusMessage> : null}
      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}
    </section>
  );
}
