/**
 * Input: label?hint?error ????? children  |  Output: ???????????????
 * Output: ?????????????????????????
 * Role: ?????????????????
 * Use: ?????????????????????? label/error ??
 */
import { forwardRef } from "react";
import type { InputHTMLAttributes, LabelHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

interface FieldShellProps extends LabelHTMLAttributes<HTMLLabelElement> {
  label: string;
  hint?: ReactNode;
}

export function FieldShell({ label, hint, className, children, ...props }: FieldShellProps) {
  return (
    <label className={cn("grid gap-2 text-sm font-medium text-[var(--text-main)]", className)} {...props}>
      <span>{label}</span>
      {children}
      {hint ? <span className="text-xs font-normal text-[var(--text-muted)]">{hint}</span> : null}
    </label>
  );
}

export function TextField({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn("ui-field", className)} {...props} />;
}

export const TextareaField = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn("ui-field min-h-28 resize-y", className)} {...props} />
  ),
);

TextareaField.displayName = "TextareaField";

export function SelectField({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("ui-field", className)} {...props} />;
}
