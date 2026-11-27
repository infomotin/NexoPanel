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
    token: (typeof localStorage !== 'undefined' ? localStorage.getItem('nexopanel_token') : null) as string | null,
    user: null as PanelUser | null,
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
      if (typeof localStorage !== 'undefined' && token) {
        localStorage.setItem('nexopanel_token', token)
      }
    },
    setUser(user: PanelUser | null, token?: string) {
      this.user = user
      this.sessionChecked = true
      if (token) {
        this.token = token
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('nexopanel_token', token)
        }
      }
    },
    clearSession() {
      this.token = null
      this.user = null
      this.sessionChecked = false
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('nexopanel_token')
      }
    },
  },
})
