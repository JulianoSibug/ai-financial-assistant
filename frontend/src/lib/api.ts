import type {
  FixRequest,
  HealthResponse,
  Period,
  PeriodTotal,
  SummaryPayload,
  Transaction,
  TransactionFilters,
  TransactionsPage,
} from "./types";

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // response wasn't JSON -- fall back to statusText
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export function startIngest(): Promise<{ job_id: string }> {
  return request("/api/ingest", { method: "POST" });
}

export function startAnalyze(period?: string): Promise<{ job_id: string }> {
  const qs = period ? `?period=${encodeURIComponent(period)}` : "";
  return request(`/api/analyze${qs}`, { method: "POST" });
}

export function getSummary(period?: string): Promise<SummaryPayload> {
  const qs = period ? `?period=${encodeURIComponent(period)}` : "";
  return request<SummaryPayload>(`/api/summary${qs}`);
}

export async function getPeriods(): Promise<Period[]> {
  const { periods } = await request<{ periods: Period[] }>("/api/periods");
  return periods;
}

export async function getTrends(): Promise<PeriodTotal[]> {
  const { periods } = await request<{ periods: PeriodTotal[] }>("/api/trends");
  return periods;
}

export async function getFixRequests(): Promise<FixRequest[]> {
  const { fix_requests } = await request<{ fix_requests: FixRequest[] }>("/api/fix-requests");
  return fix_requests;
}

export function resolveFixRequest(id: number, status: "resolved" | "dismissed"): Promise<{ ok: boolean }> {
  return request(`/api/fix-requests/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function deleteFile(id: number): Promise<{ ok: boolean }> {
  return request(`/api/files/${id}`, { method: "DELETE" });
}

export function getTransactions(filters: TransactionFilters): Promise<TransactionsPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  }
  return request<TransactionsPage>(`/api/transactions?${params.toString()}`);
}

export function patchTransaction(
  id: string,
  category: string,
  subcategory?: string | null,
): Promise<{ transaction: Transaction; propagated_to: number }> {
  return request(`/api/transactions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ category, subcategory: subcategory ?? null }),
  });
}

export function exportUrl(format: "csv" | "md", period?: string): string {
  const params = new URLSearchParams({ format });
  if (period) params.set("period", period);
  return `/api/export?${params.toString()}`;
}

export { ApiError };
