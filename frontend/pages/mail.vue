<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Mail Server & Routing Engine</h1>
        <p class="text-xs text-slate-500">Manage Postfix/Dovecot domains, mailboxes, DKIM/SPF/DMARC readiness, and outbound SMTP relay.</p>
      </div>
      <div class="flex gap-2">
        <button @click="flushQueue" class="np-btn-secondary">Flush Postfix Queue</button>
        <button @click="showDomainModal = true" class="np-btn-primary">+ Add Mail Domain</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Mail Domains</div>
      <table class="np-table">
        <thead>
          <tr><th>Domain</th><th>DKIM Selector</th><th>Outbound Mode</th><th>Relay Host</th><th class="text-right">Actions</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in domains" :key="d.id">
            <td class="font-semibold">{{ d.domain }}</td>
            <td class="font-mono text-[11px]">{{ d.dkim_selector }}</td>
            <td><span class="px-2 py-0.5 rounded bg-slate-100 text-[11px]">{{ d.outbound_mode }}</span></td>
            <td class="font-mono text-[11px]">{{ d.relay_host || 'Direct Egress' }}</td>
            <td class="text-right space-x-2">
              <button @click="inspectDns(d.id)" class="text-emerald-600 hover:underline">DNS Readiness</button>
              <button @click="openMailboxModal(d.id)" class="text-blue-600 hover:underline">+ Mailbox</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="dnsReport" class="np-card p-4 space-y-2">
      <h3 class="text-xs font-bold text-slate-800">DNS Readiness Inspector: {{ dnsReport.domain }}</h3>
      <div v-for="rec in dnsReport.required_records" :key="rec.name + rec.type" class="p-2 rounded bg-slate-50 border border-slate-200 text-xs">
        <div class="flex justify-between font-semibold">
          <span>{{ rec.type }} · {{ rec.name }}</span>
          <span class="text-slate-500">{{ rec.purpose }}</span>
        </div>
        <div class="font-mono text-[11px] text-slate-700 break-all mt-1">{{ rec.value }}</div>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Virtual Mailboxes</div>
      <table class="np-table">
        <thead><tr><th>Email</th><th>Quota (MB)</th><th>Status</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="m in mailboxes" :key="m.id">
            <td class="font-mono">{{ m.email }}</td>
            <td>{{ m.quota_mb }} MB</td>
            <td>{{ m.is_active ? 'Active' : 'Disabled' }}</td>
            <td class="text-right"><button @click="deleteMailbox(m.id)" class="text-rose-600 hover:underline">Delete</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showDomainModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add Mail Domain</h3>
        <input v-model="newDomain.domain" placeholder="example.com" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showDomainModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createDomain" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <div v-if="showMboxModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Create Mailbox</h3>
        <input v-model="newMbox.local_part" placeholder="info" class="np-input" />
        <input v-model="newMbox.password" type="password" placeholder="Password (min 8 chars)" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showMboxModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createMailbox" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const domains = ref<any[]>([])
const mailboxes = ref<any[]>([])
const dnsReport = ref<any>(null)
const showDomainModal = ref(false)
const showMboxModal = ref(false)
const newDomain = reactive({ domain: '' })
const newMbox = reactive({ mail_domain_id: 0, local_part: '', password: '' })

async function load() {
  domains.value = await apiFetch('/mail/domains')
  mailboxes.value = await apiFetch('/mail/mailboxes')
}
async function createDomain() {
  await apiFetch('/mail/domains', { method: 'POST', body: newDomain })
  showDomainModal.value = false
  await load()
}
function openMailboxModal(domainId: number) {
  newMbox.mail_domain_id = domainId
  showMboxModal.value = true
}
async function createMailbox() {
  await apiFetch('/mail/mailboxes', { method: 'POST', body: newMbox })
  showMboxModal.value = false
  await load()
}
async function deleteMailbox(id: number) {
  await apiFetch(`/mail/mailboxes/${id}`, { method: 'DELETE' })
  await load()
}
async function inspectDns(id: number) {
  dnsReport.value = await apiFetch(`/mail/domains/${id}/dns-readiness`)
}
async function flushQueue() {
  await apiFetch('/mail/queue/flush', { method: 'POST' })
}
onMounted(load)
</script>
