import type { FixRequest } from "../../lib/types";
import { Banner } from "../shared/Banner";

const TRIGGER_LABEL: Record<FixRequest["trigger"], string> = {
  reconciliation_warning: "doesn't reconcile",
  low_extraction: "may be missing transactions",
};

interface FixRequestsBannerProps {
  requests: FixRequest[];
  onResolve: (id: number, status: "resolved" | "dismissed") => void;
  onDeleteFile: (fileId: number) => void;
}

export function FixRequestsBanner({ requests, onResolve, onDeleteFile }: FixRequestsBannerProps) {
  if (requests.length === 0) return null;

  return (
    <div className="mb-8 space-y-2">
      {requests.map((r) => (
        <Banner
          key={r.id}
          tone="warning"
          dismissLabel="Mark fixed"
          onDismiss={() => onResolve(r.id, "resolved")}
          secondaryAction={{ label: "Delete & re-ingest", onClick: () => onDeleteFile(r.file_id) }}
        >
          <span className="font-medium">{r.filename}</span> {TRIGGER_LABEL[r.trigger]}.{" "}
          <span className="text-ink-secondary">{r.signal_detail}</span>
        </Banner>
      ))}
    </div>
  );
}
