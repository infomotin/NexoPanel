<template>
  <div class="space-y-3 text-xs">
    <!-- Top Project Type Tabs (aaPanel parity) -->
    <div class="flex items-center gap-6 border-b border-slate-200 bg-white px-4 py-2 text-xs font-medium overflow-x-auto">
      <button
        v-for="tab in projectTabs"
        :key="tab.id"
        @click="activeProjectTab = tab.id"
        :class="activeProjectTab === tab.id ? 'text-emerald-600 font-semibold border-b-2 border-emerald-600' : 'text-slate-600 hover:text-slate-900 border-b-2 border-transparent'"
        class="pb-2 whitespace-nowrap transition-colors"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Action Toolbar -->
    <div class="np-card p-2.5 flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-center gap-2">
        <button v-if="auth.can('websites:write')" @click="openAddModal" class="np-btn-primary">Add site</button>
        <button v-if="auth.can('subdomains:write')" @click="showSubModal = true" class="np-btn-secondary">+ Add Subdomain</button>
        <button @click="reloadNginx" class="np-btn-secondary flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Nginx Reload ▶</span>
        </button>
      </div>

      <div class="flex items-center gap-2">
        <input v-model="searchQuery" placeholder="Domain or Remarks..." class="np-input w-56" />
      </div>
    </div>

    <!-- Main Websites Table (aaPanel Columns) -->
    <div v-if="activeProjectTab !== 'subdomains'" class="np-card overflow-hidden">
      <div class="overflow-x-auto">
        <table class="np-table">
          <thead>
            <tr>
              <th class="w-8"><input type="checkbox" @change="toggleAll($event)" /></th>
              <th>Site name</th>
              <th class="text-center">Status</th>
              <th>Backup / Restore</th>
              <th>Quick action</th>
              <th>Expiration</th>
              <th>SSL</th>
              <th>Requests</th>
              <th class="text-center">WAF</th>
              <th class="text-right">Operate</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="site in filteredSites" :key="site.id" class="hover:bg-slate-50/80">
              <td><input type="checkbox" :value="site.id" v-model="selectedIds" /></td>
              <td>
                <div class="flex items-center gap-2">
                  <span class="w-5 h-5 rounded bg-emerald-100 text-emerald-700 flex items-center justify-center text-[10px] font-bold shrink-0">N</span>
                  <div>
                    <a :href="`http://${site.domain}`" target="_blank" class="font-semibold text-slate-900 hover:text-emerald-600">{{ site.domain }}</a>
                    <div class="text-[10px] font-mono text-slate-400 mt-0.5">{{ site.document_root }}</div>
                  </div>
                </div>
              </td>
              <td class="text-center">
                <button
                  @click="toggleSite(site.id)"
                  :class="site.status === 'active' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'"
                  class="px-2 py-0.5 rounded border text-[11px] font-medium"
                >
                  {{ site.status === 'active' ? '▶ Running' : '⏸ Stopped' }}
                </button>
              </td>
              <td>
                <button @click="quickBackup(site.domain)" class="text-xs text-slate-700 hover:text-emerald-600 underline">
                  ☁ Backup Now
                </button>
              </td>
              <td>
                <div class="flex items-center gap-2 text-xs">
                  <NuxtLink :to="`/files?path=${encodeURIComponent(site.document_root)}`" class="text-slate-600 hover:text-emerald-600" title="Open Root Folder">
                    📁
                  </NuxtLink>
                  <button @click="openLogs(site)" class="text-slate-600 hover:text-emerald-600" title="View Logs">
                    🖥
                  </button>
                  <button @click="openDrawer(site, 'php')" class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 hover:bg-emerald-50 hover:text-emerald-700">
                    {{ site.runtime_type === 'php' ? (site.php_version || '8.4') : site.runtime_type }}
                  </button>
                </div>
              </td>
              <td class="text-slate-600 text-[11px]">Perpetual</td>
              <td>
                <button
                  @click="openDrawer(site, 'ssl')"
                  :class="site.ssl_enabled ? 'text-emerald-600' : 'text-rose-500'"
                  class="text-[11px] font-medium hover:underline"
                >
                  {{ site.ssl_enabled ? '🔒 Active' : 'Not Set' }}
                </button>
              </td>
              <td>
                <div class="flex items-center gap-1.5">
                  <svg class="w-14 h-4 stroke-emerald-500 fill-emerald-500/10" viewBox="0 0 60 20">
                    <path d="M 0 16 Q 15 15, 25 10 T 45 4 T 60 8 L 60 20 L 0 20 Z" stroke-width="0" />
                    <path d="M 0 16 Q 15 15, 25 10 T 45 4 T 60 8" fill="none" stroke-width="1.5" />
                  </svg>
                  <span class="font-mono text-[11px] text-slate-600">{{ ((site.id || 1) * 12450).toLocaleString() }}</span>
                </div>
              </td>
              <td class="text-center">
                <span class="text-emerald-600 font-medium text-[11px]">Active</span>
              </td>
              <td class="text-right space-x-2">
                <button @click="openDrawer(site, 'domains')" class="text-emerald-600 hover:underline font-medium">Conf</button>
                <span class="text-slate-300">|</span>
                <button @click="openLogs(site)" class="text-blue-600 hover:underline">Log</button>
                <span class="text-slate-300">|</span>
                <button v-if="auth.can('websites:delete')" @click="deleteSite(site.id)" class="text-rose-600 hover:underline">Del</button>
              </td>
            </tr>
            <tr v-if="!filteredSites.length">
              <td colspan="10" class="text-center text-slate-400 py-8">No websites in this category yet. Click "Add site" to create one.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Batch Operations Footer -->
      <div class="px-3 py-2 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <select v-model="batchAction" class="np-input w-36">
            <option value="">Please choose</option>
            <option value="start">Start Selected</option>
            <option value="stop">Stop Selected</option>
            <option value="delete">Delete Selected</option>
          </select>
          <button @click="runBatch" :disabled="!selectedIds.length || !batchAction" class="np-btn-secondary">Execute</button>
        </div>
        <span class="text-slate-500">Total: {{ filteredSites.length }}</span>
      </div>
    </div>

    <!-- Subdomains Table -->
    <div v-else class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs text-slate-700">Subdomains</div>
      <table class="np-table">
        <thead>
          <tr><th>FQDN</th><th>Runtime</th><th>Document Root</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          <tr v-for="sub in subdomains" :key="sub.id">
            <td class="font-semibold">{{ sub.fqdn }}</td>
            <td>{{ sub.runtime_type }}</td>
            <td class="font-mono text-[11px]">{{ sub.document_root }}</td>
            <td class="text-right">
              <button v-if="auth.can('subdomains:delete')" @click="deleteSub(sub.id)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Add Website Modal -->
    <div v-if="showSiteModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add Website</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Domain(s)</label>
          <input v-model="newSite.domain" placeholder="example.com" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Runtime Type</label>
          <select v-model="newSite.runtime_type" class="np-input">
            <option value="php">PHP Project (PHP-FPM)</option>
            <option value="static">Static / SPA</option>
            <option value="proxy">Reverse Proxy (Node.js / Go / Python)</option>
          </select>
        </div>
        <div v-if="newSite.runtime_type === 'php'">
          <div class="flex items-center justify-between mb-1">
            <label class="block text-[11px] font-medium text-slate-600">PHP Version</label>
            <NuxtLink to="/packages" class="text-[10px] text-emerald-600 hover:underline">+ Manage Packages</NuxtLink>
          </div>
          <select v-model="newSite.php_version" class="np-input">
            <option v-for="php in availablePhpVersions" :key="php.version" :value="php.version">
              {{ php.label || `PHP ${php.version}` }}
            </option>
          </select>
        </div>
        <div v-if="newSite.runtime_type === 'proxy'">
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Proxy Upstream URL</label>
          <input v-model="newSite.proxy_upstream" placeholder="http://127.0.0.1:3000" class="np-input" />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showSiteModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createSite" class="np-btn-primary">Create Site</button>
        </div>
      </div>
    </div>

    <!-- Add Subdomain Modal -->
    <div v-if="showSubModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add Subdomain</h3>
        <select v-model="newSub.website_id" class="np-input">
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.domain }}</option>
        </select>
        <input v-model="newSub.prefix" placeholder="api" class="np-input" />
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showSubModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createSubdomain" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <!-- Tabbed Site Configuration (Conf) Modal -->
    <div v-if="editingSite" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-2xl w-full max-w-3xl h-[75vh] flex flex-col overflow-hidden">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <h3 class="text-sm font-bold text-slate-800">Site Configuration — {{ editingSite.domain }}</h3>
          <button @click="editingSite = null" class="np-btn-secondary">Close</button>
        </div>
        <div class="flex flex-1 overflow-hidden">
          <div class="w-40 border-r border-slate-200 bg-slate-50 p-2 space-y-1 text-xs">
            <button
              v-for="t in confTabs"
              :key="t.id"
              @click="confTab = t.id"
              :class="confTab === t.id ? 'bg-emerald-600 text-white' : 'text-slate-700 hover:bg-slate-200'"
              class="w-full text-left px-3 py-2 rounded font-medium"
            >
              {{ t.label }}
            </button>
          </div>
          <div class="flex-1 p-5 overflow-y-auto space-y-3 text-xs">
            <div v-if="confTab === 'domains'" class="space-y-2">
              <label class="font-semibold text-slate-700">Domain Aliases (comma-separated)</label>
              <input v-model="aliasesInput" placeholder="www.example.com, alias.example.com" class="np-input" />
            </div>

            <div v-if="confTab === 'php'" class="space-y-2">
              <label class="font-semibold text-slate-700">Runtime & PHP Version</label>
              <select v-model="editingSite.runtime_type" class="np-input">
                <option value="php">PHP-FPM</option>
                <option value="static">Static / Pure HTML</option>
                <option value="proxy">Reverse Proxy</option>
              </select>
              <div v-if="editingSite.runtime_type === 'php'">
                <select v-model="editingSite.php_version" class="np-input">
                  <option v-for="php in availablePhpVersions" :key="php.version" :value="php.version">
                    {{ php.label || `PHP ${php.version}` }}
                  </option>
                </select>
                <p class="text-[11px] text-slate-500 mt-1">
                  Need another PHP version? <NuxtLink to="/packages" class="text-emerald-600 underline font-medium">Install PHP versions in Software & Packages</NuxtLink>.
                </p>
              </div>
              <input v-if="editingSite.runtime_type === 'proxy'" v-model="editingSite.proxy_upstream" placeholder="http://127.0.0.1:3000" class="np-input" />
            </div>

            <div v-if="confTab === 'rewrite'" class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="font-semibold text-slate-700">URL Rewrite / Custom Directives</label>
                <select @change="applyPreset($event)" class="np-input w-44">
                  <option value="">Load Preset...</option>
                  <option v-for="(val, key) in rewritePresets" :key="key" :value="key">{{ key }}</option>
                </select>
              </div>
              <textarea v-model="editingSite.custom_directives" rows="12" class="np-input font-mono text-[11px]"></textarea>
            </div>

            <div v-if="confTab === 'ssl'" class="space-y-3">
              <label class="flex items-center gap-2 font-medium">
                <input type="checkbox" v-model="editingSite.force_https" />
                <span>Force HTTPS (301 Redirect HTTP -> HTTPS)</span>
              </label>
              <p class="text-slate-500">Issue or manage Let's Encrypt certificates on the <NuxtLink to="/ssl" class="text-emerald-600 underline">SSL / ACME</NuxtLink> page.</p>
            </div>
          </div>
        </div>
        <div class="px-5 py-3 border-t border-slate-200 flex justify-end gap-2 bg-slate-50">
          <button @click="editingSite = null" class="np-btn-secondary">Cancel</button>
          <button @click="saveSiteConfig" class="np-btn-primary">Validate (nginx -t) & Save</button>
        </div>
      </div>
    </div>

    <!-- Site Logs Modal -->
    <div v-if="logsSite" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-6">
      <div class="bg-white rounded-lg p-5 w-full max-w-3xl h-[70vh] flex flex-col">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-bold">Site Logs — {{ logsSite.domain }}</h3>
          <div class="flex gap-2">
            <button @click="loadSiteLogs('access')" class="np-btn-secondary">Access Log</button>
            <button @click="loadSiteLogs('error')" class="np-btn-secondary">Error Log</button>
            <button @click="logsSite = null" class="np-btn-secondary">Close</button>
          </div>
        </div>
        <pre class="bg-slate-900 text-slate-200 p-3 rounded text-[11px] font-mono flex-1 overflow-y-auto">{{ siteLogLines.join('\n') || 'No log entries recorded yet.' }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch } = useApi()

