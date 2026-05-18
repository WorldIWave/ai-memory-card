/**
 * Input: ????????/??/?????  |  Output: ??????
 * Output: ?? folder ?????????????
 * Role: ?? Library ???????????
 * Use: ??????????????????????????
 */
import * as ContextMenu from "@radix-ui/react-context-menu";
import * as Dialog from "@radix-ui/react-dialog";
import { Folder, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiRequest } from "../../api/client";
import type { FolderRead } from "../../api/types";
import { Button, ConfirmDialog, TextField } from "../../components/ui";
import { cn } from "../../lib/utils";

interface Props {
  folders: FolderRead[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onRename: (folder: FolderRead) => void;
  onChanged: () => void;
}

export function FolderPanel({ folders, selectedId, onSelect, onRename, onChanged }: Props) {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<FolderRead | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteErrorText, setDeleteErrorText] = useState("");

  async function createFolder() {
    if (!newName.trim() || submitting) return;
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiRequest("/api/folders", { method: "POST", body: { name: newName.trim() } });
      setNewName("");
      setDialogOpen(false);
      onChanged();
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Create folder failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteFolder(folder: FolderRead) {
    if (deleting) return;
    setDeleting(true);
    setDeleteErrorText("");
    try {
      await apiRequest(`/api/folders/${folder.id}`, { method: "DELETE" });
      setDeleteTarget(null);
      onChanged();
    } catch (error) {
      setDeleteErrorText(error instanceof Error ? error.message : t("folder_delete_error"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <section className="library-column" aria-label={t("folder_heading")}>
      <div className="library-column-header">
        <div>
          <p className="library-column-kicker">{t("folder_heading")}</p>
          <h2>{folders.length}</h2>
        </div>
        <Folder size={18} aria-hidden="true" />
      </div>
      <div className="library-list">
        {folders.map((f) => (
          <ContextMenu.Root key={f.id}>
            <ContextMenu.Trigger asChild>
              <button
                onClick={() => onSelect(f.id)}
                className={cn(
                  "library-list-card",
                  selectedId === f.id
                    ? "is-selected"
                    : "text-[var(--text-muted)] hover:text-[var(--text-main)]",
                )}
              >
                {f.name}
              </button>
            </ContextMenu.Trigger>
            <ContextMenu.Portal>
              <ContextMenu.Content className="z-50 min-w-[150px] rounded-[var(--radius-md)] border border-[var(--border-light)] bg-white p-1 shadow-[var(--shadow-md)]">
                {f.id !== 1 ? (
                  <ContextMenu.Item
                    onSelect={() => onRename(f)}
                    className="cursor-pointer rounded px-3 py-1.5 text-sm hover:bg-[var(--primary-soft)]"
                  >
                    {t("folder_rename")}
                  </ContextMenu.Item>
                ) : null}
                <ContextMenu.Item
                  onSelect={() => setTimeout(() => setDialogOpen(true), 0)}
                  className="cursor-pointer rounded px-3 py-1.5 text-sm hover:bg-[var(--primary-soft)]"
                >
                  {t("folder_new")}
                </ContextMenu.Item>
                {f.id !== 1 && (
                  <ContextMenu.Item
                    onSelect={() => {
                      setDeleteErrorText("");
                      setDeleteTarget(f);
                    }}
                    className="cursor-pointer rounded px-3 py-1.5 text-sm text-[var(--danger)] hover:bg-[var(--danger-soft)]"
                  >
                    {t("folder_delete")}
                  </ContextMenu.Item>
                )}
              </ContextMenu.Content>
            </ContextMenu.Portal>
          </ContextMenu.Root>
        ))}
      </div>

      <Button variant="secondary" onClick={() => setDialogOpen(true)} className="mt-3 w-full">
        <Plus size={16} aria-hidden="true" />
        {t("folder_new")}
      </Button>

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="ui-dialog-overlay" />
          <Dialog.Content className="ui-dialog-content" aria-describedby={undefined}>
            <Dialog.Title className="text-base font-semibold mb-4">{t("folder_new")}</Dialog.Title>
            <TextField
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void createFolder();
              }}
              placeholder={t("folder_name_placeholder")}
              className="mb-4"
            />
            {errorMsg ? <p className="text-destructive text-sm mb-2">{errorMsg}</p> : null}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setDialogOpen(false)} size="sm">
                {t("cancel")}
              </Button>
              <Button onClick={() => void createFolder()} disabled={submitting} size="sm">
                {submitting ? t("saving") : t("confirm")}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) {
            setDeleteTarget(null);
            setDeleteErrorText("");
          }
        }}
        title={t("folder_delete_title")}
        description={t("folder_delete_description")}
        confirmLabel={t("confirm")}
        cancelLabel={t("cancel")}
        destructive
        confirmDisabled={deleting}
        cancelDisabled={deleting}
        actionOrder="confirm-cancel"
        errorText={deleteErrorText}
        onConfirm={() => {
          if (deleteTarget) {
            void deleteFolder(deleteTarget);
          }
        }}
      />
    </section>
  );
}
