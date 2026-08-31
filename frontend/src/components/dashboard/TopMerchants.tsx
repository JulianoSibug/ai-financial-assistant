import type { MerchantTotal } from "../../lib/types";
import { formatMoneyAbs } from "../../lib/format";

export function TopMerchants({ merchants }: { merchants: MerchantTotal[] }) {
  if (merchants.length === 0) {
    return <p className="text-sm text-ink-secondary">No merchant activity for this period.</p>;
  }

  return (
    <ul className="divide-y divide-hairline">
      {merchants.map((m) => (
        <li key={m.merchant} className="flex items-center justify-between py-2.5 text-sm">
          <span className="text-ink">{m.merchant}</span>
          <span className="flex items-baseline gap-3">
            <span className="text-ink-secondary">
              {m.count} {m.count === 1 ? "transaction" : "transactions"}
            </span>
            <span className="tabular-nums text-ink">{formatMoneyAbs(m.total)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