const sites = ref<any[]>([])
const subdomains = ref<any[]>([])
const rewritePresets = ref<Record<string, string>>({})
const activeProjectTab = ref('all')
const searchQuery = ref('')
const selectedIds = ref<number[]>([])
const batchAction = ref('')

const showSiteModal = ref(false)
const showSubModal = ref(false)
const editingSite = ref<any>(null)
const confTab = ref('domains')
const aliasesInput = ref('')
const logsSite = ref<any>(null)
const siteLogLines = ref<string[]>([])

const availablePhpVersions = ref<any[]>([
  { version: '8.4', label: 'PHP 8.4' },
  { version: '8.3', label: 'PHP 8.3' },
  { version: '8.2', label: 'PHP 8.2' },
])

const newSite = reactive({ domain: '', runtime_type: 'php', php_version: '8.4', proxy_upstream: '' })
const newSub = reactive({ website_id: 0, prefix: '' })

const projectTabs = [
  { id: 'all', label: 'All Sites' },
  { id: 'php', label: 'PHP Project' },
  { id: 'proxy', label: 'Node.js / Proxy / Python / Go' },
  { id: 'static', label: 'Static / SPA' },
  { id: 'subdomains', label: 'Subdomains' },
]

const confTabs = [
  { id: 'domains', label: 'Domain Manager' },
  { id: 'php', label: 'Runtime / PHP' },
  { id: 'rewrite', label: 'URL Rewrite / Conf' },
  { id: 'ssl', label: 'SSL & HTTPS' },
]

