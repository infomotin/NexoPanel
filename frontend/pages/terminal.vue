<template>
  <div class="space-y-3 h-full flex flex-col">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Authenticated Web Terminal</h1>
        <p class="text-xs text-slate-500">Interactive PTY session over WebSockets with JWT handshake verification.</p>
      </div>
      <span :class="connected ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-200 text-slate-600'" class="px-2 py-1 rounded text-xs font-medium">
        {{ connected ? 'Connected' : 'Disconnected' }}
      </span>
    </div>
    <div ref="termContainer" class="flex-1 min-h-[420px] bg-[#0f172a] rounded-lg p-2 border border-slate-800"></div>
  </div>
</template>

<script setup lang="ts">
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { wsBase } = useApi()
const termContainer = ref<HTMLElement | null>(null)
const connected = ref(false)

let term: Terminal | null = null
let ws: WebSocket | null = null

onMounted(() => {
  if (!termContainer.value || !auth.token) return
  term = new Terminal({ cursorBlink: true, fontSize: 13, theme: { background: '#0f172a' } })
  const fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(termContainer.value)
  fitAddon.fit()

  ws = new WebSocket(`${wsBase}/terminal/ws?token=${encodeURIComponent(auth.token)}`)
  ws.onopen = () => {
    connected.value = true
    ws?.send(JSON.stringify({ resize: true, rows: term?.rows || 24, cols: term?.cols || 80 }))
  }
  ws.onmessage = (evt) => term?.write(evt.data)
  ws.onclose = () => { connected.value = false }
  term.onData((data) => ws?.send(data))
})

onUnmounted(() => {
  ws?.close()
  term?.dispose()
})
</script>
