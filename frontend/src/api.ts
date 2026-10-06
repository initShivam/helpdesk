const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
export const AUTH_TOKEN_STORAGE_KEY = 'helpdesk-auth-token';
export const AUTH_INVALID_EVENT = 'helpdesk:auth-invalid';

export function getAuthToken(): string | null {
  return window.sessionStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function setAuthToken(token: string): void {
  window.sessionStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

export function clearAuthToken(): void {
  window.sessionStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

export async function apiFetch(path: string, options?: RequestInit): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(options?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const apiOrigin = new URL(API_BASE_URL || window.location.origin, window.location.origin).origin;
  let url = new URL(path, API_BASE_URL || window.location.origin);
  if (!API_BASE_URL && url.origin !== window.location.origin) {
    if (!url.pathname.startsWith('/api/')) {
      throw new Error('Refusing to send authentication credentials to another origin.');
    }
    url = new URL(`${url.pathname}${url.search}${url.hash}`, window.location.origin);
  }
  if (url.origin !== apiOrigin) {
    throw new Error('Refusing to send authentication credentials to another origin.');
  }

  const response = await fetch(url.toString(), {
    ...options,
    credentials: 'omit',
    headers,
  });

  if (response.status === 401 && token && getAuthToken() === token) {
    clearAuthToken();
    window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
  }
  return response;
}

export async function apiJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    const errorData = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(errorData?.detail || `Request failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function getCsrfToken(): Promise<string> {
  const data = await apiJson<{ csrfToken: string }>('/api/auth/csrf/');
  return data.csrfToken;
}

export { API_BASE_URL };
