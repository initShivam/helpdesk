const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export async function apiJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...options,
  });
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
