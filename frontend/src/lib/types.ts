// Mirrors backend/models.py. Money fields are strings -- parsed only for
// display formatting (see format.ts), never for arithmetic. Every number a
// user sees was computed in Python; the frontend just renders it.

export type ExtractionMethod = "regex" | "csv" | "llm";
export type CategorySource = "llm" | "cache" | "manual" | "rule" | "uncategorized";
export type ReconciliationStatus = "ok" | "warning" | "not_applicable";

export interface Period {
  period: string; // "YYYY-MM"
  transaction_count: number;
}

export interface Transaction {
  id: string;
  date: string;
  description: string;
  merchant: string;
  merchant_normalized: string;
  amount: string;
  account: string;
  source_file: string;
  extraction_method: ExtractionMethod;
  category: string | null;
  subcategory: string | null;
  confidence: number | null;
  is_transfer: boolean;
  category_source: CategorySource;
}

export interface HealthResponse {
  status: string;
  statements_dir: string;
  dir_exists: boolean;
  file_count: number;
  llm_provider: string;
  llm_authenticated: boolean;
  llm_auth_detail: string | null;
}

export interface ReconciliationWarning {
  file_id: number;
  filename: string;
  status: ReconciliationStatus;
  delta: string;
  detail: string | null;
}

export type FixRequestTrigger = "reconciliation_warning" | "low_extraction";

export interface FixRequest {
  id: number;
  file_id: number;
  filename: string;
  trigger: FixRequestTrigger;
  signal_detail: string;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
  resolved_at: string | null;
}

export interface CategoryTotal {
  category: string;
  total: string;
  percent: number;
  delta_vs_prior: string | null;
}

export interface MerchantTotal {
  merchant: string;
  count: number;
  total: string;
}

export interface DailyPoint {
  date: string;
  total_out: string;
}

export interface SummaryPayload {
  period: string;
  total_in: string;
  total_out: string;
  net: string;
  transaction_count: number;
  days_covered: number;
  category_totals: CategoryTotal[];
  top_merchants: MerchantTotal[];
  largest_transactions: Transaction[];
  daily_series: DailyPoint[];
  reconciliation_warnings: ReconciliationWarning[];
  narrative_markdown: string | null;
}

export interface JobEvent {
  type: "progress" | "done" | "error";
  stage?: string | null;
  message?: string | null;
  current?: number | null;
  total?: number | null;
  data?: Record<string, unknown> | null;
}

export interface TransactionsPage {
  transactions: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface TransactionFilters {
  category?: string;
  account?: string;
  date_from?: string;
  date_to?: string;
  min_amount?: string;
  max_amount?: string;
  merchant?: string;
  include_transfers?: boolean;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}
