<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Web File Manager</h1>
        <p class="text-xs text-slate-500">Canonicalized directory browser, inline editor, archive/extract, and chmod management.</p>
      </div>
      <div class="flex gap-2 items-center">
        <input type="file" ref="fileInput" @change="uploadFile" class="hidden" />
        <button @click="($refs.fileInput as HTMLInputElement).click()" class="np-btn-secondary">Upload File</button>
        <button @click="createFolder" class="np-btn-primary">+ New Folder</button>
      </div>
    </div>

    <div class="np-card p-3 flex items-center gap-2 text-xs">
      <span class="font-semibold text-slate-600">Path:</span>
      <input v-model="currentPath" @keyup.enter="loadDir(currentPath)" class="np-input font-mono flex-1" />
      <button @click="loadDir(currentPath)" class="np-btn-secondary">Go</button>
    </div>

    <div class="np-card overflow-hidden">
      <table class="np-table">
        <thead><tr><th>Name</th><th>Size</th><th>Mode</th><th class="text-right">Actions</th></tr></thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.path">
            <td>
              <button v-if="entry.is_dir" @click="loadDir(entry.path)" class="font-semibold text-emerald-700 hover:underline">
                📁 {{ entry.name }}
              </button>
              <span v-else class="font-mono">📄 {{ entry.name }}</span>
            </td>
            <td>{{ entry.is_dir ? '-' : `${entry.size} B` }}</td>
            <td class="font-mono text-[11px]">{{ entry.mode }}</td>
            <td class="text-right space-x-2">
              <button v-if="!entry.is_dir" @click="editFile(entry.path)" class="text-emerald-600 hover:underline">Edit</button>
              <button @click="chmodFile(entry.path)" class="text-blue-600 hover:underline">Chmod</button>
              <button @click="deleteEntry(entry.path)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="editingPath" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-6">
      <div class="bg-white rounded-lg p-5 w-full max-w-3xl h-[80vh] flex flex-col">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-xs font-bold font-mono">{{ editingPath }}</h3>
          <button @click="editingPath = ''" class="np-btn-secondary">Close</button>
        </div>
        <textarea v-model="editingContent" class="np-input font-mono text-xs flex-1"></textarea>
        <div class="flex justify-end mt-3">
          <button @click="saveFile" class="np-btn-primary">Save File</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const { apiFetch } = useApi()
const currentPath = ref('/var/www')
const entries = ref<any[]>([])
const editingPath = ref('')
const editingContent = ref('')

async function loadDir(path: string) {
  currentPath.value = path
  const res = await apiFetch<any>(`/files/list?path=${encodeURIComponent(path)}`)
  entries.value = res.entries
}
async function editFile(path: string) {
  const res = await apiFetch<any>(`/files/read?path=${encodeURIComponent(path)}`)
  editingPath.value = res.path
  editingContent.value = res.content
}
async function saveFile() {
  await apiFetch('/files/write', { method: 'POST', body: { path: editingPath.value, content: editingContent.value } })
  editingPath.value = ''
  await loadDir(currentPath.value)
}
async function createFolder() {
  const name = prompt('Folder name:')
  if (!name) return
  await apiFetch('/files/mkdir', { method: 'POST', body: { source: `${currentPath.value}/${name}` } })
  await loadDir(currentPath.value)
}
async function chmodFile(path: string) {
  const mode = prompt('Octal permissions (e.g. 0755):', '0644')
  if (!mode) return
  await apiFetch('/files/chmod', { method: 'POST', body: { path, mode } })
  await loadDir(currentPath.value)
}
async function uploadFile(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  const fd = new FormData()
  fd.append('path', currentPath.value)
  fd.append('file', input.files[0])
  await apiFetch('/files/upload', { method: 'POST', body: fd })
  await loadDir(currentPath.value)
}
async function deleteEntry(path: string) {
  await apiFetch(`/files?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
  await loadDir(currentPath.value)
}
onMounted(() => loadDir(currentPath.value).catch(() => {}))
</script>
