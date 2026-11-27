<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Granular RBAC & Users</h1>
        <p class="text-xs text-slate-500">Compose fine-grained permission roles and manage local panel accounts.</p>
      </div>
      <div class="flex gap-2">
        <button @click="showRoleModal = true" class="np-btn-secondary">+ Create Role</button>
        <button @click="showUserModal = true" class="np-btn-primary">+ Create User</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Panel Users</div>
      <table class="np-table">
        <thead><tr><th>Username</th><th>Email</th><th>Role</th><th>2FA</th><th>Active</th></tr></thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="font-semibold">{{ u.username }}</td>
            <td>{{ u.email }}</td>
            <td><span class="px-2 py-0.5 rounded bg-slate-100 text-[11px]">{{ u.role_name }}</span></td>
            <td>{{ u.totp_enabled ? 'Enabled' : 'Off' }}</td>
            <td>{{ u.is_active ? 'Active' : 'Disabled' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Roles</div>
      <table class="np-table">
        <thead><tr><th>Role</th><th>Description</th><th>Permissions</th></tr></thead>
        <tbody>
          <tr v-for="r in roles" :key="r.id">
            <td class="font-semibold">{{ r.name }}</td>
            <td>{{ r.description }}</td>
            <td class="font-mono text-[10px]">{{ r.permissions.slice(0, 6).join(', ') }}{{ r.permissions.length > 6 ? '...' : '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showUserModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Create Panel User</h3>
        <input v-model="userForm.username" placeholder="operator1" class="np-input" />
        <input v-model="userForm.email" placeholder="operator@example.com" class="np-input" />
        <input v-model="userForm.password" type="password" placeholder="Password" class="np-input" />
        <select v-model="userForm.role_id" class="np-input">
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
        <div class="flex justify-end gap-2">
          <button @click="showUserModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createUser" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <div v-if="showRoleModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-lg space-y-3">
        <h3 class="text-sm font-bold">Create Custom Role</h3>
        <input v-model="roleForm.name" placeholder="DNS Manager" class="np-input" />
        <input v-model="roleForm.description" placeholder="Description" class="np-input" />
        <div class="max-h-48 overflow-y-auto grid grid-cols-2 gap-1 text-xs border p-2 rounded">
          <label v-for="p in allPerms" :key="p" class="flex items-center gap-1.5">
            <input type="checkbox" :value="p" v-model="roleForm.permissions" />
            <span class="font-mono text-[11px]">{{ p }}</span>
          </label>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="showRoleModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createRole" class="np-btn-primary">Create Role</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const users = ref<any[]>([])
const roles = ref<any[]>([])
const allPerms = ref<string[]>([])
const showUserModal = ref(false)
const showRoleModal = ref(false)
const userForm = reactive({ username: '', email: '', password: '', role_id: 1 })
const roleForm = reactive({ name: '', description: '', permissions: [] as string[] })

async function load() {
  users.value = await apiFetch('/rbac/users')
  roles.value = await apiFetch('/rbac/roles')
  const pRes = await apiFetch<any>('/rbac/permissions')
  allPerms.value = pRes.permissions
}
async function createUser() {
  await apiFetch('/rbac/users', { method: 'POST', body: userForm })
  showUserModal.value = false
  await load()
}
async function createRole() {
  await apiFetch('/rbac/roles', { method: 'POST', body: roleForm })
  showRoleModal.value = false
  await load()
}
onMounted(load)
</script>
