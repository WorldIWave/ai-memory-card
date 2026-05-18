/**
 * Input: button ?????variant?size ?????  |  Output: ????????????
 * Output: ????????????????????????
 * Role: ?????????????????????????
 * Use: ?????????? variant???????????????
 */
import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "icon";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] font-semibold",
        "disabled:cursor-not-allowed disabled:opacity-60 active:scale-[0.98]",
        size === "sm" && "min-h-8 px-3 py-1.5 text-sm",
        size === "md" && "min-h-10 px-4 py-2 text-sm",
        size === "icon" && "h-10 w-10 p-0",
        variant === "primary" &&
          "border border-transparent bg-[var(--color-primary)] text-white shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-md)]",
        variant === "secondary" &&
          "border border-[var(--border-light)] bg-white text-[var(--text-main)] shadow-[var(--shadow-sm)] hover:border-[var(--color-primary)]",
        variant === "ghost" &&
          "border border-transparent bg-transparent text-[var(--text-muted)] hover:bg-[var(--primary-soft)] hover:text-[var(--text-main)]",
        variant === "danger" &&
          "border border-transparent bg-[var(--danger-soft)] text-[var(--danger)] hover:bg-[rgba(214,69,69,0.16)]",
        className,
      )}
      {...props}
    />
  ),
);

Button.displayName = "Button";
