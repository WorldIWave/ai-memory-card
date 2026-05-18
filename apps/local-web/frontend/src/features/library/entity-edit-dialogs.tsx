/**
 * Input: ???/???????????????  |  Output: ?????????
 * Output: ?????????????????????????????
 * Role: ?? library ??????????????
 * Use: ????????????????????????????
 */
import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest } from "../../api/client";
import type { DeckRead, DeckUpdateInput, FolderRead, FolderUpdateInput } from "../../api/types";
import { Button, FieldShell, SelectField, StatusMessage, TextField, TextareaField } from "../../components/ui";

interface FolderRenameDialogProps {
  folder: FolderRead | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (folder: FolderRead) => void;
}

interface DeckEditDialogProps {
  deck: DeckRead | null;
  folders: FolderRead[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (deck: DeckRead) => void;
}

export function FolderRenameDialog({ folder, open, onOpenChange, onSaved }: FolderRenameDialogProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(folder?.name ?? "");
  const [errorText, setErrorText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !folder) {
      return;
    }

    setName(folder.name);
    setErrorText("");
    setSaving(false);
  }, [folder, open]);

  async function save() {
    if (!folder || saving || !name.trim()) {
      return;
    }

    setSaving(true);
    setErrorText("");

    const payload: FolderUpdateInput = {
      name: name.trim(),
    };

    try {
      const updated = await apiRequest<FolderRead>(`/api/folders/${folder.id}`, {
        method: "PUT",
        body: payload,
      });
      onSaved(updated);
      onOpenChange(false);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("folder_save_error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content" aria-describedby={undefined}>
          <Dialog.Title className="mb-4 text-base font-semibold">{t("folder_rename")}</Dialog.Title>

          <div className="grid gap-3">
            <FieldShell label={t("folder_name_placeholder")}>
              <TextField
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("folder_name_placeholder")}
              />
            </FieldShell>
          </div>

          {errorText ? <StatusMessage tone="error" className="mt-3">{errorText}</StatusMessage> : null}

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)} size="sm">
              {t("cancel")}
            </Button>
            <Button onClick={() => void save()} disabled={saving || !name.trim()} size="sm">
              {saving ? t("saving") : t("confirm")}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function DeckEditDialog({ deck, folders, open, onOpenChange, onSaved }: DeckEditDialogProps) {
  const { t } = useTranslation();
  const initialFolderId = useMemo(() => {
    if (deck?.folder_id != null) {
      return String(deck.folder_id);
    }
    return String(folders[0]?.id ?? 0);
  }, [deck?.folder_id, folders]);
  const [name, setName] = useState(deck?.name ?? "");
  const [description, setDescription] = useState(deck?.description ?? "");
  const [folderId, setFolderId] = useState(initialFolderId);
  const [errorText, setErrorText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !deck) {
      return;
    }

    setName(deck.name);
    setDescription(deck.description);
    setFolderId(deck.folder_id != null ? String(deck.folder_id) : String(folders[0]?.id ?? 0));
    setErrorText("");
    setSaving(false);
  }, [deck, folders, open]);

  async function save() {
    if (!deck || saving || !name.trim() || folders.length === 0) {
      return;
    }

    setSaving(true);
    setErrorText("");

    const payload: DeckUpdateInput = {
      name: name.trim(),
      description: description.trim(),
      folder_id: Number(folderId),
    };

    try {
      const updated = await apiRequest<DeckRead>(`/api/decks/${deck.id}`, {
        method: "PUT",
        body: payload,
      });
      onSaved(updated);
      onOpenChange(false);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("deck_save_error"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content" aria-describedby={undefined}>
          <Dialog.Title className="mb-4 text-base font-semibold">{t("deck_edit")}</Dialog.Title>

          <div className="grid gap-3">
            <FieldShell label={t("deck_name_placeholder")}>
              <TextField
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("deck_name_placeholder")}
              />
            </FieldShell>

            <FieldShell label={t("deck_description_label")}>
              <TextareaField
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder={t("deck_description_label")}
                rows={4}
              />
            </FieldShell>

            <FieldShell label={t("deck_folder_label")}>
              <SelectField
                value={folderId}
                onChange={(event) => setFolderId(event.target.value)}
                disabled={folders.length === 0}
              >
                {folders.map((folderOption) => (
                  <option key={folderOption.id} value={String(folderOption.id)}>
                    {folderOption.name}
                  </option>
                ))}
              </SelectField>
            </FieldShell>
          </div>

          {errorText ? <StatusMessage tone="error" className="mt-3">{errorText}</StatusMessage> : null}

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => onOpenChange(false)} size="sm">
              {t("cancel")}
            </Button>
            <Button onClick={() => void save()} disabled={saving || !name.trim() || folders.length === 0} size="sm">
              {saving ? t("saving") : t("deck_save")}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
