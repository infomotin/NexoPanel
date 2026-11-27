<template>
  <div class="space-y-3 text-xs">
    <!-- Header Title & Quick Actions -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-base font-bold text-slate-900">Software & Package Manager</h1>
        <p class="text-xs text-slate-500">Manage web servers, PHP runtimes, databases, caching services, and Debian/Ubuntu system packages.</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button @click="updateRepoCache" :disabled="isStreaming" class="np-btn-secondary flex items-center gap-1.5">
          <RefreshCw :class="{ 'animate-spin': isStreaming }" class="w-3.5 h-3.5 text-slate-600" />
          <span>Update Index (apt update)</span>
        </button>
        <button @click="openCustomInstallModal" :disabled="isStreaming" class="np-btn-primary flex items-center gap-1.5">
          <Plus class="w-3.5 h-3.5" />
          <span>Install Custom Package</span>
        </button>
      </div>
    </div>

    <!-- Category Filter Tabs -->
    <div class="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 text-xs font-medium overflow-x-auto">
      <button
        v-for="cat in categories"
        :key="cat.id"
        @click="activeCategory = cat.id; loadData()"
        :class="activeCategory === cat.id ? 'text-emerald-600 font-semibold border-b-2 border-emerald-600' : 'text-slate-600 hover:text-slate-900 border-b-2 border-transparent'"
        class="pb-1.5 px-1 whitespace-nowrap transition-colors flex items-center gap-1"
      >
        <span>{{ cat.label }}</span>
        <span v-if="cat.count !== undefined" class="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600">
          {{ cat.count }}
        </span>
      </button>
    </div>

    <!-- Search & Filter Bar -->
    <div class="np-card p-2.5 flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <input
          v-model="search"
          @input="onSearchInput"
          :placeholder="activeCategory === 'apt' ? 'Search all Debian/Ubuntu packages...' : 'Filter software by name or keyword...'"
          class="np-input w-72"
        />
        <button @click="loadData" class="np-btn-secondary">Search</button>
      </div>

      <div class="flex items-center gap-3 text-slate-500 text-[11px]">
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span>Running</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-amber-500"></span>
          <span>Stopped</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-slate-300"></span>
          <span>Not Installed</span>
        </div>
      </div>
    </div>

    <!-- Curated Software Catalog View -->
    <div v-if="activeCategory !== 'apt'" class="np-card overflow-hidden">
      <div v-if="loadingCatalog" class="p-8 text-center text-slate-400">
        <RefreshCw class="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-600" />
        <p>Inspecting installed software & service states...</p>
      </div>
      <table v-else class="np-table">
        <thead>
          <tr>
            <th class="w-64">Software Name</th>
            <th class="w-28">Category</th>
            <th>Description & Required Packages</th>
            <th class="w-36 text-center">Service Status</th>
            <th class="w-40 text-center">Service Control</th>
            <th class="w-32 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in catalog" :key="item.slug" class="hover:bg-slate-50/80">
            <!-- Software Name & Version -->
            <td>
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 font-bold text-xs shrink-0">
                  <span v-if="item.category === 'PHP'" class="text-indigo-600 font-mono">PHP</span>
                  <span v-else-if="item.category === 'Web Server'" class="text-emerald-600 font-mono">WEB</span>
                  <span v-else-if="item.category === 'Database'" class="text-amber-600 font-mono">DB</span>
                  <span v-else-if="item.category === 'FTP'" class="text-blue-600 font-mono">FTP</span>
                  <span v-else-if="item.category === 'Security'" class="text-rose-600 font-mono">SEC</span>
                  <span v-else class="text-slate-600 font-mono">APP</span>
                </div>
                <div>
                  <div class="flex items-center gap-1.5">
                    <span class="font-semibold text-slate-900">{{ item.name }}</span>
                    <span v-if="item.version" class="text-[10px] font-mono px-1 py-0.2 rounded bg-slate-100 text-slate-600">
                      v{{ item.version.split('+')[0].split('-')[0] }}
                    </span>
                  </div>
                  <span class="text-[10px] font-mono text-slate-400">{{ item.slug }}</span>
                </div>
              </div>
            </td>

            <!-- Category -->
            <td>
              <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                {{ item.category }}
              </span>
            </td>

            <!-- Description -->
            <td>
              <p class="text-slate-700 font-normal">{{ item.description }}</p>
              <div class="text-[10px] font-mono text-slate-400 mt-1 flex flex-wrap gap-1">
                <span v-for="pkg in item.apt_packages" :key="pkg" class="bg-slate-50 px-1 py-0.2 rounded border border-slate-200">
                  {{ pkg }}
                </span>
              </div>
            </td>

            <!-- Service Status -->
            <td class="text-center">
              <div v-if="item.is_installed">
                <span
                  v-if="item.service_status === 'active'"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  Running
                </span>
                <span
                  v-else-if="item.service_status === 'inactive' && item.service"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                  Stopped
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200"
                >
                  Installed
                </span>
              </div>
              <div v-else>
                <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-400">
                  Not Installed
                </span>
              </div>
            </td>

            <!-- Service Control -->
            <td class="text-center">
              <div v-if="item.is_installed && item.service" class="flex items-center justify-center gap-1">
                <button
                  @click="controlService(item.slug, 'restart')"
                  :disabled="isStreaming"
                  title="Restart Service"
                  class="px-2 py-1 text-[11px] font-medium bg-white border border-slate-200 rounded hover:bg-slate-50 text-slate-700"
                >
                  Restart
                </button>
                <button
                  @click="controlService(item.slug, item.service_status === 'active' ? 'stop' : 'start')"
                  :disabled="isStreaming"
                  :title="item.service_status === 'active' ? 'Stop Service' : 'Start Service'"
                  :class="item.service_status === 'active' ? 'text-amber-600 hover:bg-amber-50' : 'text-emerald-600 hover:bg-emerald-50'"
                  class="px-2 py-1 text-[11px] font-medium bg-white border border-slate-200 rounded"
                >
                  {{ item.service_status === 'active' ? 'Stop' : 'Start' }}
                </button>
              </div>
              <span v-else class="text-slate-400 text-[11px]">—</span>
            </td>

            <!-- Main Actions -->
            <td class="text-right">
              <div v-if="item.is_installed">
                <button
                  @click="confirmUninstall(item)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 text-rose-600 hover:bg-rose-50 border border-rose-200 rounded font-medium text-xs transition-colors"
                >
                  Uninstall
                </button>
              </div>
              <div v-else>
                <button
                  @click="confirmInstall(item)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded font-medium text-xs transition-colors flex items-center gap-1 ml-auto"
                >
                  <Plus class="w-3 h-3" />
                  <span>Install</span>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="catalog.length === 0">
            <td colspan="6" class="p-8 text-center text-slate-400">
              No software found matching the selected filter or search term.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Raw APT Packages Browser View -->
    <div v-else class="np-card overflow-hidden">
      <div v-if="loadingApt" class="p-8 text-center text-slate-400">
        <RefreshCw class="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-600" />
        <p>Scanning installed APT packages...</p>
      </div>
      <table v-else class="np-table">
        <thead>
          <tr>
            <th>Package Name</th>
            <th>Installed Version</th>
            <th>DPKG Status</th>
            <th class="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in rawPackages" :key="p.name" class="hover:bg-slate-50/80">
            <td class="font-mono font-semibold text-slate-900">{{ p.name }}</td>
            <td class="font-mono text-[11px] text-slate-600">{{ p.version }}</td>
            <td>
              <span class="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-700 font-mono">
                {{ p.status }}
              </span>
            </td>
            <td class="text-right">
              <button
                @click="removeRawApt(p.name)"
                :disabled="isStreaming"
                class="text-rose-600 hover:underline font-medium"
              >
                Remove
              </button>
            </td>
          </tr>
          <tr v-if="rawPackages.length === 0">
            <td colspan="4" class="p-8 text-center text-slate-400">
              No packages found matching query. Try typing a search term and press Search.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Live Execution / Terminal Log Modal (aaPanel style) -->
    <div v-if="showLogModal" class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div class="bg-slate-900 text-slate-100 rounded-lg shadow-2xl w-full max-w-3xl h-[70vh] flex flex-col border border-slate-700 overflow-hidden">
        <!-- Terminal Header -->
        <div class="px-4 py-2.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span
              :class="isStreaming ? 'bg-amber-500 animate-pulse' : (streamError ? 'bg-rose-500' : 'bg-emerald-500')"
              class="w-2.5 h-2.5 rounded-full"
            ></span>
            <span class="font-mono font-bold text-xs text-slate-200">{{ streamTitle }}</span>
          </div>
          <button
            v-if="!isStreaming"
            @click="showLogModal = false; loadData()"
            class="px-2 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 rounded text-slate-300"
          >
            Close
          </button>
          <span v-else class="text-[11px] text-amber-400 font-mono flex items-center gap-1.5">
            <RefreshCw class="w-3 h-3 animate-spin" />
            <span>Processing...</span>
          </span>
        </div>

        <!-- Terminal Output -->
        <div ref="logContainer" class="flex-1 p-4 font-mono text-[11px] overflow-y-auto space-y-1 text-emerald-400 bg-slate-900 select-text">
          <div v-for="(line, i) in logLines" :key="i" class="leading-relaxed">
            <span v-if="line.startsWith('✓')" class="text-emerald-300 font-semibold">{{ line }}</span>
            <span v-else-if="line.startsWith('✗') || line.toLowerCase().includes('error')" class="text-rose-400 font-semibold">{{ line }}</span>
            <span v-else-if="line.startsWith('===') || line.startsWith('🎉')" class="text-amber-300 font-bold">{{ line }}</span>
            <span v-else class="text-slate-300">{{ line }}</span>
          </div>
        </div>

        <!-- Terminal Footer -->
        <div class="px-4 py-2 bg-slate-950 border-t border-slate-800 text-[11px] text-slate-500 flex items-center justify-between">
          <span>Execution logs streamed directly from host system package manager.</span>
          <span v-if="!isStreaming" class="text-emerald-400 font-medium">Ready</span>
        </div>
      </div>
    </div>

    <!-- Custom Package Install Modal -->
    <div v-if="showCustomModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-5 space-y-3">
        <h3 class="text-sm font-bold text-slate-900">Install Custom APT Package</h3>
        <p class="text-xs text-slate-500">Enter a standard Debian or Ubuntu package name (e.g. <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">htop</code>, <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">iftop</code>, <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">ncdu</code>).</p>
        <div>
          <label class="block text-[11px] font-medium text-slate-700 mb-1">Package Name</label>
          <input
            v-model="customPkgName"
            @keyup.enter="installCustomPackage"
            placeholder="e.g. htop"
            class="np-input"
          />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showCustomModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="installCustomPackage" :disabled="!customPkgName.trim()" class="np-btn-primary">
            Install Package
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, RefreshCw } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch, apiBase, authHeaders } = useApi()

