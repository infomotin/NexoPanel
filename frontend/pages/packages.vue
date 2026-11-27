<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">System Package Manager (APT)</h1>
        <p class="text-xs text-slate-500">Query installed Debian/Ubuntu packages and stream real-time apt-get transaction logs.</p>
      </div>
      <div class="flex gap-2">
        <input v-model="search" @keyup.enter="load" placeholder="Filter packages..." class="np-input w-48" />
        <button @click="installPrompt" class="np-btn-primary">+ Install Package</button>
      </div>
    </div>

    <div v-if="txLog.length" class="np-card p-3 bg-slate-900 text-emerald-400 font-mono text-[11px] max-h-48 overflow-y-auto">
      <div v-for="(line, i) in txLog" :key="i">{{ line }}</div>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead><tr><th>Package</th><th>Version</th><th>Status</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="p in packages" :key="p.name">
            <td class="font-mono font-semibold">{{ p.name }}</td>
            <td class="font-mono text-[11px]">{{ p.version }}</td>
            <td class="text-[11px]">{{ p.status }}</td>
            <td class="text-right"><button @click="runApt('remove', p.name)" class="text-rose-600 hover:underline">Remove</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch, apiBase } = useApi()
const search = ref('')
const packages = ref<any[]>([])
const txLog = ref<string[]>([])

async function load() {
  const res = await apiFetch<any>(`/system/packages?search=${encodeURIComponent(search.value)}`)
  packages.value = res.packages
}
async function installPrompt() {
  const pkg = prompt('Enter Debian package name to install:')
  if (pkg) await runApt('install', pkg)
}
async function runApt(action: string, pkg: string) {
  txLog.value = [`Running apt-get ${action} ${pkg}...`]
  const resp = await fetch(`${apiBase}/system/packages/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
    body: JSON.stringify({ packages: [pkg] }),
  })
  const reader = resp.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    const text = decoder.decode(value)
    for (const chunk of text.split('\n\n')) {
      if (chunk.startsWith('data: ')) {
        const parsed = JSON.parse(chunk.slice(6))
        if (parsed.line) txLog.value.push(parsed.line)
      }
    }
  }
  await load()
}
onMounted(load)
</script>
