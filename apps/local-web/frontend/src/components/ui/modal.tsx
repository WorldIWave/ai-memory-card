/**
 * Input: open/onOpenChange????children ?????  |  Output: ???????????
 * Output: ???????????????? modal ???????
 * Role: ???????????????????
 * Use: ?????????????????????????????
 */
import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { Button } from "./button";

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}

export function Modal({ open, onOpenChange, title, description, children }: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="ui-dialog-overlay" />
        <Dialog.Content className="ui-dialog-content">
          <Dialog.Title className="text-lg font-semibold text-[var(--text-main)]">{title}</Dialog.Title>
          {description ? (
            <Dialog.Description className="mt-1 text-sm text-[var(--text-muted)]">
              {description}
            </Dialog.Description>
          ) : null}
          <div className="mt-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  destructive?: boolean;
  confirmDisabled?: boolean;
  cancelDisabled?: boolean;
  actionOrder?: "cancel-confirm" | "confirm-cancel";
  errorText?: string;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  destructive = false,
  confirmDisabled = false,
  cancelDisabled = false,
  actionOrder = "cancel-confirm",
  errorText = "",
}: ConfirmDialogProps) {
  const cancelButton = (
    <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={cancelDisabled}>
      {cancelLabel}
    </Button>
  );
  const confirmButton = (
    <Button variant={destructive ? "danger" : "primary"} onClick={onConfirm} disabled={confirmDisabled}>
      {confirmLabel}
    </Button>
  );

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={title} description={description}>
      {errorText ? (
        <p
          role="alert"
          className="mb-3 rounded-[var(--radius-sm)] bg-[var(--danger-soft)] px-3 py-2 text-sm font-semibold text-[var(--danger)]"
        >
          {errorText}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        {actionOrder === "confirm-cancel" ? (
          <>
            {confirmButton}
            {cancelButton}
          </>
        ) : (
          <>
            {cancelButton}
            {confirmButton}
          </>
        )}
      </div>
    </Modal>
  );
}
