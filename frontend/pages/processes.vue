<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Task & Process Manager</h1>
        <p class="text-xs text-slate-500">Inspect running host processes, resource usage, and listening network ports.</p>
      </div>
      <button @click="load" class="np-btn-secondary">Refresh</button>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Top Processes</div>
      <table class="np-table">
        <thead><tr><th>PID</th><th>Name</th><th>User</th><th>CPU %</th><th>RAM %</th><th>Status</th><th class="text-right">Action</th></tr></thead>
        <tbody>
          <tr v-for="p in procs" :key="p.pid">
            <td class="font-mono">{{ p.pid }}</td>
            <td class="font-semibold">{{ p.name }}</td>
            <td>{{ p.username }}</td>
            <td>{{ p.cpu_percent }}%</td>
            <td>{{ p.memory_percent }}%</td>
            <td>{{ p.status }}</td>
            <td class="text-right"><button @click="killProc(p.pid)" class="text-rose-600 hover:underline">Terminate</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="np-card overflow-hidden">
      <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-xs">Listening Network Ports</div>
      <table class="np-table">
        <thead><tr><th>Port</th><th>Bind IP</th><th>Family</th><th>PID</th></tr></thead>
        <tbody>
          <tr v-for="(port, idx) in ports" :key="idx">
            <td class="font-mono font-semibold">{{ port.port }}</td>
            <td class="font-mono">{{ port.ip }}</td>
            <td>{{ port.family }}</td>
            <td class="font-mono">{{ port.pid || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const procs = ref<any[]>([])
const ports = ref<any[]>([])

async function load() {
  procs.value = await apiFetch('/processes?limit=30')
  ports.value = await apiFetch('/processes/ports')
}
async function killProc(pid: number) {
  await apiFetch(`/processes/${pid}/kill`, { method: 'POST' })
  await load()
}
onMounted(load)
</script>
