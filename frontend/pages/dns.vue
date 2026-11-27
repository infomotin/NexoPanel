<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <!-- Left Vertical Sub-Navigation (aaPanel Domains Rail) -->
    <aside class="w-36 shrink-0 border-r border-slate-200 bg-slate-50/50 py-3">
      <button
        @click="activeSection = 'domain'"
        :class="activeSection === 'domain' ? 'text-emerald-600 bg-emerald-50/70 border-r-2 border-emerald-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
        class="w-full text-left px-4 py-2.5 transition-colors"
      >
        Domain
      </button>
      <button
        @click="activeSection = 'certificate'; loadCertificates()"
        :class="activeSection === 'certificate' ? 'text-emerald-600 bg-emerald-50/70 border-r-2 border-emerald-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
        class="w-full text-left px-4 py-2.5 transition-colors"
      >
        Certificate
      </button>
    </aside>

    <!-- Main Content Area -->
    <div class="flex-1 p-5 flex flex-col min-w-0">
      <!-- DOMAIN SECTION -->
      <div v-if="activeSection === 'domain'" class="space-y-4 flex-1 flex flex-col">
        <!-- Sub-Tabs: Provider List | Domain Management -->
        <div class="flex items-center border-b border-slate-200">
          <button
            @click="activeTab = 'providers'"
            :class="activeTab === 'providers' ? 'bg-white border-t border-l border-r border-slate-200 text-slate-900 font-semibold -mb-px rounded-t' : 'text-slate-500 hover:text-slate-800 bg-slate-50/60'"
            class="px-4 py-2 text-xs transition-colors"
          >
            Provider List
          </button>
          <button
            @click="activeTab = 'domains'"
            :class="activeTab === 'domains' ? 'bg-white border-t border-l border-r border-slate-200 text-slate-900 font-semibold -mb-px rounded-t' : 'text-slate-500 hover:text-slate-800 bg-slate-50/60'"
            class="px-4 py-2 text-xs transition-colors"
          >
            Domain Management
          </button>
        </div>

        <!-- TAB 1: PROVIDER LIST -->
        <div v-if="activeTab === 'providers'" class="space-y-3">
          <div class="flex items-center justify-between">
            <button @click="showProviderModal = true" class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium flex items-center gap-1.5">
              <Plus class="w-3.5 h-3.5" />
              <span>Add DNS Provider</span>
            </button>
            <span class="text-slate-500 text-[11px]">Configure Local BIND9 or external DNS API providers (Cloudflare, NameCheap, DigitalOcean).</span>
          </div>

          <div class="border border-slate-200 rounded overflow-hidden">
            <table class="np-table">
              <thead>
                <tr class="bg-slate-50">
                  <th>Provider Name</th>
                  <th>Type</th>
                  <th>API Token / Credential</th>
                  <th>Status</th>
                  <th class="text-right">Operate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in providers" :key="p.id" class="hover:bg-slate-50/70">
                  <td class="font-semibold text-slate-900">{{ p.name }}</td>
                  <td>
                    <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[11px] uppercase">{{ p.provider_type }}</span>
                  </td>
                  <td class="font-mono text-[11px] text-slate-500">{{ p.api_token }}</td>
                  <td>
                    <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-medium">
                      <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                      Active
                    </span>
                  </td>
                  <td class="text-right">
                    <span v-if="p.is_builtin" class="text-slate-400 text-[11px]">Built-in</span>
                    <button v-else @click="deleteProvider(p.id)" class="text-rose-600 hover:underline">Delete</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- TAB 2A: DOMAIN MANAGEMENT -> DOMAIN LIST -->
        <div v-else-if="activeTab === 'domains' && !managingZone" class="space-y-3 flex-1 flex flex-col">
          <!-- Toolbar -->
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex flex-wrap items-center gap-2">
              <select v-model="selectedProviderId" class="np-input w-56">
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
              <button
                @click="pullData"
                :disabled="pulling"
                class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium flex items-center gap-1.5 transition-colors"
              >
                <RefreshCw :class="{ 'animate-spin': pulling }" class="w-3.5 h-3.5" />
                <span>Pull Data</span>
              </button>
              <button @click="openPullLogs" class="px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
                Pull Log
              </button>
              <button @click="openZoneModal" class="px-3 py-1.5 rounded border border-emerald-600 text-emerald-700 bg-emerald-50/50 hover:bg-emerald-50 font-medium">
                + Add Domain
              </button>
            </div>

            <div class="relative">
              <input
                v-model="domainSearch"
                placeholder="Please enter domain"
                class="np-input w-56 pr-8"
              />
              <Search class="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-2" />
            </div>
          </div>

          <!-- Domains Table -->
          <div class="border border-slate-200 rounded overflow-hidden">
            <table class="np-table">
              <thead>
                <tr class="bg-slate-50">
                  <th>Domain</th>
                  <th>SSL</th>
                  <th>Number of Resolutions</th>
                  <th>Expiration Time</th>
                  <th class="text-right">Operate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="z in paginatedZones" :key="z.id" class="hover:bg-slate-50/80">
                  <td>
                    <button @click="enterManage(z)" class="flex items-center gap-2 font-semibold text-slate-800 hover:text-emerald-600">
                      <Globe class="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                      <span>{{ z.domain }}</span>
                    </button>
                  </td>
                  <td>
                    <span v-if="z.ssl_status === 'active'" class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px] font-medium">
                      🔒 Active
                    </span>
                    <span v-else class="text-slate-400">--</span>
                  </td>
                  <td class="font-mono text-slate-700">{{ z.record_count ?? 0 }}</td>
                  <td class="text-slate-500 text-[11px]">
                    {{ z.ssl_expires_at ? formatDate(z.ssl_expires_at) : '-' }}
                  </td>
                  <td class="text-right space-x-3">
                    <button @click="enterManage(z)" class="text-emerald-600 hover:underline font-medium">Manage</button>
                    <button @click="deleteZone(z)" class="text-rose-600 hover:underline">Delete</button>
                  </td>
                </tr>
                <tr v-if="filteredZones.length === 0">
                  <td colspan="5" class="p-8 text-center text-slate-400">
                    No domains found. Click <button @click="openZoneModal" class="text-emerald-600 underline font-medium">+ Add Domain</button> to create your first DNS zone.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination Footer -->
          <div class="flex items-center justify-end gap-3 text-[11px] text-slate-600 pt-1">
            <div class="flex items-center gap-1">
              <button @click="domainPage = Math.max(1, domainPage - 1)" :disabled="domainPage === 1" class="px-2 py-1 border border-slate-200 rounded disabled:opacity-40">&lt;</button>
              <span class="px-2.5 py-1 border border-emerald-600 text-emerald-600 font-semibold rounded bg-emerald-50">{{ domainPage }}</span>
              <button @click="domainPage = Math.min(domainTotalPages, domainPage + 1)" :disabled="domainPage >= domainTotalPages" class="px-2 py-1 border border-slate-200 rounded disabled:opacity-40">&gt;</button>
            </div>
            <select v-model.number="domainPageSize" class="border border-slate-200 rounded px-2 py-1 bg-white">
              <option :value="10">10 / page</option>
              <option :value="20">20 / page</option>
              <option :value="50">50 / page</option>
            </select>
            <span>Total {{ filteredZones.length }}</span>
          </div>
        </div>

        <!-- TAB 2B: DOMAIN MANAGEMENT -> MANAGE RESOLUTIONS VIEW -->
        <div v-else-if="activeTab === 'domains' && managingZone" class="space-y-3 flex-1 flex flex-col">
          <!-- Context Switcher Header Box -->
          <div class="border border-slate-200 rounded p-3 bg-slate-50/40 space-y-2">
            <div class="flex items-center gap-2">
              <select v-model="selectedProviderId" class="np-input w-56 bg-white">
                <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
              <button @click="refreshRecords" class="p-1.5 border border-slate-300 rounded bg-white hover:bg-slate-50 text-slate-600" title="Refresh Records">
                <RefreshCw class="w-3.5 h-3.5" />
              </button>
            </div>
            <div class="flex items-center gap-2">
              <div class="flex items-center border border-slate-300 rounded bg-white px-2.5 py-1 w-64">
                <span class="text-slate-500 mr-2">Domain:</span>
                <select
                  :value="managingZone.id"
                  @change="switchManagingZone($event)"
                  class="flex-1 bg-transparent font-semibold text-emerald-700 focus:outline-none"
                >
                  <option v-for="z in zones" :key="z.id" :value="z.id">{{ z.domain }}</option>
                </select>
              </div>
              <span class="text-[11px] text-slate-400 font-mono">Serial: {{ managingZone.serial }}</span>
            </div>
          </div>

          <!-- Action Toolbar -->
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <button @click="openAddRecord" class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">
                Add Resolution
              </button>
              <button @click="managingZone = null" class="px-3 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
                Return
              </button>
            </div>
            <input v-model="recordSearch" placeholder="Filter records by host or value..." class="np-input w-56" />
          </div>

          <!-- Resolutions Table -->
          <div class="border border-slate-200 rounded overflow-hidden">
            <table class="np-table">
              <thead>
                <tr class="bg-slate-50">
                  <th>Record</th>
                  <th>Type</th>
                  <th>Record Value</th>
                  <th>TTL</th>
                  <th>Proxy</th>
                  <th>Remark</th>
                  <th class="text-right">Operate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in paginatedRecords" :key="r.id" class="hover:bg-slate-50/80">
                  <td class="font-mono font-medium text-slate-800">{{ r.name }}</td>
                  <td>
                    <span class="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[11px] font-semibold text-slate-700">
                      {{ r.record_type }}
                    </span>
                  </td>
                  <td class="font-mono text-[11px] text-slate-700">
                    <div class="flex items-center gap-1.5">
                      <span class="truncate max-w-xs" :title="r.value">{{ r.value }}</span>
                      <span v-if="r.priority !== null && r.priority !== undefined" class="text-[10px] text-slate-400">(Pri: {{ r.priority }})</span>
                      <button @click="copyValue(r.value)" class="text-emerald-600 hover:text-emerald-700 text-[10px]" title="Copy Value">📋</button>
                    </div>
                  </td>
                  <td class="text-slate-600">{{ r.ttl === 300 ? 'Auto (300s)' : `${r.ttl}s` }}</td>
                  <td class="text-slate-400">--</td>
                  <td class="text-slate-500 text-[11px]">NexoPanel DNS Manager Sync</td>
                  <td class="text-right space-x-2.5">
                    <button @click="openEditRecord(r)" class="text-emerald-600 hover:underline font-medium">Edit</button>
                    <button @click="deleteRecord(r.id)" class="text-rose-600 hover:underline">Delete</button>
                  </td>
                </tr>
                <tr v-if="filteredRecords.length === 0">
                  <td colspan="7" class="p-8 text-center text-slate-400">
                    No DNS resolutions found for {{ managingZone.domain }}.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination Footer -->
          <div class="flex items-center justify-end gap-3 text-[11px] text-slate-600 pt-1">
            <div class="flex items-center gap-1">
              <button @click="recPage = Math.max(1, recPage - 1)" :disabled="recPage === 1" class="px-2 py-1 border border-slate-200 rounded disabled:opacity-40">&lt;</button>
              <span class="px-2.5 py-1 border border-emerald-600 text-emerald-600 font-semibold rounded bg-emerald-50">{{ recPage }}</span>
              <button @click="recPage = Math.min(recTotalPages, recPage + 1)" :disabled="recPage >= recTotalPages" class="px-2 py-1 border border-slate-200 rounded disabled:opacity-40">&gt;</button>
            </div>
            <select v-model.number="recPageSize" class="border border-slate-200 rounded px-2 py-1 bg-white">
              <option :value="10">10 / page</option>
              <option :value="20">20 / page</option>
              <option :value="50">50 / page</option>
            </select>
            <span>Total {{ filteredRecords.length }}</span>
          </div>
        </div>
      </div>

      <!-- CERTIFICATE SECTION -->
      <div v-else-if="activeSection === 'certificate'" class="space-y-3">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3">
          <div>
            <h2 class="text-sm font-bold text-slate-900">Domain SSL Certificates</h2>
            <p class="text-[11px] text-slate-500">Overview of Let's Encrypt ACME certificates bound to your managed domains.</p>
          </div>
          <NuxtLink to="/ssl" class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">
            Manage & Issue SSL
          </NuxtLink>
        </div>

        <div class="border border-slate-200 rounded overflow-hidden">
          <table class="np-table">
            <thead>
              <tr class="bg-slate-50">
                <th>Domain</th>
                <th>Issuer</th>
                <th>Challenge</th>
                <th>Status</th>
                <th>Expires At</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in certs" :key="c.id">
                <td class="font-semibold text-slate-800">{{ c.domain }}</td>
                <td>{{ c.issuer }}</td>
                <td class="font-mono text-[11px]">{{ c.challenge_type }}</td>
                <td>
                  <span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px]">{{ c.status }}</span>
                </td>
                <td class="text-[11px] text-slate-500">{{ c.expires_at ? formatDate(c.expires_at) : '-' }}</td>
              </tr>
              <tr v-if="certs.length === 0">
                <td colspan="5" class="p-8 text-center text-slate-400">No SSL certificates issued yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal: Add Domain Zone -->
    <div v-if="showZoneModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold text-slate-900">Add Domain Zone</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Domain Name</label>
          <input v-model="newZone.domain" placeholder="example.com" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Primary Nameserver</label>
          <input v-model="newZone.primary_ns" placeholder="ns1.example.com" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Admin Email</label>
          <input v-model="newZone.admin_email" placeholder="hostmaster@example.com" class="np-input" />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showZoneModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createZone" class="np-btn-primary">Create Zone</button>
        </div>
      </div>
    </div>

    <!-- Modal: Add / Edit Resolution Record -->
    <div v-if="showRecModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold text-slate-900">{{ editingRecordId ? 'Edit Resolution' : 'Add Resolution' }} — {{ managingZone?.domain }}</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Record Type</label>
          <select v-model="recForm.record_type" class="np-input">
            <option v-for="t in ['A','AAAA','CNAME','MX','TXT','NS','SRV','CAA']" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Host / Record Name</label>
          <input v-model="recForm.name" placeholder="@, www, mail, or subdomain" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Record Value</label>
          <input v-model="recForm.value" placeholder="192.0.2.10 or target hostname" class="np-input" />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-medium text-slate-600 mb-1">TTL (Seconds)</label>
            <select v-model.number="recForm.ttl" class="np-input">
              <option :value="300">Auto (300s)</option>
              <option :value="600">600s (10m)</option>
              <option :value="1800">1800s (30m)</option>
              <option :value="3600">3600s (1h)</option>
              <option :value="86400">86400s (24h)</option>
            </select>
          </div>
          <div v-if="recForm.record_type === 'MX' || recForm.record_type === 'SRV'">
            <label class="block text-[11px] font-medium text-slate-600 mb-1">Priority</label>
            <input v-model.number="recForm.priority" type="number" min="0" max="65535" placeholder="10" class="np-input" />
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showRecModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveRecord" class="np-btn-primary">{{ editingRecordId ? 'Save Changes' : 'Add Resolution' }}</button>
        </div>
      </div>
    </div>

    <!-- Modal: Add DNS Provider -->
    <div v-if="showProviderModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold text-slate-900">Add DNS Provider</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Account / Label Name</label>
          <input v-model="newProvider.name" placeholder="e.g. Cloudflare Main" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Provider</label>
          <select v-model="newProvider.provider_type" class="np-input">
            <option value="cloudflare">Cloudflare DNS</option>
            <option value="namecheap">NameCheapDns</option>
            <option value="digitalocean">DigitalOcean DNS</option>
            <option value="route53">AWS Route53</option>
            <option value="dnspod">DNSPod</option>
            <option value="aliyun">Aliyun DNS</option>
          </select>
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">API Token / Secret</label>
          <input v-model="newProvider.api_token" type="password" placeholder="Enter API key or token" class="np-input" />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showProviderModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createProvider" class="np-btn-primary">Save Provider</button>
        </div>
      </div>
    </div>

    <!-- Modal: Pull Log -->
    <div v-if="showLogsModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-2xl h-[65vh] flex flex-col">
        <div class="flex items-center justify-between border-b border-slate-200 pb-3 mb-3">
          <h3 class="text-sm font-bold text-slate-900">DNS Sync & Audit Logs</h3>
          <button @click="showLogsModal = false" class="np-btn-secondary">Close</button>
        </div>
        <div class="flex-1 overflow-y-auto border border-slate-200 rounded">
          <table class="np-table">
            <thead>
              <tr class="bg-slate-50">
                <th>Time</th>
                <th>User</th>
                <th>Action</th>
                <th>Target</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in dnsLogs" :key="l.id">
                <td class="text-[11px] text-slate-500">{{ formatDate(l.created_at) }}</td>
                <td class="font-medium">{{ l.actor }}</td>
                <td class="font-mono text-[11px]">{{ l.action }}</td>
                <td class="font-mono text-[11px]">{{ l.target }}</td>
                <td>
                  <span :class="l.status === 'success' ? 'text-emerald-600' : 'text-rose-600'" class="font-medium">{{ l.status }}</span>
                </td>
              </tr>
              <tr v-if="dnsLogs.length === 0">
                <td colspan="5" class="p-6 text-center text-slate-400">No DNS operation logs yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Globe, Plus, RefreshCw, Search } from 'lucide-vue-next'

