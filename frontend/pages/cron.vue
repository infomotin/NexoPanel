<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Cron Jobs & Scheduled Tasks</h1>
        <p class="text-xs text-slate-500">Schedule shell scripts, URL webhooks, automated backups, and log rotation.</p>
      </div>
      <button @click="showModal = true" class="np-btn-primary">+ Add Cron Job</button>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead>
          <tr><th>Name</th><th>Type</th><th>Schedule</th><th>Target</th><th>Last Run</th><th>Status</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          <tr v-for="j in jobs" :key="j.id">
            <td class="font-semibold">{{ j.name }}</td>
            <td class="uppercase text-[11px]">{{ j.job_type }}</td>
            <td class="font-mono text-[11px]">{{ j.schedule }}</td>
            <td class="font-mono text-[11px] truncate max-w-xs">{{ j.command_or_target }}</td>
            <td class="text-[11px]">{{ j.last_run_at ? new Date(j.last_run_at).toLocaleString() : 'Never' }}</td>
            <td>
              <span :class="j.is_enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="px-2 py-0.5 rounded text-[11px]">
                {{ j.is_enabled ? 'Active' : 'Paused' }}
              </span>
            </td>
            <td class="text-right space-x-2">
              <button @click="runNow(j.id)" class="text-emerald-600 hover:underline">Run Now</button>
              <button @click="toggleJob(j.id)" class="text-blue-600 hover:underline">{{ j.is_enabled ? 'Pause' : 'Resume' }}</button>
              <button @click="deleteJob(j.id)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Create Scheduled Task</h3>
        <input v-model="form.name" placeholder="Nightly Log Rotation" class="np-input" />
        <select v-model="form.job_type" class="np-input">
          <option value="shell">Shell Command</option>
          <option value="url">URL Webhook</option>
          <option value="backup_site">Backup Website</option>
          <option value="backup_db">Backup Database</option>
          <option value="log_rotate">Rotate Nginx Logs</option>
        </select>
        <input v-model="form.schedule" placeholder="0 2 * * *" class="np-input font-mono" />
        <input v-model="form.command_or_target" placeholder="https://example.com/cron or domain.com" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createJob" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const jobs = ref<any[]>([])
const showModal = ref(false)
const form = reactive({ name: '', job_type: 'url', schedule: '0 2 * * *', command_or_target: '' })

async function load() {
  jobs.value = await apiFetch('/cron')
}
async function createJob() {
  await apiFetch('/cron', { method: 'POST', body: form })
  showModal.value = false
  await load()
}
async function runNow(id: number) {
  await apiFetch(`/cron/${id}/run`, { method: 'POST' })
  await load()
}
async function toggleJob(id: number) {
  await apiFetch(`/cron/${id}/toggle`, { method: 'POST' })
  await load()
}
async function deleteJob(id: number) {
  await apiFetch(`/cron/${id}`, { method: 'DELETE' })
  await load()
}
onMounted(load)
</script>
