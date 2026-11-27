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
    token: (typeof localStorage !== 'undefined' ? localStorage.getItem('np_token') : null) as string | null,
    user: null as PanelUser | null,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    can: (state) => (perm: string) => {
      if (!state.user) return false
      return state.user.permissions.includes('*') || state.user.permissions.includes(perm)
    },
  },
  actions: {
    setSession(token: string, user: PanelUser) {
      this.token = token
      this.user = user
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('np_token', token)
      }
    },
    clearSession() {
      this.token = null
      this.user = null
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('np_token')
      }
    },
  },
})
