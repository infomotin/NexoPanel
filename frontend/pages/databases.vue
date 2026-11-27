<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Database Administration</h1>
        <p class="text-xs text-slate-500">Provision MariaDB/MySQL and PostgreSQL databases, users, and rotate passwords.</p>
      </div>
      <button v-if="auth.can('databases:write')" @click="showModal = true" class="np-btn-primary">+ Create Database</button>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead>
          <tr><th>Engine</th><th>Database</th><th>Username</th><th>Host</th><th>Charset</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          <tr v-for="db in databases" :key="db.id">
            <td class="uppercase font-semibold text-[11px]">{{ db.engine }}</td>
            <td class="font-mono">{{ db.db_name }}</td>
            <td class="font-mono">{{ db.db_user }}</td>
            <td>{{ db.db_host }}</td>
            <td>{{ db.charset }}</td>
            <td class="text-right space-x-2">
              <button @click="rotatePassword(db.id)" class="text-emerald-600 hover:underline">Rotate Password</button>
              <button v-if="auth.can('databases:delete')" @click="dropDb(db.id)" class="text-rose-600 hover:underline">Drop</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Create Database</h3>
        <select v-model="form.engine" class="np-input">
          <option value="mariadb">MariaDB / MySQL</option>
          <option value="postgresql">PostgreSQL</option>
        </select>
        <input v-model="form.db_name" placeholder="app_prod" class="np-input" />
        <input v-model="form.db_user" placeholder="app_user" class="np-input" />
        <input v-model="form.db_password" type="password" placeholder="Strong password (min 8 chars)" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createDb" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch } = useApi()
const databases = ref<any[]>([])
const showModal = ref(false)
const form = reactive({ engine: 'mariadb', db_name: '', db_user: '', db_password: '' })

async function load() {
  databases.value = await apiFetch('/databases')
}
async function createDb() {
  await apiFetch('/databases', { method: 'POST', body: form })
  showModal.value = false
  await load()
}
async function rotatePassword(id: number) {
  const new_password = prompt('Enter new database password (min 8 chars):')
  if (!new_password) return
  await apiFetch(`/databases/${id}/rotate-password`, { method: 'POST', body: { new_password } })
}
async function dropDb(id: number) {
  await apiFetch(`/databases/${id}`, { method: 'DELETE' })
  await load()
}
onMounted(load)
</script>
