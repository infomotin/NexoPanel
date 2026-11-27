<template>
  <div class="space-y-3 text-xs">
    <!-- Toast Notification -->
    <div
      v-if="toast"
      :class="toast.ok ? 'bg-emerald-600 border-emerald-700' : 'bg-rose-600 border-rose-700'"
      class="fixed top-14 right-5 z-50 px-4 py-2 rounded-md shadow-lg border text-white font-medium"
    >
      {{ toast.msg }}
    </div>

    <!-- FTP Address & Security Status Banner -->
    <div class="np-card p-3 flex flex-wrap items-center justify-between gap-3">
      <div class="flex items-center gap-2.5 text-slate-700">
        <span class="w-2 h-2 rounded-full bg-amber-400"></span>
        <span>FTP address:</span>
        <strong class="font-mono text-slate-900 bg-slate-100 px-2 py-0.5 rounded">{{ ftpAddress }}</strong>
        <button @click="copyText(ftpAddress, 'addr')" class="text-slate-500 hover:text-emerald-600 text-[11px] underline">
          {{ copiedKey === 'addr' ? 'Copied' : 'Copy' }}
        </button>
        <span class="text-slate-400 hidden sm:inline">| Passive Ports: {{ overview.passive_range }}</span>
      </div>
      <div class="flex items-center gap-2">
        <span
          v-if="overview.security?.weak_password_accounts?.length"
          @click="showSecurity = true"
          class="px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 cursor-pointer font-medium"
        >
          ⚠ {{ overview.security.weak_password_accounts.length }} Weak Password(s)
        </span>
        <span class="px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-700 font-medium flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          Pure-Ftpd
        </span>
      </div>
    </div>

    <!-- Action Toolbar -->
    <div class="np-card p-2.5 flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <button @click="openAddModal" class="np-btn-primary">Add FTP</button>
        <button @click="showPort = true" class="np-btn-secondary">Change FTP Port</button>
        <button @click="openLogAnalysis" class="np-btn-secondary">FTP log analysis</button>
        <button @click="showSecurity = true" class="np-btn-secondary">Security Config</button>
      </div>
      <div class="flex items-center gap-2">
        <input v-model="searchQuery" @keyup.enter="loadOverview" placeholder="FTP search..." class="np-input w-52" />
        <button @click="loadOverview" class="np-btn-secondary">Search</button>
      </div>
    </div>

    <!-- Main FTP Table -->
    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead>
          <tr>
            <th class="w-8"><input type="checkbox" @change="toggleAll($event)" /></th>
            <th>Username</th>
            <th>Password</th>
            <th>Status</th>
            <th>Document Root</th>
            <th>Quota</th>
            <th>Note</th>
            <th class="text-right">Operate</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in overview.items" :key="a.id">
            <td><input type="checkbox" :value="a.id" v-model="selectedIds" /></td>
            <td class="font-mono font-semibold text-slate-900">{{ a.username }}</td>
            <td class="font-mono">
              <div class="flex items-center gap-1.5">
                <span class="min-w-[80px]">{{ revealedPasswords[a.id] || '••••••••' }}</span>
                <button @click="toggleRevealPassword(a)" class="text-slate-500 hover:text-emerald-600 text-[11px] underline">
                  {{ revealedPasswords[a.id] ? 'Hide' : 'Show' }}
                </button>
                <button @click="copyAccountPassword(a)" class="text-slate-500 hover:text-blue-600 text-[11px] underline">
                  {{ copiedKey === `pw-${a.id}` ? 'Copied' : 'Copy' }}
                </button>
              </div>
            </td>
            <td>
              <button
                @click="toggleAccountStatus(a)"
                :class="a.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'"
                class="px-2 py-0.5 rounded text-[11px] font-medium"
              >
                {{ a.is_active ? '▶ Activated' : '⏸ Stopped' }}
              </button>
            </td>
            <td>
              <NuxtLink :to="`/files?path=${encodeURIComponent(a.home_directory)}`" class="font-mono text-[11px] text-emerald-600 hover:underline">
                📁 {{ a.home_directory }}
              </NuxtLink>
            </td>
            <td>
              <button @click="openQuotaModal(a)" class="underline decoration-dotted hover:text-emerald-600">
                {{ a.quota_mb ? `${a.used_mb || 0}/${a.quota_mb} MB` : 'Unlimited' }}
              </button>
            </td>
            <td>
              <input
                v-model="noteEdits[a.id]"
                @blur="saveNote(a)"
                @keyup.enter="saveNote(a)"
                placeholder="Edit notes"
                class="bg-transparent border border-transparent hover:border-slate-200 focus:border-emerald-500 focus:bg-white rounded px-1.5 py-0.5 w-32 text-xs"
              />
            </td>
            <td class="text-right space-x-2 text-[11px]">
              <button @click="openHomeModal(a)" class="text-emerald-600 hover:underline font-medium">Set Path</button>
              <span class="text-slate-300">|</span>
              <button @click="openPassModal(a)" class="text-emerald-600 hover:underline font-medium">Password</button>
              <span class="text-slate-300">|</span>
              <button @click="openUserLogs(a)" class="text-blue-600 hover:underline font-medium">Log</button>
              <span class="text-slate-300">|</span>
              <button @click="deleteAccount(a)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
          <tr v-if="!overview.items?.length">
            <td colspan="8" class="text-center py-8 text-slate-400">No FTP accounts found. Click "Add FTP" to create one.</td>
          </tr>
        </tbody>
      </table>

      <!-- Bottom Batch & Pagination Bar -->
      <div class="px-3 py-2 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <select v-model="batchAction" class="np-input w-36">
            <option value="">Please choose</option>
            <option value="delete">Delete</option>
          </select>
          <button @click="executeBatch" :disabled="!selectedIds.length || !batchAction" class="np-btn-secondary">Execute</button>
          <span class="text-slate-400">{{ selectedIds.length }} selected</span>
        </div>
        <span class="text-slate-500 font-medium">Total: {{ overview.total }}</span>
      </div>
    </div>

    <!-- Add FTP Modal -->
    <div v-if="showAdd" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 border border-slate-200 shadow-xl">
        <h3 class="text-sm font-bold">Add FTP User</h3>
        <input v-model="addForm.username" @input="onAddUsernameInput" placeholder="Username (letters, numbers, _)" class="np-input font-mono" />
        <div class="flex gap-2">
          <input v-model="addForm.password" placeholder="Password (min 6 chars)" class="np-input font-mono flex-1" />
          <button type="button" @click="addForm.password = genPass()" class="np-btn-secondary">Random</button>
        </div>
        <input v-model="addForm.home_directory" placeholder="/var/www/site" class="np-input font-mono" />
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="addForm.quota_mb" type="number" placeholder="0 (Unlimited MB)" class="np-input" />
          <input v-model="addForm.note" placeholder="Note" class="np-input" />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showAdd = false" class="np-btn-secondary">Cancel</button>
          <button @click="createAccount" class="np-btn-primary">Confirm</button>
        </div>
      </div>
    </div>

    <!-- Change FTP Port Modal -->
    <div v-if="showPort" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-sm space-y-3 shadow-xl">
        <h3 class="text-sm font-bold">Change FTP Port</h3>
        <input v-model.number="portInput" type="number" min="1" max="65535" class="np-input font-mono" />
        <p class="text-[11px] text-slate-500">Firewall port rules are automatically synced. Passive range: {{ overview.passive_range }}.</p>
        <div class="flex justify-end gap-2">
          <button @click="showPort = false" class="np-btn-secondary">Cancel</button>
          <button @click="savePort" class="np-btn-primary">Save</button>
        </div>
      </div>
    </div>

    <!-- Set Path + Migrate Modal -->
    <div v-if="homeModal.open" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <h3 class="text-sm font-bold">Change FTP User Home — {{ homeModal.row?.username }}</h3>
        <input v-model="homeModal.path" class="np-input font-mono" />
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" v-model="homeModal.migrate" />
          <span>Migrate existing directory data (cp -rp)</span>
        </label>
        <div class="flex justify-end gap-2">
          <button @click="homeModal.open = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveHome" class="np-btn-primary">Save</button>
        </div>
      </div>
    </div>

    <!-- Change Password Modal -->
    <div v-if="passModal.open" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <h3 class="text-sm font-bold">Change FTP Password — {{ passModal.row?.username }}</h3>
        <div class="flex gap-2">
          <input v-model="passModal.password" class="np-input font-mono flex-1" />
          <button type="button" @click="passModal.password = genPass()" class="np-btn-secondary">Random</button>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="passModal.open = false" class="np-btn-secondary">Cancel</button>
          <button @click="savePassword" class="np-btn-primary">Save</button>
        </div>
      </div>
    </div>

    <!-- Quota Modal -->
    <div v-if="quotaModal.open" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-sm space-y-3 shadow-xl">
        <h3 class="text-sm font-bold">Set Quota — {{ quotaModal.row?.username }}</h3>
        <input v-model.number="quotaModal.quota_mb" type="number" min="0" class="np-input font-mono" />
        <div class="flex justify-end gap-2">
          <button @click="quotaModal.open = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveQuota" class="np-btn-primary">Save</button>
        </div>
      </div>
    </div>

    <!-- Security Config Modal -->
    <div v-if="showSecurity" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <h3 class="text-sm font-bold">FTP Security Hardening</h3>
        <label class="flex items-center justify-between p-2 border rounded">
          <span>Disable Anonymous Login (NoAnonymous yes)</span>
          <input type="checkbox" :checked="overview.security?.no_anonymous" @change="updateSec('no_anonymous', ($event.target as HTMLInputElement).checked)" />
        </label>
        <label class="flex items-center justify-between p-2 border rounded">
          <span>Forbid Root Login (MinUID 100)</span>
          <input type="checkbox" :checked="overview.security?.forbid_root" @change="updateSec('forbid_root', ($event.target as HTMLInputElement).checked)" />
        </label>
        <div class="flex justify-end"><button @click="showSecurity = false" class="np-btn-secondary">Close</button></div>
      </div>
    </div>

    <!-- User Logs Modal -->
    <div v-if="logsModal.open" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-2xl space-y-3 shadow-xl">
        <div class="flex justify-between items-center border-b pb-2">
          <h3 class="text-sm font-bold">FTP Logs — {{ logsModal.row?.username }}</h3>
          <button @click="logsModal.open = false" class="text-slate-400">✕</button>
        </div>
        <div class="flex gap-3 border-b pb-2">
          <button @click="switchLogTab('login')" :class="logsModal.tab === 'login' ? 'text-emerald-600 font-bold' : 'text-slate-500'">Login Log</button>
          <button @click="switchLogTab('action')" :class="logsModal.tab === 'action' ? 'text-emerald-600 font-bold' : 'text-slate-500'">Action Log</button>
        </div>
        <table v-if="logsModal.tab === 'login'" class="np-table">
          <thead><tr><th>User</th><th>IP</th><th>State</th><th>Login Time</th><th>Logout Time</th></tr></thead>
          <tbody>
            <tr v-for="l in loginLogs" :key="l.id"><td>{{ l.user }}</td><td class="font-mono">{{ l.ip }}</td><td>{{ l.status }}</td><td>{{ l.in_time }}</td><td>{{ l.out_time }}</td></tr>
            <tr v-if="!loginLogs.length"><td colspan="5" class="text-center text-slate-400 py-4">No login logs.</td></tr>
          </tbody>
        </table>
        <table v-else class="np-table">
          <thead><tr><th>User</th><th>IP</th><th>Document</th><th>Type</th><th>Time</th></tr></thead>
          <tbody>
            <tr v-for="l in actionLogs" :key="l.id"><td>{{ l.name }}</td><td class="font-mono">{{ l.ip }}</td><td class="font-mono">{{ l.file }}</td><td>{{ l.type }}</td><td>{{ l.time }}</td></tr>
            <tr v-if="!actionLogs.length"><td colspan="5" class="text-center text-slate-400 py-4">No action logs.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- FTP Log Analysis Scanner Modal -->
    <div v-if="analysisOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-2xl space-y-4 shadow-xl">
        <div class="flex justify-between items-center border-b pb-2">
          <h3 class="text-sm font-bold">FTP Log Scanning Tool</h3>
          <button @click="analysisOpen = false" class="text-slate-400">✕</button>
        </div>
        <div class="flex justify-between items-center">
          <span class="font-semibold">{{ scanned ? `Completed scan: ${scanRisks.length} risk record(s)` : 'Scan FTP login failures, abnormal areas, script uploads, and anonymous sessions.' }}</span>
          <div class="flex gap-2">
            <button @click="openWhitelist" class="np-btn-secondary">Whitelist</button>
            <button @click="runScan" class="np-btn-primary">Scan now</button>
          </div>
        </div>
        <table v-if="scanned" class="np-table">
          <thead><tr><th>Type</th><th>User</th><th>IP</th><th>Time</th><th>Operate</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in scanRisks" :key="i"><td class="text-rose-600">{{ r.type }}</td><td>{{ r.user }}</td><td class="font-mono">{{ r.ip }}</td><td>{{ r.exec_time }}</td><td><button @click="ignoreIp(r.ip)" class="text-emerald-600 underline">Ignore</button></td></tr>
            <tr v-if="!scanRisks.length"><td colspan="5" class="text-center text-emerald-600 py-4">No risks found.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Whitelist Modal -->
    <div v-if="whitelistOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex justify-between items-center"><h3 class="text-sm font-bold">FTP Log Whitelist</h3><button @click="whitelistOpen = false">✕</button></div>
        <div class="flex gap-2">
          <input v-model="newIp" placeholder="IP Address" class="np-input font-mono flex-1" />
          <button @click="addIp" class="np-btn-primary">Add</button>
        </div>
        <table class="np-table">
          <tbody>
            <tr v-for="ip in whitelistIps" :key="ip"><td class="font-mono">{{ ip }}</td><td class="text-right"><button @click="delIp(ip)" class="text-rose-600">Delete</button></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const overview = ref<any>({ items: [], total: 0, port: 21, passive_range: '39000-40000', security: { no_anonymous: true, forbid_root: true, weak_password_accounts: [] } })
