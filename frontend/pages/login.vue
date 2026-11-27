<template>
  <div class="min-h-screen bg-[#111827] flex items-center justify-center p-4">
    <div class="w-full max-w-sm bg-white rounded-lg shadow-xl border border-slate-200 p-6">
      <div class="flex items-center gap-2.5 mb-6">
        <div class="w-8 h-8 rounded bg-emerald-600 flex items-center justify-center text-white font-bold">N</div>
        <div>
          <h1 class="text-base font-bold text-slate-900">NexoPanel</h1>
          <p class="text-[11px] text-slate-500">Linux Server Control Plane</p>
        </div>
      </div>

      <div v-if="errorMsg" class="mb-4 p-2.5 text-xs bg-rose-50 text-rose-700 border border-rose-200 rounded">
        {{ errorMsg }}
      </div>

      <form v-if="!requires2fa" @submit.prevent="submitLogin" class="space-y-3">
        <div>
          <label class="block text-xs font-medium text-slate-700 mb-1">Username</label>
          <input v-model="username" type="text" class="np-input" required autofocus />
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-700 mb-1">Password</label>
          <input v-model="password" type="password" class="np-input" required />
        </div>
        <button type="submit" :disabled="loading" class="w-full np-btn-primary justify-center py-2">
          {{ loading ? 'Authenticating...' : 'Sign In' }}
        </button>
      </form>

      <form v-else @submit.prevent="submit2fa" class="space-y-3">
        <p class="text-xs text-slate-600">Enter your 6-digit TOTP authenticator code or a single-use recovery code.</p>
        <div>
          <label class="block text-xs font-medium text-slate-700 mb-1">2FA / Recovery Code</label>
          <input v-model="totpCode" type="text" class="np-input" placeholder="123456" required autofocus />
        </div>
        <button type="submit" :disabled="loading" class="w-full np-btn-primary justify-center py-2">
          Verify & Continue
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

definePageMeta({ layout: false })

const { apiFetch } = useApi()
const auth = useAuthStore()

const username = ref('admin')
const password = ref('')
const totpCode = ref('')
const partialToken = ref('')
const requires2fa = ref(false)
const loading = ref(false)
const errorMsg = ref('')

async function submitLogin() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await apiFetch<any>('/auth/login', {
      method: 'POST',
      body: { username: username.value, password: password.value },
    })
    if (res.requires_2fa) {
      requires2fa.value = true
      partialToken.value = res.partial_token
    } else {
      auth.setSession(res.access_token, res.user)
      navigateTo('/')
    }
  } catch (err: any) {
    errorMsg.value = err.message || 'Login failed'
  } finally {
    loading.value = false
  }
}

async function submit2fa() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await apiFetch<any>('/auth/2fa/verify', {
      method: 'POST',
      body: { partial_token: partialToken.value, code: totpCode.value },
    })
    auth.setSession(res.access_token, res.user)
    navigateTo('/')
  } catch (err: any) {
    errorMsg.value = err.message || '2FA verification failed'
  } finally {
    loading.value = false
  }
}
</script>
