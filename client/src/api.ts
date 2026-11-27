// The bearer token is kept in memory only. Persisting it in localStorage would
// expose a full-privilege session token to any XSS payload (and to any other
// script running on the page) for the lifetime of the browser profile.
let authToken: string | null = null;

// Purge any token persisted by an older build so it cannot be replayed.
if (typeof localStorage !== 'undefined') {
  localStorage.removeItem('np_express_token');
}

export function getToken(): string | null {
  return authToken;
}

export function setToken(token: string) {
  authToken = token;
}

export function clearToken() {
  authToken = null;
}

export async function apiFetch<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const isFormData = options.body instanceof FormData;
  if (!isFormData && options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`/api${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || 'Request failed');
  }
  return res.json();
}
