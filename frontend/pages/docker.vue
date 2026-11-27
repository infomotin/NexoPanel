<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Docker Container Manager</h1>
        <p class="text-xs text-slate-500">Manage Docker containers and pull/inspect container images.</p>
      </div>
      <button @click="pullPrompt" class="np-btn-primary">+ Pull Image</button>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Containers</div>
      <table class="np-table">
        <thead><tr><th>ID</th><th>Name</th><th>Image</th><th>Status</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="c in containers" :key="c.ID">
            <td class="font-mono text-[11px]">{{ c.ID }}</td>
            <td class="font-semibold">{{ c.Names }}</td>
            <td class="font-mono text-[11px]">{{ c.Image }}</td>
            <td>{{ c.Status }}</td>
            <td class="text-right space-x-2">
              <button @click="control(c.ID, 'start')" class="text-emerald-600 hover:underline">Start</button>
              <button @click="control(c.ID, 'stop')" class="text-amber-600 hover:underline">Stop</button>
              <button @click="control(c.ID, 'restart')" class="text-blue-600 hover:underline">Restart</button>
            </td>
          </tr>
          <tr v-if="!containers.length">
            <td colspan="5" class="text-center text-slate-400 py-4">No containers found (or Docker daemon not running).</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const containers = ref<any[]>([])

async function load() {
  const res = await apiFetch<any>('/docker/containers')
  containers.value = res.containers || []
}
async function control(id: string, action: string) {
  await apiFetch(`/docker/containers/${id}/${action}`, { method: 'POST' })
  await load()
}
async function pullPrompt() {
  const image = prompt('Enter Docker image (e.g. redis:7-alpine):')
  if (!image) return
  await apiFetch('/docker/images/pull', { method: 'POST', body: { image } })
  await load()
}
onMounted(load)
</script>