const { apiFetch } = useApi()

const activeSection = ref<'domain' | 'certificate'>('domain')
const activeTab = ref<'providers' | 'domains'>('domains')

const providers = ref<any[]>([])
const selectedProviderId = ref<number>(0)
const zones = ref<any[]>([])
const managingZone = ref<any>(null)
const records = ref<any[]>([])
const certs = ref<any[]>([])
const dnsLogs = ref<any[]>([])

const domainSearch = ref('')
const recordSearch = ref('')
const domainPage = ref(1)
const domainPageSize = ref(10)
const recPage = ref(1)
const recPageSize = ref(10)
const pulling = ref(false)

const showZoneModal = ref(false)
const showRecModal = ref(false)
const showProviderModal = ref(false)
const showLogsModal = ref(false)
const editingRecordId = ref<number | null>(null)

const newZone = reactive({ domain: '', primary_ns: 'ns1.localhost.localdomain', admin_email: 'hostmaster@localhost.localdomain' })
const recForm = reactive<{ name: string; record_type: string; value: string; ttl: number; priority: number | null }>({
  name: '@',
  record_type: 'A',
  value: '',
  ttl: 300,
  priority: null,
})
const newProvider = reactive({ name: '', provider_type: 'cloudflare', api_token: '' })

const filteredZones = computed(() => {
  const q = domainSearch.value.trim().toLowerCase()
  if (!q) return zones.value
  return zones.value.filter((z) => z.domain.toLowerCase().includes(q))
})