const activeCategory = ref('ALL')
const search = ref('')
const catalog = ref<any[]>([])
const rawPackages = ref<any[]>([])
const loadingCatalog = ref(false)
const loadingApt = ref(false)

const showLogModal = ref(false)
const streamTitle = ref('Package Operation')
const logLines = ref<string[]>([])
const isStreaming = ref(false)
const streamError = ref(false)
const logContainer = ref<HTMLElement | null>(null)

const showCustomModal = ref(false)
const customPkgName = ref('')

const categories = ref([
  { id: 'ALL', label: 'All Software' },
  { id: 'Web Server', label: 'Web Server' },
  { id: 'PHP', label: 'PHP Versions' },
  { id: 'Database', label: 'Databases' },
  { id: 'FTP', label: 'FTP' },
  { id: 'Runtime', label: 'Runtime' },
  { id: 'Security', label: 'Security' },
  { id: 'Tools', label: 'Tools' },
  { id: 'Installed', label: 'Installed' },
  { id: 'apt', label: 'Raw APT Browser' },
])

async function loadData() {
  if (activeCategory.value === 'apt') {
    await loadRawApt()
  } else {
    await loadCatalog()
  }
}

async function loadCatalog() {
  loadingCatalog.value = true
  try {
    const res = await apiFetch<any[]>(
      `/system/packages/catalog?category=${encodeURIComponent(activeCategory.value)}&search=${encodeURIComponent(search.value)}`
    )
    catalog.value = res || []
  } catch (err) {
    console.error('Failed to load package catalog:', err)
  } finally {
    loadingCatalog.value = false
  }
}

