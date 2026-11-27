<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Firewall (UFW) & Fail2Ban</h1>
        <p class="text-xs text-slate-500">Manage port ingress rules, UFW firewall state, and Fail2Ban IP bans.</p>
      </div>
      <div class="flex gap-2">
        <button @click="toggleUfw(!fwStatus.active)" class="np-btn-secondary">
          {{ fwStatus.active ? 'Disable UFW' : 'Enable UFW' }}
        </button>
        <button @click="showModal = true" class="np-btn-primary">+ Add Port Rule</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Firewall Rules</div>
      <table class="np-table">
        <thead><tr><th>Action</th><th>Port</th><th>Protocol</th><th>Source IP</th><th>Comment</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="r in rules" :key="r.id">
            <td><span :class="r.action === 'allow' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'" class="px-2 py-0.5 rounded uppercase text-[10px] font-bold">{{ r.action }}</span></td>
            <td class="font-mono font-semibold">{{ r.port }}</td>
            <td class="uppercase">{{ r.protocol }}</td>
            <td class="font-mono">{{ r.source_ip }}</td>
            <td>{{ r.comment }}</td>
            <td class="text-right"><button @click="deleteRule(r.id)" class="text-rose-600 hover:underline">Delete</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="np-card p-4 space-y-2">
      <div class="flex items-center justify-between">
        <h2 class="text-xs font-bold text-slate-800">Fail2Ban (sshd jail)</h2>
        <button @click="unbanPrompt" class="np-btn-secondary">Unban IP</button>
      </div>
      <pre class="bg-slate-900 text-slate-200 p-3 rounded text-[11px] font-mono">{{ fail2ban.raw || 'Fail2Ban status unavailable in dev mode' }}</pre>
    </div>

    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add Firewall Rule</h3>
        <input v-model="form.port" placeholder="443 or 8000:8100" class="np-input" />
        <select v-model="form.protocol" class="np-input">
          <option value="tcp">TCP</option>
          <option value="udp">UDP</option>
          <option value="any">Any</option>
        </select>
        <select v-model="form.action" class="np-input">
          <option value="allow">Allow</option>
          <option value="deny">Deny</option>
        </select>
        <input v-model="form.source_ip" placeholder="any or 203.0.113.5" class="np-input" />
        <input v-model="form.comment" placeholder="HTTPS ingress" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createRule" class="np-btn-primary">Add Rule</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const fwStatus = ref<any>({ active: false })
const rules = ref<any[]>([])
const fail2ban = ref<any>({})
const showModal = ref(false)
const form = reactive({ port: '443', protocol: 'tcp', action: 'allow', source_ip: 'any', comment: '' })

async function load() {
  fwStatus.value = await apiFetch('/firewall/status')
  rules.value = await apiFetch('/firewall/rules')
  fail2ban.value = await apiFetch('/firewall/fail2ban')
}
async function toggleUfw(enable: boolean) {
  await apiFetch(`/firewall/toggle?enable=${enable}`, { method: 'POST' })
  await load()
}
async function createRule() {
  await apiFetch('/firewall/rules', { method: 'POST', body: form })
  showModal.value = false
  await load()
}
async function deleteRule(id: number) {
  await apiFetch(`/firewall/rules/${id}`, { method: 'DELETE' })
  await load()
}
async function unbanPrompt() {
  const ip = prompt('Enter IP address to unban from sshd:')
  if (!ip) return
  await apiFetch('/firewall/fail2ban/unban', { method: 'POST', body: { jail: 'sshd', ip } })
  await load()
}
onMounted(load)
</script>