const searchQuery = ref('')
const selectedIds = ref<number[]>([])
const batchAction = ref('')
const revealedPasswords = reactive<Record<number, string>>({})
const noteEdits = reactive<Record<number, string>>({})
const copiedKey = ref('')
const toast = ref<{ msg: string; ok: boolean } | null>(null)

const showAdd = ref(false)
const showPort = ref(false)
const showSecurity = ref(false)
const portInput = ref(21)
const addForm = reactive({ username: '', password: '', home_directory: '/var/www', quota_mb: 0, note: '' })
const homeModal = reactive<{ open: boolean; row: any; path: string; migrate: boolean }>({ open: false, row: null, path: '', migrate: false })
const passModal = reactive<{ open: boolean; row: any; password: string }>({ open: false, row: null, password: '' })
const quotaModal = reactive<{ open: boolean; row: any; quota_mb: number }>({ open: false, row: null, quota_mb: 0 })

const logsModal = reactive<{ open: boolean; row: any; tab: 'login' | 'action' }>({ open: false, row: null, tab: 'login' })
const loginLogs = ref<any[]>([])
const actionLogs = ref<any[]>([])

const analysisOpen = ref(false)
const scanned = ref(false)
const scanRisks = ref<any[]>([])
const whitelistOpen = ref(false)
const whitelistIps = ref<string[]>([])
const newIp = ref('')

