import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  loading?: boolean;
  variant?: ButtonVariant;
}

export function Button({
  children,
  className = "",
  disabled,
  loading = false,
  type = "button",
  variant = "secondary",
  ...props
}: ButtonProps) {
  const classes = ["ui-button", `ui-button-${variant}`, className].filter(Boolean).join(" ");
  return (
    <button type={type} className={classes} disabled={disabled || loading} {...props}>
      {loading ? "Calculating recommendations..." : children}
    </button>
  );
}
