import { formatPeriodLabel } from "../../lib/format";

interface TopBarProps {
  period?: string;
  view: "dashboard" | "transactions";
  onViewChange: (view: "dashboard" | "transactions") => void;
  showNav: boolean;
}

export function TopBar({ period, view, onViewChange, showNav }: TopBarProps) {
  return (
    <div className="mb-10 flex items-baseline justify-between border-b border-hairline pb-4">
      <div className="flex items-baseline gap-4">
        <h1 className="text-lg font-medium tracking-tight text-ink">Ledger</h1>
        {period && <span className="text-sm text-ink-secondary">{formatPeriodLabel(period)}</span>}
      </div>
      {showNav && (
        <nav className="flex gap-6 text-sm">
          <button
            onClick={() => onViewChange("dashboard")}
            className={view === "dashboard" ? "text-ink" : "text-ink-secondary hover:text-ink"}
          >
            Dashboard
          </button>
          <button
            onClick={() => onViewChange("transactions")}
            className={view === "transactions" ? "text-ink" : "text-ink-secondary hover:text-ink"}
          >
            Transactions
          </button>
        </nav>
      )}
    </div>
  );
}
