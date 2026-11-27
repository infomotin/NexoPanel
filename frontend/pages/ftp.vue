<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">FTP Account Management</h1>
        <p class="text-xs text-slate-500">Create isolated FTP accounts mapped to website document roots with quota & status controls.</p>
      </div>
      <button @click="showModal = true" class="np-btn-primary">+ Add FTP Account</button>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead><tr><th>Username</th><th>Home Directory</th><th>Quota</th><th>Status</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="a in accounts" :key="a.id">
            <td class="font-mono font-semibold">{{ a.username }}</td>
            <td class="font-mono text-[11px]">{{ a.home_directory }}</td>
            <td>{{ a.quota_mb ? `${a.quota_mb} MB` : 'Unlimited' }}</td>
            <td>
              <span :class="a.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'" class="px-2 py-0.5 rounded text-[11px]">
                {{ a.is_active ? 'Active' : 'Disabled' }}
              </span>
            </td>
            <td class="text-right space-x-2">
              <button @click="toggleAccount(a.id)" class="text-blue-600 hover:underline">{{ a.is_active ? 'Disable' : 'Enable' }}</button>
              <button @click="deleteAccount(a.id)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add FTP Account</h3>
        <input v-model="form.username" placeholder="ftp_site1" class="np-input" />
        <input v-model="form.password" type="password" placeholder="Password (min 8 chars)" class="np-input" />
        <input v-model="form.home_directory" placeholder="/var/www/example.com/public" class="np-input font-mono" />
        <input v-model.number="form.quota_mb" type="number" placeholder="0 (Unlimited)" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createAccount" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const accounts = ref<any[]>([])
const showModal = ref(false)
const form = reactive({ username: '', password: '', home_directory: '/var/www', quota_mb: 0 })

async function load() {
  accounts.value = await apiFetch('/ftp')
}
async function createAccount() {
  await apiFetch('/ftp', { method: 'POST', body: form })
  showModal.value = false
  await load()
}
async function toggleAccount(id: number) {
  await apiFetch(`/ftp/${id}/toggle`, { method: 'POST' })
  await load()
}
async function deleteAccount(id: number) {
  await apiFetch(`/ftp/${id}`, { method: 'DELETE' })
  await load()
}
onMounted(load)
</script>