const domainTotalPages = computed(() => Math.max(1, Math.ceil(filteredZones.value.length / domainPageSize.value)))
const paginatedZones = computed(() => {
  const start = (domainPage.value - 1) * domainPageSize.value
  return filteredZones.value.slice(start, start + domainPageSize.value)
})

const filteredRecords = computed(() => {
  const q = recordSearch.value.trim().toLowerCase()
  if (!q) return records.value
  return records.value.filter(
    (r) =>
      r.name.toLowerCase().includes(q) ||
      r.value.toLowerCase().includes(q) ||
      r.record_type.toLowerCase().includes(q)
  )
})

const recTotalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / recPageSize.value)))
const paginatedRecords = computed(() => {
  const start = (recPage.value - 1) * recPageSize.value
  return filteredRecords.value.slice(start, start + recPageSize.value)
})

function formatDate(iso: string) {
  if (!iso) return '-'
  return iso.replace('T', ' ').slice(0, 19)
}

async function load() {
  const [zList, pList] = await Promise.all([
    apiFetch<any[]>('/dns/zones'),
    apiFetch<any[]>('/dns/providers'),
  ])
  zones.value = zList || []
  providers.value = pList || []
}

async function loadCertificates() {
  try {
    certs.value = await apiFetch<any[]>('/ssl')
  } catch {
    certs.value = []
  }
}

