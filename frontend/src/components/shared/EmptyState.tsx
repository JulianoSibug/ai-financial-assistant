import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  detail?: string;
  action?: ReactNode;
}

export function EmptyState({ title, detail, action }: EmptyStateProps) {
  return (
    <div className="border border-hairline px-8 py-12 text-left">
      <p className="text-lg text-ink">{title}</p>
      {detail && <p className="mt-2 text-sm text-ink-secondary">{detail}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
