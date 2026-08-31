import type { CategoryTotal } from "../../lib/types";
import { formatMoneyAbs, formatPercent } from "../../lib/format";

export function CategoryBreakdown({ categories }: { categories: CategoryTotal[] }) {
  const spendCategories = categories.filter((c) => Number(c.total) > 0);
  const max = Math.max(...spendCategories.map((c) => Number(c.total)), 1);

  if (spendCategories.length === 0) {
    return <p className="text-sm text-ink-secondary">No spending recorded for this period.</p>;
  }

  return (
    <div className="space-y-3">
      {spendCategories.map((c) => {
        const width = (Number(c.total) / max) * 100;
        return (
          <div key={c.category}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-ink">{c.category}</span>
              <span className="tabular-nums text-ink-secondary">
                {formatMoneyAbs(c.total)} &middot; {formatPercent(c.percent)}
              </span>
            </div>
            <div className="h-1.5 bg-hairline">
              <div className="h-full bg-ink" style={{ width: `${width}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
