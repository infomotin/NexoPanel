<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">DNS Zone & Record Management</h1>
        <p class="text-xs text-slate-500">Authoritative Bind9 zones with serial auto-increment and named-checkzone validation.</p>
      </div>
      <button @click="showZoneModal = true" class="np-btn-primary">+ Add Zone</button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="np-card p-3 space-y-1">
        <h3 class="text-xs font-bold text-slate-600 mb-2">Zones</h3>
        <button
          v-for="z in zones"
          :key="z.id"
          @click="selectZone(z)"
          :class="selectedZone?.id === z.id ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-white border-slate-200'"
          class="w-full text-left px-3 py-2 rounded border text-xs font-medium flex justify-between"
        >
          <span>{{ z.domain }}</span>
          <span class="font-mono text-[10px] text-slate-400">{{ z.serial }}</span>
        </button>
      </div>

      <div class="np-card overflow-hidden lg:col-span-2">
        <div class="px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
          <span class="text-xs font-bold">{{ selectedZone ? `Records for ${selectedZone.domain}` : 'Select a zone' }}</span>
          <button v-if="selectedZone" @click="showRecModal = true" class="np-btn-primary">+ Add Record</button>
        </div>
        <table class="np-table">
          <thead><tr><th>Name</th><th>Type</th><th>Value</th><th>TTL</th><th class="text-right">Actions</th></tr></thead>
          <tbody>
            <tr v-for="r in records" :key="r.id">
              <td class="font-mono">{{ r.name }}</td>
              <td><span class="px-1.5 py-0.5 rounded bg-slate-100 font-mono text-[11px]">{{ r.record_type }}</span></td>
              <td class="font-mono text-[11px]">{{ r.value }}</td>
              <td>{{ r.ttl }}</td>
              <td class="text-right"><button @click="deleteRecord(r.id)" class="text-rose-600 hover:underline">Delete</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showZoneModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Create DNS Zone</h3>
        <input v-model="newZone.domain" placeholder="example.com" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showZoneModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createZone" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <div v-if="showRecModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Add DNS Record</h3>
        <select v-model="newRec.record_type" class="np-input">
          <option v-for="t in ['A','AAAA','CNAME','MX','TXT','NS','SRV','CAA']" :key="t">{{ t }}</option>
        </select>
        <input v-model="newRec.name" placeholder="@ or www" class="np-input" />
        <input v-model="newRec.value" placeholder="192.0.2.10" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="showRecModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="addRecord" class="np-btn-primary">Add</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const zones = ref<any[]>([])
const selectedZone = ref<any>(null)
const records = ref<any[]>([])
const showZoneModal = ref(false)
const showRecModal = ref(false)
const newZone = reactive({ domain: '' })
const newRec = reactive({ name: '@', record_type: 'A', value: '', ttl: 300 })

async function load() {
  zones.value = await apiFetch('/dns/zones')
  if (zones.value.length && !selectedZone.value) {
    await selectZone(zones.value[0])
  }
}
async function selectZone(z: any) {
  selectedZone.value = z
  records.value = await apiFetch(`/dns/zones/${z.id}/records`)
}
async function createZone() {
  await apiFetch('/dns/zones', { method: 'POST', body: newZone })
  showZoneModal.value = false
  await load()
}
async function addRecord() {
  await apiFetch(`/dns/zones/${selectedZone.value.id}/records`, { method: 'POST', body: newRec })
  showRecModal.value = false
  await selectZone(selectedZone.value)
}
async function deleteRecord(id: number) {
  await apiFetch(`/dns/records/${id}`, { method: 'DELETE' })
  await selectZone(selectedZone.value)
}
onMounted(load)
</script>
