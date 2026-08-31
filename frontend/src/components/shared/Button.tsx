import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const base = "px-4 py-2 text-sm border transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const styles =
    variant === "primary"
      ? "bg-ink text-paper border-ink hover:bg-accent hover:border-accent"
      : "bg-transparent text-ink border-hairline hover:border-ink";
  return <button className={`${base} ${styles} ${className}`} {...props} />;
}
