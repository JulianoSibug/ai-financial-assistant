import { useState, type ReactNode } from "react";

interface BannerProps {
  tone?: "warning" | "note";
  children: ReactNode;
  dismissible?: boolean;
  dismissLabel?: string;
  onDismiss?: () => void;
}

export function Banner({ tone = "note", children, dismissible = true, dismissLabel = "Dismiss", onDismiss }: BannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const toneStyles = tone === "warning" ? "border-accent" : "border-hairline";

  return (
    <div className={`flex items-start justify-between gap-4 border-l-2 ${toneStyles} bg-paper px-4 py-3 text-sm`}>
      <div className="text-ink">{children}</div>
      {dismissible && (
        <button
          onClick={() => {
            setDismissed(true);
            onDismiss?.();
          }}
          aria-label="Dismiss"
          className="shrink-0 text-ink-secondary hover:text-ink"
        >
          {dismissLabel}
        </button>
      )}
    </div>
  );
}
