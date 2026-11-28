import { useAuthStore } from '~/stores/auth'
import type { PanelUser } from '~/stores/auth'

/**
 * Global route guard. Authentication is enforced before any page renders, so
 * no route can fire authenticated API calls or draw its UI while anonymous
 * (previously the only check was a post-mount `token exists` test in the
 * layout, which every page mounted before).
 *
 * The session is validated server-side against the HttpOnly access_token
 * cookie rather than trusting a client-side flag.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  const config = useRuntimeConfig()

  if (to.path === '/login') {
    // Signed-in users do not need the login screen.
    if (auth.isAuthenticated) return '/'
    return
  }

  // Always refresh and validate session against backend
  try {
    const res = await fetch(`${config.public.apiBase}/auth/me`, {
      credentials: 'same-origin',
      headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
    })
    if (res.ok) {
      const data = (await res.json()) as (PanelUser & { access_token?: string })
      auth.setUser(data, data.access_token)
    } else if (res.status === 401) {
      auth.clearSession()
      return '/login'
    }
  } catch {
    if (!auth.isAuthenticated) {
      auth.clearSession()
      return '/login'
    }
  }

  if (!auth.isAuthenticated) return '/login'
})
