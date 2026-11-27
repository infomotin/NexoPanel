import { defineStore } from 'pinia'

export interface PanelUser {
  id: number
  username: string
  email: string
  role: string
  permissions: string[]
  totp_enabled: boolean
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    // The JWT is held in memory only. It is never written to localStorage or
    // sessionStorage, so an XSS payload cannot exfiltrate it; after a page
    // reload the session is restored from the HttpOnly `access_token` cookie
    // (set by the backend) via `GET /auth/me`.
    token: null as string | null,
    user: null as PanelUser | null,
    // True once the session has been confirmed against the server.
    sessionChecked: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.user),
    can: (state) => (perm: string) => {
      if (!state.user) return false
      return state.user.permissions.includes('*') || state.user.permissions.includes(perm)
    },
  },
  actions: {
    setSession(token: string, user: PanelUser) {
      this.token = token
      this.user = user
      this.sessionChecked = true
    },
    setUser(user: PanelUser | null) {
      this.user = user
      this.sessionChecked = true
    },
    clearSession() {
      this.token = null
      this.user = null
      this.sessionChecked = false
    },
  },
})
