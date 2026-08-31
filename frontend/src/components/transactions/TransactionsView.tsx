import { useCallback, useEffect, useState } from "react";
import { getTransactions, patchTransaction } from "../../lib/api";
import type { Transaction, TransactionFilters, TransactionsPage } from "../../lib/types";
import { Button } from "../shared/Button";
import { FilterBar } from "./FilterBar";
import { TransactionsTable } from "./TransactionsTable";

const PAGE_SIZE = 50;

export function TransactionsView() {
  const [filters, setFilters] = useState<TransactionFilters>({ page: 1, page_size: PAGE_SIZE, include_transfers: true });
  const [data, setData] = useState<TransactionsPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    return getTransactions(filters)
      .then(setData)
      .catch((e) => setError(e.message ?? "Failed to load transactions."));
  }, [filters]);

  useEffect(() => {
    let cancelled = false;
    getTransactions(filters)
      .then((page) => {
        if (!cancelled) setData(page);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message ?? "Failed to load transactions.");
      });
    return () => {
      cancelled = true;
    };
  }, [filters]);

  async function handleCategoryChange(id: string, category: string) {
    if (!data) return;
    // Optimistic update for the edited row only -- a manual override also
    // propagates to every other transaction sharing the same merchant
    // server-side, so re-fetch afterward to pick those up too rather than
    // trying to replicate that matching logic on the client.
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

  const page = filters.page ?? 1;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="animate-fade-in">
      <FilterBar filters={filters} onChange={setFilters} />

      {error && <p className="mb-4 text-sm text-accent">{error}</p>}

      {data && (
        <TransactionsTable
          transactions={data.transactions}
          filters={filters}
          onFiltersChange={setFilters}
          onCategoryChange={handleCategoryChange}
        />
      )}

      {data && data.total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-between text-sm text-ink-secondary">
          <span>
            {data.total} transaction{data.total === 1 ? "" : "s"}
          </span>
          <div className="flex items-center gap-3">
            <Button disabled={page <= 1} onClick={() => setFilters({ ...filters, page: page - 1 })}>
              Previous
            </Button>
            <span className="tabular-nums">
              {page} / {totalPages}
            </span>
            <Button disabled={page >= totalPages} onClick={() => setFilters({ ...filters, page: page + 1 })}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
