<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Backup & Disaster Recovery</h1>
        <p class="text-xs text-slate-500">Scheduled & manual backups for websites, databases, and mail directories with one-click restore.</p>
      </div>
      <button @click="showModal = true" class="np-btn-primary">+ Run Backup Now</button>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Backup Manifests</div>
      <table class="np-table">
        <thead><tr><th>Type</th><th>Target</th><th>Backend</th><th>Size</th><th>Checksum (SHA256)</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="m in manifests" :key="m.id">
            <td class="uppercase text-[11px] font-semibold">{{ m.target_type }}</td>
            <td class="font-mono">{{ m.target_identifier }}</td>
            <td>{{ m.storage_backend }}</td>
            <td>{{ m.size_bytes }} B</td>
            <td class="font-mono text-[10px]">{{ m.checksum_sha256.slice(0, 16) }}...</td>
            <td class="text-right"><button @click="restore(m.id)" class="text-emerald-600 hover:underline">Restore</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Run Manual Backup</h3>
        <select v-model="form.target_type" class="np-input">
          <option value="website">Website Files</option>
          <option value="database">Database Dump</option>
          <option value="mail">Mail Directory</option>
        </select>
        <input v-model="form.target_identifier" placeholder="example.com or db_name" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="runBackup" class="np-btn-primary">Start Backup</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const manifests = ref<any[]>([])
const showModal = ref(false)
const form = reactive({ target_type: 'website', target_identifier: '' })

async function load() {
  manifests.value = await apiFetch('/backups/manifests')
}
async function runBackup() {
  await apiFetch('/backups/run', { method: 'POST', body: form })
  showModal.value = false
  await load()
}
async function restore(id: number) {
  await apiFetch(`/backups/manifests/${id}/restore`, { method: 'POST' })
}
onMounted(load)
</script>