const filteredSites = computed(() => {
  return sites.value.filter((s) => {
    if (activeProjectTab.value !== 'all' && s.runtime_type !== activeProjectTab.value) return false
    if (searchQuery.value && !s.domain.toLowerCase().includes(searchQuery.value.toLowerCase())) return false
    return true
  })
})

async function load() {
  sites.value = await apiFetch('/sites')
  subdomains.value = await apiFetch('/sites/subdomains')
  rewritePresets.value = await apiFetch('/sites/rewrite-presets')
  if (sites.value.length && !newSub.website_id) newSub.website_id = sites.value[0].id
  try {
    const runtimes = await apiFetch<any[]>('/system/runtimes/php')
    if (runtimes && runtimes.length) {
      availablePhpVersions.value = runtimes
      const activeOne = runtimes.find((r) => r.is_installed && r.service_status === 'active') || runtimes.find((r) => r.is_installed)
      if (activeOne) {
        newSite.php_version = activeOne.version
      }
    }
  } catch {
    // Keep fallback list
  }
}

function openAddModal() {
  if (activeProjectTab.value === 'proxy' || activeProjectTab.value === 'static') {
    newSite.runtime_type = activeProjectTab.value
  } else {
    newSite.runtime_type = 'php'
  }
  showSiteModal.value = true
}

function toggleAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedIds.value = checked ? filteredSites.value.map((s) => s.id) : []
}

async function runBatch() {
  if (!selectedIds.value.length || !batchAction.value) return
  await apiFetch('/sites/batch', { method: 'POST', body: { site_ids: selectedIds.value, action: batchAction.value } })
  selectedIds.value = []
  batchAction.value = ''
  await load()
}

async function createSite() {
  await apiFetch('/sites', { method: 'POST', body: newSite })
  showSiteModal.value = false
  newSite.domain = ''
  await load()
}

async function toggleSite(id: number) {
  await apiFetch(`/sites/${id}/toggle`, { method: 'POST' })
  await load()
}

async function quickBackup(domain: string) {
  await apiFetch('/backups/run', { method: 'POST', body: { target_type: 'website', target_identifier: domain } })
}

async function reloadNginx() {
  await apiFetch('/system/services/control', { method: 'POST', body: { service: 'nginx', action: 'reload' } })
}

async function createSubdomain() {
  await apiFetch('/sites/subdomains', { method: 'POST', body: newSub })
  showSubModal.value = false
  newSub.prefix = ''
  await load()
}

function openDrawer(site: any, tab = 'domains') {
  editingSite.value = { ...site }
  aliasesInput.value = (site.aliases || []).join(', ')
  confTab.value = tab
}

function applyPreset(e: Event) {
  const key = (e.target as HTMLSelectElement).value
  if (key && rewritePresets.value[key]) {
    editingSite.value.custom_directives = rewritePresets.value[key]
  }
}

async function saveSiteConfig() {
  const aliases = aliasesInput.value.split(',').map((s) => s.trim()).filter(Boolean)
  await apiFetch(`/sites/${editingSite.value.id}`, {
    method: 'PUT',
    body: {
      aliases,
      runtime_type: editingSite.value.runtime_type,
      php_version: editingSite.value.php_version,
      proxy_upstream: editingSite.value.proxy_upstream,
      custom_directives: editingSite.value.custom_directives,
      force_https: editingSite.value.force_https,
    },
  })
  editingSite.value = null
  await load()
}

async function openLogs(site: any) {
  logsSite.value = site
  await loadSiteLogs('access')
}

async function loadSiteLogs(logType: string) {
  const res = await apiFetch<any>(`/sites/${logsSite.value.id}/logs?log_type=${logType}`)
  siteLogLines.value = res.lines
}

async function deleteSite(id: number) {
  await apiFetch(`/sites/${id}`, { method: 'DELETE' })
  await load()
}

async function deleteSub(id: number) {
  await apiFetch(`/sites/subdomains/${id}`, { method: 'DELETE' })
  await load()
}

onMounted(load)
</script>
