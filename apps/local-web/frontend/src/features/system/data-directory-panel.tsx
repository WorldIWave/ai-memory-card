/**
 * Input: data-directory desktop bridge state  |  Output: settings card for migration scheduling
 * Role: lets the desktop app choose a one-time custom durable data directory
 * Note: browser/backend fallback is read-only; migration commands require the Tauri bridge
 * Usage: mount from Settings data section after Task 7 wires the page
 */
import { FolderOpen, HardDrive } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  chooseDataDirectory,
  getDataDirectoryState,
  scheduleDataDirectoryMigration,
} from "../../api/data-directory";
import type { DataDirectoryStateRead } from "../../api/types";
import { ConfirmDialog, Skeleton, StatusMessage } from "../../components/ui";

function DirectoryField({
  disabled,
  label,
  onChoose,
  value,
}: {
  disabled: boolean;
  label: string;
  onChoose?: () => void;
  value: string;
}) {
  if (!onChoose) {
    return (
      <div className="settings-directory-field">
        <span>
          <strong>{label}</strong>
          <span>{value}</span>
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      className="settings-directory-field is-clickable"
      aria-label={label}
      onClick={onChoose}
      disabled={disabled}
    >
      <span>
        <strong>{label}</strong>
        <span>{value}</span>
      </span>
      <FolderOpen size={18} aria-hidden="true" />
    </button>
  );
}

export function DataDirectoryPanel() {
  const { t } = useTranslation();
  const [state, setState] = useState<DataDirectoryStateRead | null>(null);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [errorText, setErrorText] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isScheduling, setIsScheduling] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadState() {
      setErrorText("");
      try {
        const nextState = await getDataDirectoryState();
        if (!ignore) {
          setState(nextState);
        }
      } catch (error) {
        if (!ignore) {
          setErrorText(error instanceof Error ? error.message : t("data_directory_load_error"));
        }
      } finally {
        if (!ignore) {
          setIsLoading(false);
        }
      }
    }

    void loadState();
    return () => {
      ignore = true;
    };
  }, [t]);

  async function onChooseDirectory() {
    setStatusText("");
    setErrorText("");

    try {
      const target = await chooseDataDirectory();
      if (!target) {
        setStatusText(t("data_directory_select_cancelled"));
        return;
      }

      setSelectedTarget(target);
      setConfirmOpen(true);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("data_directory_schedule_error"));
    }
  }

  async function onScheduleMigration() {
    const target = selectedTarget;
    if (!target) return;

    setIsScheduling(true);
    setErrorText("");
    setStatusText("");

    try {
      const nextState = await scheduleDataDirectoryMigration(target);
      setState(nextState);
      setConfirmOpen(false);
      setSelectedTarget("");
    } catch (error) {
      setConfirmOpen(false);
      setSelectedTarget("");
      setErrorText(error instanceof Error ? error.message : t("data_directory_schedule_error"));
    } finally {
      setIsScheduling(false);
    }
  }

  function onConfirmOpenChange(open: boolean) {
    if (isScheduling) return;
    setConfirmOpen(open);
    if (!open) {
      setSelectedTarget("");
    }
  }

  return (
    <section className="settings-card">
      <div className="settings-card-header">
        <div>
          <h3>{t("data_directory_heading")}</h3>
          <p>{t("data_directory_hint")}</p>
        </div>
        <HardDrive size={20} aria-hidden="true" />
      </div>

      {isLoading ? <Skeleton className="h-24 w-full" aria-label={t("data_directory_loading")} /> : null}

      {!isLoading && state ? (
        <>
          <DirectoryField
            label={t("data_directory_current")}
            value={state.current_app_data_root}
            disabled={!state.migration_allowed || isScheduling}
            onChoose={state.desktop_bridge_available ? () => void onChooseDirectory() : undefined}
          />

          <StatusMessage tone={state.custom_app_data_root ? "success" : "info"}>
            {state.custom_app_data_root ? t("data_directory_custom_active") : t("data_directory_default_active")}
          </StatusMessage>

          {state.pending_target_app_data_root ? (
            <StatusMessage tone="info">
              {t("data_directory_pending_restart")} {state.pending_target_app_data_root}
            </StatusMessage>
          ) : null}

          {!state.desktop_bridge_available ? (
            <StatusMessage tone="info">{t("data_directory_desktop_only")}</StatusMessage>
          ) : null}
        </>
      ) : null}

      {statusText ? <StatusMessage tone="info">{statusText}</StatusMessage> : null}
      {errorText ? <StatusMessage tone="error">{errorText}</StatusMessage> : null}

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={onConfirmOpenChange}
        title={t("data_directory_confirm_title")}
        description={t("data_directory_confirm_description", { target: selectedTarget })}
        cancelLabel={t("data_directory_cancel_target")}
        confirmLabel={t("data_directory_schedule")}
        confirmDisabled={isScheduling}
        cancelDisabled={isScheduling}
        onConfirm={() => void onScheduleMigration()}
      />
    </section>
  );
}
