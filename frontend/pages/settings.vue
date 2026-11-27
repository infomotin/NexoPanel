<template>
  <div class="space-y-4">
    <div>
      <h1 class="text-base font-bold text-slate-900">Panel Settings</h1>
      <p class="text-xs text-slate-500">Global control-plane configuration stored in SQLite WAL.</p>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead><tr><th>Key</th><th>Value</th><th class="text-right">Action</th></tr></thead>
        <tbody>
          <tr v-for="s in settingsList" :key="s.key">
            <td class="font-mono font-semibold">{{ s.key }}</td>
            <td><input v-model="s.value" class="np-input font-mono text-xs" /></td>
            <td class="text-right"><button @click="saveSetting(s)" class="np-btn-primary">Save</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const settingsList = ref<any[]>([])

async function load() {
  settingsList.value = await apiFetch('/system/settings')
}
async function saveSetting(s: any) {
  await apiFetch(`/system/settings/${s.key}`, { method: 'PUT', body: { value: s.value } })
}
onMounted(load)
</script>
