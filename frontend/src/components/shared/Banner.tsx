import { useState, type ReactNode } from "react";

interface BannerProps {
  tone?: "warning" | "note";
  children: ReactNode;
  dismissible?: boolean;
  dismissLabel?: string;
  onDismiss?: () => void;
  secondaryAction?: { label: string; onClick: () => void };
}

export function Banner({
  tone = "note",
  children,
  dismissible = true,
  dismissLabel = "Dismiss",
  onDismiss,
  secondaryAction,
}: BannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const toneStyles = tone === "warning" ? "border-accent" : "border-hairline";

  return (
    <div className={`flex items-start justify-between gap-4 border-l-2 ${toneStyles} bg-paper px-4 py-3 text-sm`}>
      <div className="text-ink">{children}</div>
      <div className="flex shrink-0 items-baseline gap-4">
        {secondaryAction && (
          <button onClick={secondaryAction.onClick} className="text-ink-secondary hover:text-ink">
            {secondaryAction.label}
          </button>
        )}
        {dismissible && (
          <button
            onClick={() => {
              setDismissed(true);
              onDismiss?.();
            }}
            aria-label="Dismiss"
            className="text-ink-secondary hover:text-ink"
          >
            {dismissLabel}
          </button>
        )}
      </div>
    </div>
  );
}
