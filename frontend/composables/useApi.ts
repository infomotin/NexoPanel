import { useAuthStore } from '~/stores/auth'

export function useApi() {
  const config = useRuntimeConfig()
  const auth = useAuthStore()

  async function apiFetch<T>(path: string, options: RequestInit & { method?: string; body?: any } = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    }
    if (auth.token) {
      headers['Authorization'] = `Bearer ${auth.token}`
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

  const dynamicWsBase = config.public.wsBase
    || (typeof window !== 'undefined'
      ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/v1`
      : 'ws://localhost:8443/api/v1')

  return { apiFetch, apiBase: config.public.apiBase, wsBase: dynamicWsBase }
}