async function loadRawApt() {
  loadingApt.value = true
  try {
    const res = await apiFetch<any>(`/system/packages?search=${encodeURIComponent(search.value)}`)
    rawPackages.value = res?.packages || []
  } catch (err) {
    console.error('Failed to load raw packages:', err)
  } finally {
    loadingApt.value = false
  }
}

function onSearchInput() {
  // Debounce search
  clearTimeout((onSearchInput as any)._timer)
  ;(onSearchInput as any)._timer = setTimeout(() => {
    loadData()
  }, 300)
}

function openCustomInstallModal() {
  customPkgName.value = ''
  showCustomModal.value = true
}

async function installCustomPackage() {
  const pkg = customPkgName.value.trim()
  if (!pkg) return
  showCustomModal.value = false
  await startSseStream(
    `Installing Package: ${pkg}`,
    `${apiBase}/system/packages/install`,
    { packages: [pkg] }
  )
}

async function confirmInstall(item: any) {
  if (!confirm(`Are you sure you want to install ${item.name}?\n\nThis will install packages: ${item.apt_packages.join(', ')} and start any required services.`)) {
    return
  }
  await startSseStream(
    `Installing ${item.name}`,
    `${apiBase}/system/packages/curated/${item.slug}/install`,
    {}
  )
}

