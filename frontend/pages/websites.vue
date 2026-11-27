<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Websites & Subdomains</h1>
        <p class="text-xs text-slate-500">Manage Nginx virtual hosts, PHP-FPM pools, reverse proxies, and custom directives.</p>
      </div>
      <div class="flex gap-2">
        <button v-if="auth.can('subdomains:write')" @click="showSubModal = true" class="np-btn-secondary">+ Add Subdomain</button>
        <button v-if="auth.can('websites:write')" @click="showSiteModal = true" class="np-btn-primary">+ Add Website</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Runtime</th>
            <th>Document Root</th>
            <th>SSL</th>
            <th>Status</th>
            <th class="text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="site in sites" :key="site.id">
            <td class="font-semibold text-slate-900">{{ site.domain }}</td>
            <td>
              <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[11px]">
                {{ site.runtime_type }}{{ site.runtime_type === 'php' ? ` (${site.php_version})` : '' }}
              </span>
            </td>
            <td class="font-mono text-[11px]">{{ site.document_root }}</td>
            <td>
              <span :class="site.ssl_enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'" class="px-2 py-0.5 rounded text-[11px]">
                {{ site.ssl_enabled ? 'HTTPS Active' : 'HTTP Only' }}
              </span>
            </td>
            <td><span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px]">{{ site.status }}</span></td>
            <td class="text-right space-x-2">
              <button @click="openDrawer(site)" class="text-emerald-600 hover:underline">Configure</button>
              <button v-if="auth.can('websites:delete')" @click="deleteSite(site.id)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Subdomains Table -->
    <div class="np-card overflow-hidden">
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
        <input v-model="newSite.domain" placeholder="example.com" class="np-input" />
        <select v-model="newSite.runtime_type" class="np-input">
          <option value="static">Static / SPA</option>
          <option value="php">PHP-FPM</option>
          <option value="proxy">Reverse Proxy</option>
        </select>
        <input v-if="newSite.runtime_type === 'proxy'" v-model="newSite.proxy_upstream" placeholder="http://127.0.0.1:3000" class="np-input" />
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showSiteModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createSite" class="np-btn-primary">Create</button>
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

    <!-- Slide-over Nginx Config Drawer -->
    <div v-if="editingSite" class="fixed inset-y-0 right-0 w-96 bg-white shadow-2xl border-l border-slate-200 p-5 z-50 flex flex-col">
      <h3 class="text-sm font-bold mb-3">Configure {{ editingSite.domain }}</h3>
      <label class="text-xs font-medium text-slate-600 mb-1">Custom Nginx Directives (validated via nginx -t)</label>
      <textarea v-model="editingSite.custom_directives" rows="10" class="np-input font-mono text-[11px] flex-1"></textarea>
      <div class="flex justify-end gap-2 mt-4">
        <button @click="editingSite = null" class="np-btn-secondary">Close</button>
        <button @click="saveSiteConfig" class="np-btn-primary">Validate & Save</button>
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
const showSiteModal = ref(false)
const showSubModal = ref(false)
const editingSite = ref<any>(null)
const newSite = reactive({ domain: '', runtime_type: 'static', php_version: '8.2', proxy_upstream: '' })
const newSub = reactive({ website_id: 0, prefix: '' })

async function load() {
  sites.value = await apiFetch('/sites')
  subdomains.value = await apiFetch('/sites/subdomains')
  if (sites.value.length && !newSub.website_id) newSub.website_id = sites.value[0].id
}

async function createSite() {
  await apiFetch('/sites', { method: 'POST', body: newSite })
  showSiteModal.value = false
  newSite.domain = ''
  await load()
}

async function createSubdomain() {
  await apiFetch('/sites/subdomains', { method: 'POST', body: newSub })
  showSubModal.value = false
  newSub.prefix = ''
  await load()
}

function openDrawer(site: any) {
  editingSite.value = { ...site }
}

async function saveSiteConfig() {
  await apiFetch(`/sites/${editingSite.value.id}`, {
    method: 'PUT',
    body: { custom_directives: editingSite.value.custom_directives },
  })
  editingSite.value = null
  await load()
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
