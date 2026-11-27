<template>
  <div class="space-y-4">
    <h1 class="text-base font-bold text-slate-900">Security Hardening, 2FA & Audit Log</h1>

    <!-- 2FA TOTP Card -->
    <div class="np-card p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-xs font-bold text-slate-800">Two-Factor Authentication (TOTP RFC 6238)</h2>
          <p class="text-xs text-slate-500">Protect your account with an authenticator app and single-use recovery codes.</p>
        </div>
        <button v-if="!auth.user?.totp_enabled" @click="start2fa" class="np-btn-primary">Enable 2FA</button>
        <button v-else @click="disable2fa" class="np-btn-danger">Disable 2FA</button>
      </div>
      <div v-if="totpSetup" class="p-3 bg-slate-50 border border-slate-200 rounded flex gap-4 items-center">
        <img :src="totpSetup.qr_data_url" alt="TOTP QR" class="w-32 h-32 border bg-white p-1" />
        <div class="space-y-2 text-xs">
          <p>Scan QR code and enter the 6-digit verification code:</p>
          <input v-model="totpCode" placeholder="123456" class="np-input w-40" />
          <button @click="confirm2fa" class="np-btn-primary">Verify & Activate</button>
        </div>
      </div>
      <div v-if="recoveryCodes.length" class="p-3 bg-amber-50 border border-amber-200 rounded text-xs">
        <p class="font-bold text-amber-800 mb-1">Save these single-use recovery codes securely:</p>
        <div class="font-mono grid grid-cols-4 gap-1">{{ recoveryCodes.join('  ') }}</div>
      </div>
    </div>

    <!-- System Log Viewer -->
    <div class="np-card p-4 space-y-2">
      <div class="flex items-center justify-between">
        <h2 class="text-xs font-bold text-slate-800">Log Observability Viewer</h2>
        <div class="flex gap-2">
          <select v-model="logTarget" @change="loadLogs" class="np-input w-40">
            <option value="nginx_access">Nginx Access</option>
            <option value="nginx_error">Nginx Error</option>
            <option value="syslog">System Log</option>
            <option value="mail">Mail Log</option>
            <option value="nexopanel">NexoPanel Log</option>
          </select>
          <button @click="loadLogs" class="np-btn-secondary">Tail</button>
        </div>
      </div>
      <pre class="bg-slate-900 text-slate-200 p-3 rounded text-[11px] font-mono max-h-48 overflow-y-auto">{{ logLines.join('\n') || 'No log entries' }}</pre>
    </div>

    <!-- Immutable Audit Log -->
    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Immutable Audit Trail</div>
      <table class="np-table">
        <thead><tr><th>Timestamp</th><th>Actor</th><th>IP</th><th>Permission</th><th>Action</th><th>Resource</th><th>Status</th></tr></thead>
        <tbody>
          <tr v-for="l in auditLogs" :key="l.id">
            <td class="font-mono text-[11px]">{{ new Date(l.timestamp).toLocaleString() }}</td>
            <td>{{ l.actor_username }}</td>
            <td class="font-mono text-[11px]">{{ l.source_ip }}</td>
            <td class="font-mono text-[11px]">{{ l.permission }}</td>
            <td class="font-semibold">{{ l.action }}</td>
            <td class="font-mono text-[11px]">{{ l.target_resource }}</td>
            <td>{{ l.status }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch } = useApi()
const auditLogs = ref<any[]>([])
const totpSetup = ref<any>(null)
const totpCode = ref('')
const recoveryCodes = ref<string[]>([])
const logTarget = ref('nginx_error')
const logLines = ref<string[]>([])

async function load() {
  auditLogs.value = await apiFetch('/system/audit-logs?limit=100')
  await loadLogs()
}
async function loadLogs() {
  const res = await apiFetch<any>(`/system/logs/${logTarget.value}?lines=100`)
  logLines.value = res.lines
}
async function start2fa() {
  totpSetup.value = await apiFetch('/auth/2fa/setup', { method: 'POST' })
}
async function confirm2fa() {
  const res = await apiFetch<any>('/auth/2fa/enable', {
    method: 'POST',
    body: { secret: totpSetup.value.secret, code: totpCode.value },
  })
  recoveryCodes.value = res.recovery_codes
  totpSetup.value = null
  if (auth.user) auth.user.totp_enabled = true
}
async function disable2fa() {
  await apiFetch('/auth/2fa/disable', { method: 'POST' })
  if (auth.user) auth.user.totp_enabled = false
}
onMounted(load)
</script>