const ftpAddress = computed(() => {
  const host = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1'
  return `ftp://${host}:${overview.value.port || 21}`
})

function notify(msg: string, ok = true) {
  toast.value = { msg, ok }
  setTimeout(() => { toast.value = null }, 3000)
}
function genPass(len = 14) {
  const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%'
  // CSPRNG: Math.random() is not cryptographically strong and must not mint
  // account credentials.
  const rnd = new Uint32Array(len)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(rnd)
  else for (let i = 0; i < len; i++) rnd[i] = Math.floor(Math.random() * 0xffffffff)
  return Array.from({ length: len }, (_, i) => chars[rnd[i] % chars.length]).join('')
}
function copyText(text: string, key: string) {
  navigator.clipboard?.writeText(text)
  copiedKey.value = key
  setTimeout(() => { copiedKey.value = '' }, 1500)
}
function onAddUsernameInput() {
  addForm.note = addForm.username
  addForm.home_directory = addForm.username ? `/var/www/${addForm.username}` : '/var/www'
}
function openAddModal() {
  addForm.username = ''
  addForm.password = genPass(12)
  addForm.home_directory = '/var/www'
  addForm.note = ''
  showAdd.value = true
}

async function loadOverview() {
  const data = await apiFetch(`/ftp/overview?search=${encodeURIComponent(searchQuery.value)}`)
  overview.value = data
  portInput.value = data.port
  for (const item of data.items || []) {
    noteEdits[item.id] = item.note || ''
  }
}

