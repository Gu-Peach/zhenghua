import { useSessionStore } from "@/stores/session-store";
import type { LoginResult } from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(path, {
    ...options,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(options?.body instanceof Blob ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options?.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string | { message?: string } } | null;
    if (response.status === 401) useSessionStore.getState().clearSession();
    throw new ApiError(typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || response.statusText, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

let refreshInFlight: Promise<void> | null = null;
export async function authenticatedFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const send = () => fetch(`${API_BASE_URL}${path}`, { ...options, credentials: "include", headers: { ...options.headers, ...authHeaders() } });
  let response = await send();
  if (response.status === 401 && !path.startsWith("/api/v1/auth/")) {
    await restoreSession();
    if (useSessionStore.getState().session) response = await send();
  }
  return response;
}


export function authHeaders(): Record<string, string> {
  const token = useSessionStore.getState().session?.accessToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function restoreSession(): Promise<void> {
  if (!refreshInFlight) refreshInFlight = performRestoreSession().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

async function performRestoreSession(): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, { method: "POST", credentials: "include" });
    if (response.ok) useSessionStore.getState().setSession(await response.json() as LoginResult);
    else useSessionStore.getState().clearSession();
  } catch (error) {
    useSessionStore.getState().clearSession();
    throw error;
  } finally { useSessionStore.getState().setInitialized(); }
}