async function confirmUninstall(item: any) {
  if (!confirm(`Warning: Are you sure you want to uninstall ${item.name}?\n\nThis will stop its service and remove packages: ${item.apt_packages.join(', ')}.`)) {
    return
  }
  await startSseStream(
    `Uninstalling ${item.name}`,
    `${apiBase}/system/packages/curated/${item.slug}/uninstall`,
    {}
  )
}

async function removeRawApt(pkgName: string) {
  if (!confirm(`Are you sure you want to remove package ${pkgName}?`)) return
  await startSseStream(
    `Removing ${pkgName}`,
    `${apiBase}/system/packages/remove`,
    { packages: [pkgName] }
  )
}

async function updateRepoCache() {
  await startSseStream(
    'Updating APT Package Index (apt-get update)',
    `${apiBase}/system/packages/update-cache`,
    {}
  )
}

async function controlService(slug: string, action: string) {
  try {
    await apiFetch(`/system/packages/curated/${slug}/control`, {
      method: 'POST',
      body: { service: slug, action },
    })
    await loadCatalog()
  } catch (err: any) {
    alert(`Service action failed: ${err.data?.detail || err.message}`)
  }
}

async function startSseStream(title: string, url: string, body: any) {
  streamTitle.value = title
  logLines.value = [`[NexoPanel] Initializing operation: ${title}...`]
  showLogModal.value = true
  isStreaming.value = true
  streamError.value = false

  try {
    const resp = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders('POST'),
      },
      body: JSON.stringify(body),
    })

    if (!resp.ok) {
      if (resp.status === 401) {
        auth.clearSession()
        logLines.value.push('[ERROR] Session expired or invalid authentication token. Redirecting to login...')
        streamError.value = true
        isStreaming.value = false
        setTimeout(() => {
          window.location.href = '/login'
        }, 1200)
        return
      }
      const errJson = await resp.json().catch(() => ({}))
      logLines.value.push(`[ERROR] Server responded with HTTP ${resp.status}: ${errJson.detail || 'Request failed'}`)
      streamError.value = true
      isStreaming.value = false
      return
    }

    const reader = resp.body?.getReader()
    if (!reader) {
      logLines.value.push('[ERROR] Response body stream unavailable.')
      isStreaming.value = false
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        if (chunk.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(chunk.slice(6))
            if (parsed.line) {
              logLines.value.push(parsed.line)
            }
            if (parsed.done) {
              if (parsed.returncode !== 0) {
                streamError.value = true
              }
            }
          } catch {
            // Ignore parse errors on partial chunks
          }
        }
      }

      // Auto scroll
      nextTick(() => {
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      })
    }
  } catch (err: any) {
    logLines.value.push(`[ERROR] Network or connection error: ${err.message}`)
    streamError.value = true
  } finally {
    isStreaming.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>
