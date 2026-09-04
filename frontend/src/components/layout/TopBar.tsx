import type { Period } from "../../lib/types";
import { formatPeriodLabel } from "../../lib/format";

interface TopBarProps {
  period?: string;
  periods?: Period[];
  onPeriodChange?: (period: string) => void;
  view: "dashboard" | "transactions";
  onViewChange: (view: "dashboard" | "transactions") => void;
  showNav: boolean;
  onCheckForUpdates?: () => void;
  checking?: boolean;
}

export function TopBar({ period, periods, onPeriodChange, view, onViewChange, showNav, onCheckForUpdates, checking }: TopBarProps) {
  const canSelectPeriod = period && periods && periods.length > 1 && onPeriodChange;

  return (
    <div className="mb-10 flex items-baseline justify-between border-b border-hairline pb-4">
      <div className="flex items-baseline gap-4">
        <h1 className="text-lg font-medium tracking-tight text-ink">Ledger</h1>
        {canSelectPeriod ? (
          <select
            value={period}
            onChange={(e) => onPeriodChange(e.target.value)}
            aria-label="Select period"
            className="border border-transparent bg-transparent text-sm text-ink-secondary hover:border-hairline focus:border-ink"
          >
            {periods.map((p) => (
              <option key={p.period} value={p.period}>
                {formatPeriodLabel(p.period)}
              </option>
            ))}
          </select>
        ) : (
          period && <span className="text-sm text-ink-secondary">{formatPeriodLabel(period)}</span>
        )}
      </div>
      {showNav && (
        <nav className="flex items-baseline gap-6 text-sm">
          <button
            onClick={() => onViewChange("dashboard")}
            className={view === "dashboard" ? "text-ink" : "text-ink-secondary hover:text-ink"}
          >
            Ledger
          </button>
          <button
            onClick={() => onViewChange("transactions")}
            className={view === "transactions" ? "text-ink" : "text-ink-secondary hover:text-ink"}
          >
            Transactions
          </button>
          {onCheckForUpdates && (
            <button
              onClick={onCheckForUpdates}
              disabled={checking}
              className="text-ink-secondary hover:text-ink disabled:opacity-50"
            >
              {checking ? "Checking…" : "Check for new statements"}
            </button>
          )}
        </nav>
      )}
    </div>
  );
}