async function enterManage(z: any) {
  managingZone.value = z
  recPage.value = 1
  recordSearch.value = ''
  await refreshRecords()
}

async function switchManagingZone(e: Event) {
  const id = Number((e.target as HTMLSelectElement).value)
  const target = zones.value.find((z) => z.id === id)
  if (target) await enterManage(target)
}

async function refreshRecords() {
  if (!managingZone.value) return
  records.value = await apiFetch<any[]>(`/dns/zones/${managingZone.value.id}/records`)
}

function openZoneModal() {
  newZone.domain = ''
  newZone.primary_ns = 'ns1.localhost.localdomain'
  newZone.admin_email = 'hostmaster@localhost.localdomain'
  showZoneModal.value = true
}

async function createZone() {
  await apiFetch('/dns/zones', { method: 'POST', body: newZone })
  showZoneModal.value = false
  await load()
}

async function deleteZone(z: any) {
  if (!confirm(`Delete DNS zone ${z.domain} and all its records?`)) return
  await apiFetch(`/dns/zones/${z.id}`, { method: 'DELETE' })
  await load()
}

function openAddRecord() {
  editingRecordId.value = null
  recForm.name = '@'
  recForm.record_type = 'A'
  recForm.value = ''
  recForm.ttl = 300
  recForm.priority = null
  showRecModal.value = true
}

