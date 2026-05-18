/**
 * Input: ???????/??????? API ??  |  Output: ??????
 * Output: ??????????????????????
 * Role: ??????????????????????
 * Use: ??????????????????????????/??
 */
import { DatabaseBackup, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type { SystemBackupRead, SystemRestoreResponse } from "../../api/types";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  SelectField,
  Skeleton,
  StatusMessage,
} from "../../components/ui";
import { formatBytes, formatTimestamp } from "../../utils/format";

interface BackupListProps {
  backups: SystemBackupRead[];
}

function BackupList({ backups }: BackupListProps) {
  const { t } = useTranslation();

  if (backups.length === 0) {
    return (
      <EmptyState
        icon={DatabaseBackup}
        title={t("backup_empty")}
        description={t("backup_hint")}
        className="min-h-36"
      />
    );
  }

  return (
    <ul className="settings-list">
      {backups.map((backup) => (
        <li key={backup.filename} className="settings-list-row">
          <div>
            <p className="settings-list-title">{backup.filename}</p>
            <p className="settings-list-meta">
              {formatBytes(backup.size_bytes)} | {formatTimestamp(backup.modified_at)}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function BackupPanel() {
  const { t } = useTranslation();
  const [backups, setBackups] = useState<SystemBackupRead[]>([]);
  const [selectedFilename, setSelectedFilename] = useState("");
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<"backup" | "restore" | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadBackups() {
      setErrorText("");
      try {
        const backupList = await apiRequest<SystemBackupRead[]>("/api/system/backups");
        if (!ignore) {
          setBackups(backupList);
          setSelectedFilename(backupList[0]?.filename ?? "");
        }
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("backup_load_error"));
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void loadBackups();
    return () => {
      ignore = true;
    };
  }, [t]);

  async function refreshBackups(preferredFilename?: string) {
    const backupList = await apiRequest<SystemBackupRead[]>("/api/system/backups");
    setBackups(backupList);
    setSelectedFilename((current) => {
      if (preferredFilename && backupList.some((backup) => backup.filename === preferredFilename)) {
        return preferredFilename;
      }
      if (current && backupList.some((backup) => backup.filename === current)) {
        return current;
      }
      return backupList[0]?.filename ?? "";
    });
  }

  async function createBackup() {
    setPendingAction("backup");
    setErrorText("");
    setStatusText("");

    try {
      const backup = await apiRequest<SystemBackupRead>("/api/system/backup", {
        method: "POST",
      });
      await refreshBackups(backup.filename);
      setStatusText(t("backup_create_success", { filename: backup.filename }));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("backup_create_error"));
    } finally {
      setPendingAction(null);
    }
  }

  async function restoreBackup() {
    if (!selectedFilename) return;

    setConfirmOpen(false);
    setPendingAction("restore");
    setErrorText("");
    setStatusText("");

    try {
      const response = await apiRequest<SystemRestoreResponse>("/api/system/restore", {
        method: "POST",
        body: { filename: selectedFilename },
      });
      setStatusText(t("backup_restore_success", { filename: response.restored_from }));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("backup_restore_error"));
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>{t("backup_heading")}</h3>
          <p>{t("backup_hint")}</p>
        </div>
        <DatabaseBackup size={20} aria-hidden="true" />
      </div>

      {isLoading ? (
        <div className="grid gap-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : (
        <>
          <div className="settings-action-row">
            <Button type="button" onClick={() => void createBackup()} disabled={pendingAction !== null}>
              <DatabaseBackup size={16} aria-hidden="true" />
              {pendingAction === "backup" ? t("backup_create_loading") : t("backup_create")}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setConfirmOpen(true)}
              disabled={pendingAction !== null || !selectedFilename}
            >
              <RotateCcw size={16} aria-hidden="true" />
              {pendingAction === "restore" ? t("backup_restore_loading") : t("backup_restore")}
            </Button>
          </div>

          <label className="grid gap-2 text-sm font-medium text-[var(--text-main)]">
            <span>{t("backup_available")}</span>
            <SelectField
              aria-label={t("backup_available")}
              value={selectedFilename}
              onChange={(event) => setSelectedFilename(event.target.value)}
              disabled={backups.length === 0 || pendingAction !== null}
            >
              {backups.length === 0 ? <option value="">{t("backup_select_empty")}</option> : null}
              {backups.map((backup) => (
                <option key={backup.filename} value={backup.filename}>
                  {backup.filename}
                </option>
              ))}
            </SelectField>
          </label>

          <BackupList backups={backups} />
        </>
      )}

      {statusText ? <StatusMessage tone="success">{statusText}</StatusMessage> : null}
      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={t("backup_restore_title")}
        description={t("backup_restore_description", { filename: selectedFilename })}
        cancelLabel={t("cancel")}
        confirmLabel={t("confirm")}
        destructive
        onConfirm={() => void restoreBackup()}
      />
    </section>
  );
}
