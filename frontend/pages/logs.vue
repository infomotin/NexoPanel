<template>
  <div class="space-y-4">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-lg font-bold text-slate-900 flex items-center gap-2">
          <FileText class="w-5 h-5 text-emerald-600" />
          <span>Server & Application Log Center</span>
        </h1>
        <p class="text-xs text-slate-500">
          Real-time log inspection, diagnostic search, severity filtering, and error monitoring.
        </p>
      </div>

      <div class="flex items-center gap-2">
        <!-- Auto-Refresh Toggle -->
        <div class="flex items-center rounded border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
          <span class="mr-2 flex items-center gap-1.5 font-medium">
            <span class="w-2 h-2 rounded-full" :class="autoRefresh ? 'bg-emerald-500 animate-pulse' : 'bg-slate-300'"></span>
            Auto-refresh
          </span>
          <select v-model.number="refreshInterval" class="bg-transparent border-0 text-xs font-semibold text-slate-800 focus:ring-0 p-0 pr-1">
            <option :value="0">Off</option>
            <option :value="3">3s</option>
            <option :value="5">5s</option>
            <option :value="10">10s</option>
          </select>
        </div>

        <!-- Manual Refresh Button -->
        <button @click="loadLogContent" :disabled="loading" class="np-btn-secondary text-xs flex items-center gap-1.5">
          <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
          <span>Refresh</span>
        </button>

        <!-- Clear Log Button -->
        <button @click="confirmClearLog" :disabled="clearing" class="px-3 py-1.5 rounded border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100 text-xs font-medium flex items-center gap-1.5 transition-colors">
          <Trash2 class="w-3.5 h-3.5" />
          <span>Clear Log</span>
        </button>

        <!-- Download Raw Log Button -->
        <button @click="downloadLog" class="np-btn-secondary text-xs flex items-center gap-1.5">
          <Download class="w-3.5 h-3.5" />
          <span>Download</span>
        </button>
      </div>
    </div>

    <!-- Main Container: Two-column layout -->
    <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-12rem)] overflow-hidden text-xs">
      <!-- Left Sidebar: Log Categories & Files -->
      <aside class="w-64 shrink-0 border-r border-slate-200 bg-slate-50/50 flex flex-col">
        <!-- Search Files -->
        <div class="p-3 border-b border-slate-200">
          <div class="relative">
            <input
              v-model="catalogSearch"
              placeholder="Search logs..."
              class="w-full pl-8 pr-3 py-1.5 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
          </div>
        </div>

        <!-- Category Tabs -->
        <div class="flex items-center border-b border-slate-200 bg-slate-100/60 p-1 text-[11px]">
          <button
            v-for="cat in ['all', 'system', 'web', 'app', 'database', 'websites']"
            :key="cat"
            @click="selectedCategory = cat"
            :class="selectedCategory === cat ? 'bg-white shadow-xs font-semibold text-slate-900' : 'text-slate-500 hover:text-slate-800'"
            class="flex-1 py-1 px-1.5 rounded text-center capitalize transition-colors"
          >
            {{ cat === 'websites' ? 'Sites' : cat }}
          </button>
        </div>

        <!-- Catalog List -->
        <div class="flex-1 overflow-y-auto divide-y divide-slate-100">
          <button
            v-for="item in filteredCatalog"
            :key="item.id"
            @click="selectLog(item)"
            :class="activeTarget?.id === item.id ? 'bg-emerald-50/80 border-r-2 border-emerald-600 text-emerald-950 font-semibold' : 'text-slate-700 hover:bg-slate-100/80'"
            class="w-full text-left px-3.5 py-2.5 transition-colors flex items-start justify-between gap-2"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="item.exists ? 'bg-emerald-500' : 'bg-slate-300'"></span>
                <span class="text-xs truncate font-medium">{{ item.name }}</span>
              </div>
              <p class="text-[10px] text-slate-400 font-mono truncate mt-0.5" :title="item.path">{{ item.path }}</p>
            </div>
            <span v-if="item.size_bytes > 0" class="text-[10px] text-slate-400 font-mono shrink-0">
              {{ formatBytes(item.size_bytes) }}
            </span>
          </button>

          <div v-if="filteredCatalog.length === 0" class="p-6 text-center text-slate-400 text-xs">
            No matching log files found.
          </div>
        </div>
      </aside>

      <!-- Right Main Content: Terminal Log Viewer -->
      <div class="flex-1 flex flex-col min-w-0 bg-slate-900 text-slate-100">
        <!-- Control Toolbar above Terminal -->
        <div class="bg-slate-950 px-4 py-2.5 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
          <!-- Active Log Target Details -->
          <div class="flex items-center gap-2 min-w-0">
            <span class="font-bold text-white tracking-wide truncate">{{ activeTarget?.name || 'Syslog' }}</span>
            <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[11px] truncate max-w-xs" :title="activeTarget?.path">
              {{ activeTarget?.path || '/var/log/syslog' }}
            </span>
            <span v-if="activeTarget?.size_bytes" class="text-[11px] text-slate-400 font-mono">
              ({{ formatBytes(activeTarget.size_bytes) }})
            </span>
          </div>

          <!-- Filters: Level, Lines, Keyword -->
          <div class="flex flex-wrap items-center gap-2.5">
            <!-- Level Buttons -->
            <div class="flex items-center rounded bg-slate-900 border border-slate-800 p-0.5 text-[11px]">
              <button
                v-for="lvl in ['ALL', 'ERROR', 'WARN', 'INFO']"
                :key="lvl"
                @click="selectedLevel = lvl; loadLogContent()"
                :class="selectedLevel === lvl ? levelActiveClasses(lvl) : 'text-slate-400 hover:text-white'"
                class="px-2 py-0.5 rounded font-semibold transition-colors"
              >
                {{ lvl }}
              </button>
            </div>

            <!-- Lines Selector -->
            <select
              v-model.number="linesLimit"
              @change="loadLogContent"
              class="bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded px-2.5 py-1 focus:ring-1 focus:ring-emerald-500"
            >
              <option :value="50">Last 50 lines</option>
              <option :value="100">Last 100 lines</option>
              <option :value="250">Last 250 lines</option>
              <option :value="500">Last 500 lines</option>
              <option :value="1000">Last 1000 lines</option>
            </select>

            <!-- Search In Logs -->
            <div class="relative">
              <input
                v-model="filterKeyword"
                @keyup.enter="loadLogContent"
                placeholder="Search in log..."
                class="w-44 bg-slate-900 border border-slate-800 text-slate-100 text-xs rounded pl-7 pr-2.5 py-1 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2 top-2" />
            </div>

            <!-- Auto-scroll checkbox -->
            <label class="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer select-none">
              <input v-model="autoScroll" type="checkbox" class="rounded border-slate-700 bg-slate-900 text-emerald-500 focus:ring-0 w-3.5 h-3.5" />
              <span>Scroll bottom</span>
            </label>
          </div>
        </div>

        <!-- Terminal Viewer Body -->
        <div ref="terminalRef" class="flex-1 p-4 font-mono text-xs overflow-y-auto space-y-1 select-text">
          <div v-if="loading && logLines.length === 0" class="flex items-center justify-center py-20 text-slate-400 gap-2">
            <RefreshCw class="w-4 h-4 animate-spin text-emerald-400" />
            <span>Loading log stream from host system...</span>
          </div>

          <div v-else-if="logLines.length === 0" class="text-center py-20 text-slate-500">
            <Info class="w-6 h-6 mx-auto mb-2 text-slate-600" />
            <p>No log records found matching the current criteria or log file is empty.</p>
          </div>

          <div
            v-for="(entry, idx) in logLines"
            :key="idx"
            class="flex items-start gap-3 hover:bg-slate-800/50 py-0.5 px-1.5 rounded transition-colors group"
          >
            <!-- Line Number -->
            <span class="text-slate-600 select-none text-[11px] w-10 text-right shrink-0">{{ idx + 1 }}</span>

            <!-- Level Tag -->
            <span
              v-if="entry.level !== 'DEBUG'"
              :class="levelBadgeClasses(entry.level)"
              class="px-1.5 py-0.2 rounded text-[10px] font-bold shrink-0 tracking-wider"
            >
              {{ entry.level }}
            </span>

            <!-- Raw Content with Highlight -->
            <span class="break-all whitespace-pre-wrap leading-relaxed text-slate-200" :class="lineTextClasses(entry.level)">{{ entry.raw }}</span>
          </div>
        </div>

        <!-- Terminal Footer Bar -->
        <div class="bg-slate-950 px-4 py-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <div class="flex items-center gap-4">
            <span>Showing {{ logLines.length }} lines</span>
            <span v-if="filterKeyword">Filtered by: "{{ filterKeyword }}"</span>
          </div>
          <div>
            Last updated: {{ lastUpdatedTime || 'Just now' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Download,
  FileText,
  Info,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-vue-next'

const { apiFetch } = useApi()

interface LogCatalogItem {
  id: string
  name: string
  path: string
  category: string
  type: string
  exists: boolean
  size_bytes: number
  domain?: string
}

interface LogEntry {
  raw: string
  level: string
}

const catalog = ref<LogCatalogItem[]>([])
const activeTarget = ref<LogCatalogItem | null>(null)
const selectedCategory = ref<string>('all')
const catalogSearch = ref('')
const filterKeyword = ref('')
const selectedLevel = ref('ALL')
const linesLimit = ref(150)
const autoRefresh = ref(false)
const refreshInterval = ref(0)
const autoScroll = ref(true)

const loading = ref(false)
const clearing = ref(false)
const logLines = ref<LogEntry[]>([])
const lastUpdatedTime = ref('')
const terminalRef = ref<HTMLElement | null>(null)

let timer: any = null

const filteredCatalog = computed(() => {
  let list = catalog.value
  if (selectedCategory.value !== 'all') {
    list = list.filter((i) => i.category === selectedCategory.value)
  }
  if (catalogSearch.value.trim()) {
    const q = catalogSearch.value.toLowerCase().trim()
    list = list.filter((i) => i.name.toLowerCase().includes(q) || i.path.toLowerCase().includes(q))
  }
  return list
})

function formatBytes(bytes: number) {
  if (!bytes || bytes === 0) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function levelActiveClasses(lvl: string) {
  if (lvl === 'ERROR') return 'bg-rose-600 text-white shadow-xs'
  if (lvl === 'WARN') return 'bg-amber-600 text-white shadow-xs'
  if (lvl === 'INFO') return 'bg-sky-600 text-white shadow-xs'
  return 'bg-slate-700 text-white shadow-xs'
}

function levelBadgeClasses(lvl: string) {
  if (lvl === 'ERROR') return 'bg-rose-950 text-rose-300 border border-rose-800'
  if (lvl === 'WARN') return 'bg-amber-950 text-amber-300 border border-amber-800'
  if (lvl === 'INFO') return 'bg-sky-950 text-sky-300 border border-sky-800'
  return 'bg-slate-800 text-slate-300'
}

function lineTextClasses(lvl: string) {
  if (lvl === 'ERROR') return 'text-rose-200'
  if (lvl === 'WARN') return 'text-amber-200'
  return 'text-slate-200'
}

async function loadCatalog() {
  try {
    const res = await apiFetch<LogCatalogItem[]>('/system/logs/catalog')
    catalog.value = res || []
    if (!activeTarget.value && catalog.value.length > 0) {
      activeTarget.value = catalog.value[0]
      await loadLogContent()
    }
  } catch {
    catalog.value = []
  }
}

async function selectLog(item: LogCatalogItem) {
  activeTarget.value = item
  await loadLogContent()
}

async function loadLogContent() {
  if (!activeTarget.value) return
  loading.value = true
  try {
    const params = new URLSearchParams({
      target: activeTarget.value.id,
      path: activeTarget.value.path,
      lines: String(linesLimit.value),
      filter: filterKeyword.value,
      level: selectedLevel.value,
    })
    const res: any = await apiFetch(`/system/logs/read?${params.toString()}`)
    logLines.value = res?.entries || []
    if (res?.size_bytes !== undefined) {
      activeTarget.value.size_bytes = res.size_bytes
    }
    lastUpdatedTime.value = new Date().toLocaleTimeString()

    if (autoScroll.value) {
      nextTick(() => {
        if (terminalRef.value) {
          terminalRef.value.scrollTop = terminalRef.value.scrollHeight
        }
      })
    }
  } catch (err: any) {
    logLines.value = [{ raw: `[ERROR] Failed to fetch log stream: ${err?.message || 'Server error'}`, level: 'ERROR' }]
  } finally {
    loading.value = false
  }
}

async function confirmClearLog() {
  if (!activeTarget.value) return
  if (!confirm(`Are you sure you want to clear/truncate ${activeTarget.value.name} (${activeTarget.value.path})? This cannot be undone.`)) {
    return
  }
  clearing.value = true
  try {
    await apiFetch('/system/logs/clear', {
      method: 'POST',
      body: { target: activeTarget.value.id, path: activeTarget.value.path },
    })
    await loadLogContent()
    await loadCatalog()
  } catch (err: any) {
    alert(`Failed to clear log: ${err?.message || 'Server error'}`)
  } finally {
    clearing.value = false
  }
}

function downloadLog() {
  if (logLines.value.length === 0) return
  const text = logLines.value.map((l) => l.raw).join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${activeTarget.value?.id || 'log'}_${Date.now()}.log`
  a.click()
  URL.revokeObjectURL(url)
}

watch(refreshInterval, (newVal) => {
  if (timer) clearInterval(timer)
  if (newVal > 0) {
    autoRefresh.value = true
    timer = setInterval(() => {
      loadLogContent()
    }, newVal * 1000)
  } else {
    autoRefresh.value = false
  }
})

onMounted(async () => {
  await loadCatalog()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>