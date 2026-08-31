import type { Transaction, TransactionFilters } from "../../lib/types";
import { formatDate } from "../../lib/format";
import { Money } from "../shared/Money";
import { CategoryDropdown } from "./CategoryDropdown";
import { ExtractionBadge } from "./ExtractionBadge";

interface Column {
  key: string;
  label: string;
  align?: "right";
}

const COLUMNS: Column[] = [
  { key: "date", label: "Date" },
  { key: "merchant", label: "Merchant" },
  { key: "category", label: "Category" },
  { key: "account", label: "Account" },
  { key: "amount", label: "Amount", align: "right" },
];

interface TransactionsTableProps {
  transactions: Transaction[];
  filters: TransactionFilters;
  onFiltersChange: (filters: TransactionFilters) => void;
  onCategoryChange: (id: string, category: string) => void;
}

export function TransactionsTable({ transactions, filters, onFiltersChange, onCategoryChange }: TransactionsTableProps) {
  const sortBy = filters.sort_by ?? "date";
  const sortDir = filters.sort_dir ?? "desc";

  function toggleSort(key: string) {
    if (sortBy === key) {
      onFiltersChange({ ...filters, sort_by: key, sort_dir: sortDir === "asc" ? "desc" : "asc" });
    } else {
      onFiltersChange({ ...filters, sort_by: key, sort_dir: "desc" });
    }
  }

  if (transactions.length === 0) {
    return <p className="text-sm text-ink-secondary">No transactions match these filters.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-hairline">
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              onClick={() => toggleSort(col.key)}
              className={`cursor-pointer py-2 font-normal text-ink-secondary hover:text-ink ${
                col.align === "right" ? "text-right" : "text-left"
              }`}
            >
              {col.label}
              {sortBy === col.key && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-hairline">
        {transactions.map((t) => (
          <tr key={t.id} className={t.is_transfer ? "opacity-45" : ""}>
            <td className="py-2 whitespace-nowrap text-ink-secondary">{formatDate(t.date)}</td>
            <td className="py-2 text-ink">
              {t.merchant}
              <ExtractionBadge method={t.extraction_method} />
            </td>
            <td className="py-2">
              <CategoryDropdown value={t.category} onChange={(category) => onCategoryChange(t.id, category)} />
            </td>
            <td className="py-2 text-ink-secondary">{t.account}</td>
            <td className="py-2 text-right">
              <Money value={t.amount} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
