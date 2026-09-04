import { useCallback, useEffect, useMemo, useState } from "react";
import { getTransactions, patchTransaction } from "../../lib/api";
import type { Transaction, TransactionFilters, TransactionsPage } from "../../lib/types";
import { formatDateLong } from "../../lib/format";
import { TransactionsTable } from "../transactions/TransactionsTable";

interface DailyTransactionsPanelProps {
  date: string;
  onClose: () => void;
}

export function DailyTransactionsPanel({ date, onClose }: DailyTransactionsPanelProps) {
  const [sort, setSort] = useState<{ sort_by: string; sort_dir: "asc" | "desc" }>({
    sort_by: "date",
    sort_dir: "desc",
  });
  const [data, setData] = useState<TransactionsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filters: TransactionFilters = useMemo(
    () => ({
      date_from: date,
      date_to: date,
      page: 1,
      page_size: 200,
      include_transfers: false,
      sort_by: sort.sort_by,
      sort_dir: sort.sort_dir,
    }),
    [date, sort.sort_by, sort.sort_dir],
  );

  const refetch = useCallback(() => {
    return getTransactions(filters)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load transactions."));
  }, [filters]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getTransactions(filters)
      .then((page) => {
        if (!cancelled) setData(page);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load transactions.");
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  async function handleCategoryChange(id: string, category: string) {
    if (!data) return;
    const optimistic: Transaction[] = data.transactions.map((t) =>
      t.id === id ? { ...t, category, category_source: "manual" } : t,
    );
    setData({ ...data, transactions: optimistic });
    try {
      await patchTransaction(id, category);
      await refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save category.");
    }
  }

  function handleFiltersChange(next: TransactionFilters) {
    setSort({ sort_by: next.sort_by ?? "date", sort_dir: next.sort_dir ?? "desc" });
  }

  return (
    <div className="mt-6 border-t border-hairline pt-6">
      <div className="mb-4 flex items-baseline justify-between">
        <h3 className="text-sm text-ink-secondary">
          {formatDateLong(date)}
          {data && ` · ${data.total} transaction${data.total === 1 ? "" : "s"}`}
        </h3>
        <button onClick={onClose} className="text-sm text-ink-secondary hover:text-ink" aria-label="Close">
          Close
        </button>
      </div>

      {error && <p className="text-sm text-accent">{error}</p>}

      {data && (
        <TransactionsTable
          transactions={data.transactions}
          filters={filters}
          onFiltersChange={handleFiltersChange}
          onCategoryChange={handleCategoryChange}
        />
      )}
    </div>
  );
}