function openEditRecord(r: any) {
  editingRecordId.value = r.id
  recForm.name = r.name
  recForm.record_type = r.record_type
  recForm.value = r.value
  recForm.ttl = r.ttl
  recForm.priority = r.priority ?? null
  showRecModal.value = true
}

async function saveRecord() {
  if (!managingZone.value) return
  const payload = {
    name: recForm.name,
    record_type: recForm.record_type,
    value: recForm.value,
    ttl: recForm.ttl,
    priority: (recForm.record_type === 'MX' || recForm.record_type === 'SRV') ? recForm.priority : null,
  }
  if (editingRecordId.value) {
    await apiFetch(`/dns/records/${editingRecordId.value}`, { method: 'PUT', body: payload })
  } else {
    await apiFetch(`/dns/zones/${managingZone.value.id}/records`, { method: 'POST', body: payload })
  }
  showRecModal.value = false
  await refreshRecords()
  await load()
}

async function deleteRecord(id: number) {
  if (!confirm('Delete this DNS resolution record?')) return
  await apiFetch(`/dns/records/${id}`, { method: 'DELETE' })
  await refreshRecords()
  await load()
}

async function pullData() {
  pulling.value = true
  try {
    await apiFetch('/dns/zones/pull', { method: 'POST' })
    await load()
  } finally {
    pulling.value = false
  }
}

async function openPullLogs() {
  dnsLogs.value = await apiFetch<any[]>('/dns/logs')
  showLogsModal.value = true
}

async function createProvider() {
  await apiFetch('/dns/providers', { method: 'POST', body: newProvider })
  showProviderModal.value = false
  newProvider.name = ''
  newProvider.api_token = ''
  await load()
}

async function deleteProvider(id: number) {
  if (!confirm('Remove this DNS provider credential?')) return
  await apiFetch(`/dns/providers/${id}`, { method: 'DELETE' })
  await load()
}

function copyValue(val: string) {
  navigator.clipboard?.writeText(val)
}

onMounted(load)
</script>
