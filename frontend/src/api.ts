import type {
  Evidence,
  FactChange,
  IngestionJob,
  Product,
  QueryResult,
  SourceSummary,
  StagedSource,
  User,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL || "/api";
  const url = new URL(configured, window.location.origin);
  if (url.origin !== window.location.origin || url.search || url.hash || url.username || url.password) {
    throw new ApiError("API configuration must use the same origin as this application.", 0);
  }
  return url.pathname.replace(/\/$/, "");
}

async function request<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, { ...init, headers, redirect: "error" });
  } catch {
    throw new ApiError("Cannot reach the knowledge service. Please retry shortly.", 0);
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    if (token && response.status === 401) {
      window.dispatchEvent(new CustomEvent("rag:session-expired"));
    }
    const message = response.status === 429
      ? "Too many requests. Please wait a minute and try again."
      : response.status >= 500
        ? "Knowledge service is temporarily unavailable. Please retry shortly."
        : typeof payload?.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function login(username: string, password: string) {
  return request<{ access_token: string; expires_at: string; user: User }>("/auth/login", null, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export const api = {
  logout: (token: string) => request<void>("/auth/logout", token, { method: "POST" }),
  query: (token: string, question: string, debug: boolean) =>
    request<QueryResult>("/query", token, {
      method: "POST",
      body: JSON.stringify({ question, debug, top_k: 8 }),
    }),
  evidence: (token: string, chunkId: string) =>
    request<Evidence>(`/evidence/${encodeURIComponent(chunkId)}`, token),
  products: (token: string, search = "", category = "") => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (category) params.set("category", category);
    return request<Product[]>(`/products?${params.toString()}`, token);
  },
  productHistory: (token: string, productId: string, field = "") => {
    const params = field ? `?field_name=${encodeURIComponent(field)}` : "";
    return request<{
      facts: Product["facts"];
      changes: FactChange[];
      conflicts: Array<Record<string, unknown>>;
    }>(`/products/${encodeURIComponent(productId)}/history${params}`, token);
  },
  changes: (token: string, status = "pending") =>
    request<FactChange[]>(`/knowledge/fact-changes?status=${encodeURIComponent(status)}`, token),
  change: (token: string, id: string) =>
    request<FactChange>(`/knowledge/fact-changes/${encodeURIComponent(id)}`, token),
  decide: (token: string, id: string, action: "approve" | "reject" | "supersede", reason: string) =>
    request<FactChange>(`/knowledge/fact-changes/${encodeURIComponent(id)}/${action}`, token, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  sources: (token: string) => request<SourceSummary[]>("/admin/sources", token),
  stagedSources: (token: string) => request<StagedSource[]>("/admin/staged-sources", token),
  stageSource: (token: string, file: File) => {
    const body = new FormData();
    body.set("file", file);
    return request<StagedSource>("/admin/staged-sources", token, { method: "POST", body });
  },
  proposeStaged: (token: string, id: string) =>
    request<{ source: StagedSource; changes: FactChange[] }>(
      `/admin/staged-sources/${encodeURIComponent(id)}/propose`,
      token,
      { method: "POST" },
    ),
  ingest: (token: string) =>
    request<IngestionJob>("/admin/ingestions", token, { method: "POST" }),
  ingestionJobs: (token: string) => request<IngestionJob[]>("/admin/ingestion-jobs", token),
  ingestionJob: (token: string, id: string) =>
    request<IngestionJob>(`/admin/ingestion-jobs/${encodeURIComponent(id)}`, token),
  cancelIngestion: (token: string, id: string) =>
    request<IngestionJob>(`/admin/ingestion-jobs/${encodeURIComponent(id)}/cancel`, token, {
      method: "POST",
    }),
};
