<template>
  <div class="space-y-4">
    <!-- Upstream Update Notification -->
    <div
      v-if="updateInfo?.update_available && !updateDismissed"
      class="rounded-lg border border-amber-300 bg-amber-50 p-4"
    >
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex items-start gap-3">
          <div class="w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center shrink-0">
            <ArrowUpCircle class="w-5 h-5" />
          </div>
          <div>
            <p class="text-sm font-bold text-amber-900">Update available for NexoPanel</p>
            <p class="text-[11px] text-amber-800 mt-0.5">
              Installed
              <span class="font-mono">{{ updateInfo.current_commit_short || 'v' + updateInfo.current_version }}</span>
              · Upstream
              <span class="font-mono">{{ updateInfo.latest_commit_short || updateInfo.latest_version }}</span>
              <span v-if="updateInfo.commits_behind"> · {{ updateInfo.commits_behind }} commit(s) behind</span>
            </p>
            <p v-if="updateInfo.latest_commit_message" class="text-[11px] text-amber-800 mt-1">
              Latest: <span class="font-medium">{{ updateInfo.latest_commit_message }}</span>
            </p>
            <div v-if="updateInfo.recent_commits?.length" class="mt-2 space-y-0.5">
              <p class="text-[10px] font-semibold uppercase tracking-wide text-amber-800">Recent upstream commits</p>
              <div
                v-for="c in updateInfo.recent_commits.slice(0, 3)"
                :key="c.sha"
                class="flex items-center gap-2 text-[11px] text-amber-900"
              >
                <span class="font-mono text-[10px] bg-amber-100 rounded px-1 shrink-0">{{ c.short_sha }}</span>
                <span class="truncate">{{ c.message }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <a :href="updateInfo.repo_url" target="_blank" rel="noopener" class="np-btn-secondary">View changes</a>
          <button @click="dismissUpdate" class="np-btn-secondary">Dismiss</button>
        </div>
      </div>
      <div class="mt-3 rounded border border-amber-200 bg-white/70 p-2.5">
        <p class="text-[11px] font-semibold text-slate-700">How to update (run on the server as root):</p>
        <div class="flex items-center gap-2 mt-1">
          <code class="flex-1 text-[11px] font-mono text-slate-800 break-all">{{ updateInfo.update_command }}</code>
          <button @click="copyUpdateCommand" class="text-emerald-700 hover:underline text-[11px] font-medium shrink-0">
            {{ copied ? 'Copied' : 'Copy' }}
          </button>
        </div>
        <p class="text-[10px] text-slate-500 mt-1">
          Installed from a release tarball (no git checkout)? Reinstall with the one-line installer instead.
        </p>
      </div>
    </div>
    <div
      v-else-if="updateInfo?.error && !updateDismissed"
      class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500 flex items-center justify-between"
    >
      <span>Update check unavailable: {{ updateInfo.error }}</span>
      <button @click="loadUpdateStatus(true)" class="text-emerald-600 hover:underline font-medium">Retry</button>
    </div>

    <!-- Radial Gauges Row -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div v-for="gauge in gauges" :key="gauge.label" class="np-card p-4 flex items-center justify-between">
        <div>
          <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{{ gauge.label }}</p>
          <p class="text-xl font-bold text-slate-900 mt-1">{{ gauge.display }}</p>
          <p class="text-[11px] text-slate-500 mt-0.5">{{ gauge.sub }}</p>
        </div>
        <svg class="w-14 h-14 -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e2e8f0" stroke-width="3" />
          <circle
            cx="18"
            cy="18"
            r="15.5"
            fill="none"
            :stroke="gauge.color"
            stroke-width="3"
            stroke-dasharray="97.4"
            :stroke-dashoffset="97.4 - (97.4 * Math.min(gauge.percent, 100)) / 100"
            stroke-linecap="round"
          />
        </svg>
      </div>
    </div>

    <!-- Services & Network Sparkline -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="np-card p-4 lg:col-span-2">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-600">System Services (Delegated)</h2>
          <button @click="loadDashboard" class="np-btn-secondary">Refresh</button>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          <div v-for="svc in services" :key="svc.name" class="p-2.5 rounded border border-slate-200 bg-slate-50 flex items-center justify-between">
            <div>
              <p class="text-xs font-semibold text-slate-800">{{ svc.name }}</p>
              <span
                :class="svc.status === 'active' ? 'text-emerald-600' : 'text-amber-600'"
                class="text-[11px] font-medium"
              >
                ● {{ svc.status }}
              </span>
            </div>
            <div class="flex gap-1">
              <button @click="controlSvc(svc.name, 'restart')" class="px-1.5 py-0.5 text-[10px] bg-white border border-slate-300 rounded hover:bg-slate-100">
                Restart
              </button>
              <button @click="controlSvc(svc.name, svc.status === 'active' ? 'stop' : 'start')" class="px-1.5 py-0.5 text-[10px] bg-white border border-slate-300 rounded hover:bg-slate-100">
                {{ svc.status === 'active' ? 'Stop' : 'Start' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="np-card p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-600 mb-3">Network I/O (Live)</h2>
        <div class="space-y-2 text-xs">
          <div class="flex justify-between">
            <span class="text-slate-500">Total Sent</span>
            <span class="font-mono font-semibold">{{ formatBytes(telemetry?.network?.bytes_sent || 0) }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-slate-500">Total Received</span>
            <span class="font-mono font-semibold">{{ formatBytes(telemetry?.network?.bytes_recv || 0) }}</span>
          </div>
        </div>
        <svg class="w-full h-24 mt-3 bg-slate-50 rounded border border-slate-200" viewBox="0 0 200 60" preserveAspectRatio="none">
          <polyline fill="none" stroke="#10b981" stroke-width="2" :points="sparklinePoints" />
        </svg>
      </div>
    </div>

    <!-- Recent Audit Events -->
    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
        <h2 class="text-xs font-semibold uppercase tracking-wider text-slate-600">Recent Audit Events</h2>
        <NuxtLink to="/security" class="text-xs text-emerald-600 hover:underline">View All</NuxtLink>
      </div>
      <table class="np-table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Actor</th>
            <th>Action</th>
            <th>Target</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in auditLogs" :key="log.id">
            <td class="font-mono text-[11px]">{{ new Date(log.timestamp).toLocaleString() }}</td>
            <td>{{ log.actor_username }}</td>
            <td class="font-medium">{{ log.action }}</td>
            <td class="font-mono text-[11px]">{{ log.target_resource }}</td>
            <td>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700">{{ log.status }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowUpCircle } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const { apiFetch, wsBase } = useApi()
const auth = useAuthStore()

const telemetry = ref<any>(null)
const services = ref<any[]>([])
const auditLogs = ref<any[]>([])
const cpuHistory = ref<number[]>([15, 22, 18, 25, 20, 30, 24, 19])
const updateInfo = ref<any>(null)
const updateDismissed = ref(false)
const copied = ref(false)
let ws: WebSocket | null = null

const gauges = computed(() => {
  const t = telemetry.value
  const cpu = t?.cpu_percent ?? 0
  const mem = t?.memory?.percent ?? 0
  const disk = t?.disk?.percent ?? 0
  const load = t?.load_average?.[0] ?? 0
  const cores = t?.cpu_cores ?? 1
  return [
    { label: 'CPU Usage', display: `${cpu}%`, sub: `${cores} vCPU Cores`, percent: cpu, color: '#10b981' },
    { label: 'Memory (RAM)', display: `${mem}%`, sub: `${formatBytes(t?.memory?.used || 0)} / ${formatBytes(t?.memory?.total || 0)}`, percent: mem, color: '#3b82f6' },
    { label: 'Disk (/)', display: `${disk}%`, sub: `${formatBytes(t?.disk?.used || 0)} / ${formatBytes(t?.disk?.total || 0)}`, percent: disk, color: '#8b5cf6' },
    { label: 'Load Avg (1m)', display: `${load}`, sub: `Capacity: ${cores}.00`, percent: Math.min((load / cores) * 100, 100), color: '#f59e0b' },
  ]
})

const sparklinePoints = computed(() => {
  return cpuHistory.value
    .map((val, idx) => `${(idx / Math.max(cpuHistory.value.length - 1, 1)) * 200},${60 - (Math.min(val, 100) / 100) * 55}`)
    .join(' ')
})

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

async function loadDashboard() {
  const [t, s, a] = await Promise.all([
    apiFetch('/system/telemetry'),
    apiFetch<any[]>('/system/services'),
    apiFetch<any[]>('/system/audit-logs?limit=8'),
  ])
  telemetry.value = t
  services.value = s
  auditLogs.value = a
}

async function controlSvc(service: string, action: string) {
  await apiFetch('/system/services/control', { method: 'POST', body: { service, action } })
  services.value = await apiFetch<any[]>('/system/services')
}

async function loadUpdateStatus(force = false) {
  try {
    updateInfo.value = await apiFetch<any>(`/system/updates${force ? '?force=true' : ''}`)
    if (typeof localStorage !== 'undefined' && updateInfo.value?.latest_commit) {
      updateDismissed.value = localStorage.getItem('np_update_dismissed') === updateInfo.value.latest_commit
    }
  } catch {
    updateInfo.value = null
  }
}

function dismissUpdate() {
  updateDismissed.value = true
  if (typeof localStorage !== 'undefined' && updateInfo.value?.latest_commit) {
    localStorage.setItem('np_update_dismissed', updateInfo.value.latest_commit)
  }
}

async function copyUpdateCommand() {
  if (!updateInfo.value?.update_command || !navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(updateInfo.value.update_command)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // Clipboard permission denied; the command remains selectable in the UI.
  }
}

onMounted(async () => {
  loadUpdateStatus()
  await loadDashboard()
  if (auth.isAuthenticated) {
    // Cookie-authenticated socket: the JWT is never placed in the URL.
    ws = new WebSocket(`${wsBase}/system/telemetry/ws`)
    ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data)
      telemetry.value = data
      cpuHistory.value = [...cpuHistory.value.slice(-19), data.cpu_percent]
    }
  }
})

onUnmounted(() => {
  ws?.close()
})
</script>
