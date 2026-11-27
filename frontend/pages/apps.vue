<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-base font-bold text-slate-900">One-Click Web Applications</h1>
      <p class="text-xs text-slate-500">Deploy curated WordPress, Laravel, Static/SPA, Node.js, and Python application stacks.</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="app in catalog" :key="app.slug" class="np-card p-4 flex flex-col justify-between space-y-3">
        <div>
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-bold text-slate-900">{{ app.name }}</h3>
            <span class="px-2 py-0.5 rounded bg-slate-100 text-[10px] font-medium">{{ app.category }}</span>
          </div>
          <p class="text-xs text-slate-500 mt-1.5">{{ app.description }}</p>
        </div>
        <button @click="openDeploy(app)" class="np-btn-primary justify-center">Deploy {{ app.name }}</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Installed Applications</div>
      <table class="np-table">
        <thead><tr><th>App</th><th>Domain</th><th>Install Path</th><th>Database</th><th>Status</th></tr></thead>
        <tbody>
          <tr v-for="inst in installed" :key="inst.id">
            <td class="font-semibold uppercase text-[11px]">{{ inst.app_slug }}</td>
            <td>{{ inst.domain }}</td>
            <td class="font-mono text-[11px]">{{ inst.install_path }}</td>
            <td class="font-mono text-[11px]">{{ inst.db_name || '-' }}</td>
            <td><span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px]">{{ inst.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selectedApp" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Deploy {{ selectedApp.name }}</h3>
        <input v-model="deployForm.domain" placeholder="app.example.com" class="np-input" />
        <input v-if="selectedApp.runtime === 'proxy'" v-model.number="deployForm.proxy_port" type="number" placeholder="3000" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="selectedApp = null" class="np-btn-secondary">Cancel</button>
          <button @click="deployApp" class="np-btn-primary">Deploy</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const catalog = ref<any[]>([])
const installed = ref<any[]>([])
const selectedApp = ref<any>(null)
const deployForm = reactive({ app_slug: '', domain: '', proxy_port: 3000 })

async function load() {
  catalog.value = await apiFetch('/apps/catalog')
  installed.value = await apiFetch('/apps/installed')
}
function openDeploy(app: any) {
  selectedApp.value = app
  deployForm.app_slug = app.slug
}
async function deployApp() {
  await apiFetch('/apps/deploy', { method: 'POST', body: deployForm })
  selectedApp.value = null
  await load()
}
onMounted(load)
</script>
