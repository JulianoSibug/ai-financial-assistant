import { CATEGORIES } from "../../lib/categories";
import type { TransactionFilters } from "../../lib/types";

interface FilterBarProps {
  filters: TransactionFilters;
  onChange: (filters: TransactionFilters) => void;
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const activeCategory = filters.category ?? "";

  return (
    <div className="mb-6 space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange({ ...filters, category: undefined, page: 1 })}
          className={`border px-3 py-1 text-sm ${
            activeCategory === "" ? "border-ink text-ink" : "border-hairline text-ink-secondary hover:border-ink"
          }`}
        >
          All
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => onChange({ ...filters, category: c, page: 1 })}
            className={`border px-3 py-1 text-sm ${
              activeCategory === c ? "border-ink text-ink" : "border-hairline text-ink-secondary hover:border-ink"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <input
          type="search"
          placeholder="Search merchant"
          value={filters.merchant ?? ""}
          onChange={(e) => onChange({ ...filters, merchant: e.target.value, page: 1 })}
          className="border border-hairline px-3 py-1.5 text-sm text-ink focus:border-ink"
        />
        <input
          type="date"
          value={filters.date_from ?? ""}
          onChange={(e) => onChange({ ...filters, date_from: e.target.value, page: 1 })}
          className="border border-hairline px-3 py-1.5 text-sm text-ink focus:border-ink"
        />
        <span className="text-sm text-ink-secondary">to</span>
        <input
          type="date"
          value={filters.date_to ?? ""}
          onChange={(e) => onChange({ ...filters, date_to: e.target.value, page: 1 })}
          className="border border-hairline px-3 py-1.5 text-sm text-ink focus:border-ink"
        />
        <label className="flex items-center gap-2 text-sm text-ink-secondary">
          <input
            type="checkbox"
            checked={filters.include_transfers ?? true}
            onChange={(e) => onChange({ ...filters, include_transfers: e.target.checked, page: 1 })}
          />
          Include transfers
        </label>
      </div>
    </div>
  );
}
