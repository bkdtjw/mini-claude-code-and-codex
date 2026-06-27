const API_AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN || "";
const AUTH_STORAGE_KEY = "agent-studio.auth-token";
const DEFAULT_AUTH_TOKEN = "change-me-in-production";

interface ApiErrorPayload {
  detail?: { message?: string };
  message?: string;
}

interface AuthorizedFetchResult {
  response: Response;
  data: unknown;
}

const readStoredAuthToken = (): string => {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(AUTH_STORAGE_KEY)?.trim() ?? "";
  } catch {
    return "";
  }
};

const clearStoredAuthToken = (expectedToken: string): void => {
  if (typeof window === "undefined") return;
  try {
    if (readStoredAuthToken() === expectedToken) {
      window.localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in hardened browser contexts.
  }
};

const getAuthToken = (): string => API_AUTH_TOKEN || readStoredAuthToken() || DEFAULT_AUTH_TOKEN;

const getRetryAuthToken = (primaryToken: string): string => {
  if (API_AUTH_TOKEN || primaryToken === DEFAULT_AUTH_TOKEN) return "";
  const storedToken = readStoredAuthToken();
  if (!storedToken || storedToken !== primaryToken) return "";
  return DEFAULT_AUTH_TOKEN;
};

const readResponseData = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  return text ? JSON.parse(text) : null;
};

export const getApiErrorMessage = (data: unknown, status: number): string => {
  const payload = data as ApiErrorPayload | null;
  return payload?.detail?.message ?? payload?.message ?? `Request failed: ${status}`;
};

export const authorizedFetchJson = async (url: string, options: RequestInit = {}): Promise<AuthorizedFetchResult> => {
  const originalHeaders = new Headers(options.headers);
  const hasCallerAuth = originalHeaders.has("Authorization");

  const send = async (token: string): Promise<AuthorizedFetchResult> => {
    const headers = new Headers(options.headers);
    if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(url, { ...options, headers });
    return { response, data: await readResponseData(response) };
  };

  const primaryToken = getAuthToken();
  let result = await send(primaryToken);
  if (!hasCallerAuth && result.response.status === 401) {
    const retryToken = getRetryAuthToken(primaryToken);
    if (retryToken) {
      result = await send(retryToken);
      if (result.response.ok) clearStoredAuthToken(primaryToken);
    }
  }
  return result;
};
