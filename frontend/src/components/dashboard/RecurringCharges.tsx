import type { RecurringCharge } from "../../lib/types";
import { formatMoneyAbs } from "../../lib/format";

export function RecurringCharges({ charges }: { charges: RecurringCharge[] }) {
  if (charges.length === 0) {
    return <p className="text-sm text-ink-secondary">Nothing recurring detected yet -- this builds up as more months come in.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-hairline text-left text-ink-secondary">
          <th className="pb-2 font-normal">Merchant</th>
          <th className="pb-2 font-normal">Amount</th>
          <th className="pb-2 font-normal">Cadence</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {charges.map((c) => (
          <tr key={c.merchant}>
            <td className="py-2 text-ink">{c.merchant}</td>
            <td className="py-2 tabular-nums text-ink">{c.amount ? formatMoneyAbs(c.amount) : "varies"}</td>
            <td className="py-2 text-ink-secondary">{c.cadence}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