async function createAccount() {
  try {
    await apiFetch('/ftp', { method: 'POST', body: addForm })
    showAdd.value = false
    notify('FTP user created')
    await loadOverview()
  } catch (err: any) {
    notify(err.message || 'Create failed', false)
  }
}

async function toggleRevealPassword(a: any) {
  if (revealedPasswords[a.id]) {
    delete revealedPasswords[a.id]
    return
  }
  const res = await apiFetch(`/ftp/${a.id}/password/reveal`)
  revealedPasswords[a.id] = res.password
}

async function copyAccountPassword(a: any) {
  const res = await apiFetch(`/ftp/${a.id}/password/reveal`)
  copyText(res.password, `pw-${a.id}`)
}

async function toggleAccountStatus(a: any) {
  await apiFetch(`/ftp/${a.id}/toggle`, { method: 'POST' })
  await loadOverview()
}
async function saveNote(a: any) {
  await apiFetch(`/ftp/${a.id}/note`, { method: 'PUT', body: { note: noteEdits[a.id] || '' } })
  notify('Note saved')
}
function openHomeModal(a: any) {
  homeModal.row = a
  homeModal.path = a.home_directory
  homeModal.migrate = false
  homeModal.open = true
}
async function saveHome() {
  await apiFetch(`/ftp/${homeModal.row.id}/home`, { method: 'PUT', body: { home_directory: homeModal.path, migrate: homeModal.migrate } })
  homeModal.open = false
  notify('Home directory updated')
  await loadOverview()
}
function openPassModal(a: any) {
  passModal.row = a
  passModal.password = genPass(12)
  passModal.open = true
}
async function savePassword() {
  await apiFetch(`/ftp/${passModal.row.id}/password`, { method: 'PUT', body: { password: passModal.password } })
  passModal.open = false
  notify('Password rotated')
}
function openQuotaModal(a: any) {
  quotaModal.row = a
  quotaModal.quota_mb = a.quota_mb
  quotaModal.open = true
}
async function saveQuota() {
  await apiFetch(`/ftp/${quotaModal.row.id}/quota`, { method: 'PUT', body: { quota_mb: quotaModal.quota_mb } })
  quotaModal.open = false
  await loadOverview()
}
async function deleteAccount(a: any) {
  await apiFetch(`/ftp/${a.id}`, { method: 'DELETE' })
  await loadOverview()
}
function toggleAll(e: Event) {
  selectedIds.value = (e.target as HTMLInputElement).checked ? overview.value.items.map((i: any) => i.id) : []
}
async function executeBatch() {
  if (!selectedIds.value.length || batchAction.value !== 'delete') return
  await apiFetch('/ftp/batch-delete', { method: 'POST', body: { ids: selectedIds.value } })
  selectedIds.value = []
  batchAction.value = ''
  await loadOverview()
}
async function savePort() {
  await apiFetch('/ftp/port', { method: 'PUT', body: { port: portInput.value } })
  showPort.value = false
  notify('FTP port updated')
  await loadOverview()
}
async function updateSec(key: string, val: boolean) {
  await apiFetch('/ftp/security', { method: 'PUT', body: { [key]: val } })
  await loadOverview()
}
async function openUserLogs(a: any) {
  logsModal.row = a
  logsModal.tab = 'login'
  logsModal.open = true
  loginLogs.value = (await apiFetch(`/ftp/${a.id}/logs/login`)).data || []
}
async function switchLogTab(t: 'login' | 'action') {
  logsModal.tab = t
  if (t === 'login') loginLogs.value = (await apiFetch(`/ftp/${logsModal.row.id}/logs/login`)).data || []
  else actionLogs.value = (await apiFetch(`/ftp/${logsModal.row.id}/logs/action`)).data || []
}
function openLogAnalysis() {
  scanned.value = false
  analysisOpen.value = true
}
async function runScan() {
  const res = await apiFetch('/ftp/log-analysis/scan', { method: 'POST', body: {} })
  scanRisks.value = res.risks || []
  scanned.value = true
}
async function openWhitelist() {
  whitelistIps.value = (await apiFetch('/ftp/whitelist')).ips || []
  whitelistOpen.value = true
}
async function addIp() {
  whitelistIps.value = (await apiFetch('/ftp/whitelist', { method: 'POST', body: { ip: newIp.value } })).ips || []
  newIp.value = ''
}
async function delIp(ip: string) {
  whitelistIps.value = (await apiFetch(`/ftp/whitelist/${encodeURIComponent(ip)}`, { method: 'DELETE' })).ips || []
}
async function ignoreIp(ip: string) {
  await apiFetch('/ftp/whitelist', { method: 'POST', body: { ip } })
  await runScan()
}

onMounted(loadOverview)
</script>
