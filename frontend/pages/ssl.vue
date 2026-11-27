<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">SSL / ACMEv2 Certificates</h1>
        <p class="text-xs text-slate-500">Issue Let's Encrypt certificates via HTTP-01 or DNS-01 wildcard challenges.</p>
      </div>
      <div class="flex gap-2">
        <button @click="showProviderModal = true" class="np-btn-secondary">+ DNS API Provider</button>
        <button @click="showIssueModal = true" class="np-btn-primary">+ Issue Certificate</button>
      </div>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead><tr><th>Domain</th><th>Challenge</th><th>Provider</th><th>Status</th><th>Expires</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="c in certs" :key="c.id">
            <td class="font-semibold">{{ c.domain }}</td>
            <td class="font-mono text-[11px]">{{ c.challenge_type }}</td>
            <td>{{ c.dns_provider || 'Webroot' }}</td>
            <td><span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px]">{{ c.status }}</span></td>
            <td class="text-[11px]">{{ c.expires_at ? new Date(c.expires_at).toLocaleDateString() : '-' }}</td>
            <td class="text-right"><button @click="revokeCert(c.id)" class="text-rose-600 hover:underline">Revoke</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="showIssueModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Issue SSL Certificate</h3>
        <input v-model="issueForm.domain" placeholder="example.com or *.example.com" class="np-input" />
        <select v-model="issueForm.challenge_type" class="np-input">
          <option value="http-01">HTTP-01 (Webroot)</option>
          <option value="dns-01">DNS-01 (Wildcard API)</option>
        </select>
        <select v-if="issueForm.challenge_type === 'dns-01'" v-model="issueForm.dns_provider_cred_id" class="np-input">
          <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }} ({{ p.provider_type }})</option>
        </select>
        <div class="flex justify-end gap-2">
          <button @click="showIssueModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="issueCert" class="np-btn-primary">Issue</button>
        </div>
      </div>
    </div>

    <div v-if="showProviderModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add DNS-01 Provider Credential</h3>
        <input v-model="provForm.name" placeholder="Cloudflare Prod" class="np-input" />
        <select v-model="provForm.provider_type" class="np-input">
          <option value="cloudflare">Cloudflare</option>
          <option value="digitalocean">DigitalOcean</option>
        </select>
        <input v-model="provForm.api_token" type="password" placeholder="API Token" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showProviderModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createProvider" class="np-btn-primary">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const certs = ref<any[]>([])
const providers = ref<any[]>([])
const showIssueModal = ref(false)
const showProviderModal = ref(false)
const issueForm = reactive({ domain: '', challenge_type: 'http-01', dns_provider_cred_id: null as number | null })
const provForm = reactive({ name: '', provider_type: 'cloudflare', api_token: '' })

async function load() {
  certs.value = await apiFetch('/ssl/certificates')
  providers.value = await apiFetch('/ssl/providers')
}
async function issueCert() {
  await apiFetch('/ssl/issue', { method: 'POST', body: issueForm })
  showIssueModal.value = false
  await load()
}
async function createProvider() {
  await apiFetch('/ssl/providers', { method: 'POST', body: provForm })
  showProviderModal.value = false
  await load()
}
async function revokeCert(id: number) {
  await apiFetch(`/ssl/${id}/revoke`, { method: 'POST' })
  await load()
}
onMounted(load)
</script>
