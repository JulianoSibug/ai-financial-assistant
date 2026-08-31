import type { ReconciliationWarning } from "../../lib/types";
import { formatMoney } from "../../lib/format";
import { Banner } from "../shared/Banner";

export function ReconciliationBanner({ warnings }: { warnings: ReconciliationWarning[] }) {
  const real = warnings.filter((w) => w.status === "warning");
  if (real.length === 0) return null;

  return (
    <div className="mb-8 space-y-2">
      {real.map((w) => (
        <Banner key={w.file_id} tone="warning">
          <span className="font-medium">{w.filename}</span> doesn't reconcile: parsed transactions are off by{" "}
          {formatMoney(w.delta)} from what the statement claims.
          {w.detail && <span className="text-ink-secondary"> {w.detail}</span>}
        </Banner>
      ))}
    </div>
  );
}
