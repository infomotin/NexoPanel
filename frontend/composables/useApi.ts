import { useAuthStore } from '~/stores/auth'

export function useApi() {
  const config = useRuntimeConfig()
  const auth = useAuthStore()

  /** Read a (non-HttpOnly) cookie value, e.g. the double-submit CSRF token. */
  function readCookie(name: string): string | null {
    if (typeof document === 'undefined') return null
    const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`))
    return match ? decodeURIComponent(match[1]) : null
  }

  /**
   * Authenticate each request. A Bearer token is only present right after
   * login (it is kept in memory); after a reload the HttpOnly access_token
   * cookie authenticates the call instead, which requires the double-submit
   * `X-CSRF-Token` header on state-changing methods.
   */
  function authHeaders(method?: string): Record<string, string> {
    if (auth.token) return { Authorization: `Bearer ${auth.token}` }
    const mutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes((method || 'GET').toUpperCase())
    if (!mutating) return {}
    const csrf = readCookie('nexopanel_csrf')
    return csrf ? { 'X-CSRF-Token': csrf } : {}
  }

  async function apiFetch<T>(path: string, options: RequestInit & { method?: string; body?: any } = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
      ...authHeaders(options.method),
    }
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
    if (!isFormData && options.body && typeof options.body !== 'string') {
      headers['Content-Type'] = 'application/json'
    }

    const res = await fetch(`${config.public.apiBase}${path}`, {
      ...options,
      headers,
      body: !isFormData && options.body && typeof options.body !== 'string'
        ? JSON.stringify(options.body)
        : options.body,
    })

    if (res.status === 401) {
      auth.clearSession()
      navigateTo('/login')
      throw new Error('Unauthorized')
    }
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail))
    }
    return res.json() as Promise<T>
  }

  // Prefer a same-origin WebSocket endpoint so the HttpOnly access_token
  // cookie (SameSite=strict) is always sent. A configured base pointing at
  // another host would be cross-site, would drop the session cookie, and would
  // previously have forced the token to be passed in the URL query string
  // (leaking it into proxy/access logs).
  const dynamicWsBase = (() => {
    const configured = config.public.wsBase
    if (typeof window === 'undefined') {
      return configured || 'ws://localhost:8443/api/v1'
    }
    const sameOrigin = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1`
    if (!configured) return sameOrigin
    try {
      return new URL(configured).host === window.location.host ? configured : sameOrigin
    } catch {
      return sameOrigin
    }
  })()

  return { apiFetch, apiBase: config.public.apiBase, wsBase: dynamicWsBase }
}
