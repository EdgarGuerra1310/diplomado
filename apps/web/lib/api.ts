import { AnalyticsOverview, CaseDetail, CaseSummary } from "@/lib/types";

export const API_URL = "/api/backend";
const INTERNAL_API_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const baseUrl = typeof window === "undefined" ? INTERNAL_API_URL : API_URL;
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) throw new Error(`Error API ${response.status}`);
  return response.json() as Promise<T>;
}

export const getCases = () => apiFetch<CaseSummary[]>("/cases");
export const getCase = (id: string) => apiFetch<CaseDetail>(`/cases/${id}`);
export const seedDemo = () => apiFetch<CaseDetail>("/demo/seed", { method: "POST" });
export const getAnalytics = () => apiFetch<AnalyticsOverview>("/analytics/overview");
