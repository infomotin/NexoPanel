<template>
  <div class="space-y-3 h-full flex flex-col">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base font-bold text-slate-900">Authenticated Web Terminal</h1>
        <p class="text-xs text-slate-500">Interactive PTY session over WebSockets with JWT handshake verification.</p>
      </div>
      <div class="flex items-center gap-2">
        <span :class="connected ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-200 text-slate-600'" class="px-2 py-1 rounded text-xs font-medium flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full" :class="connected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'"></span>
          {{ connected ? 'Connected' : 'Disconnected' }}
        </span>
        <button
          v-if="!connected"
          @click="reconnect"
          class="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          Reconnect
        </button>
        <button
          v-if="connected"
          @click="clearTerminal"
          class="px-3 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium"
        >
          Clear
        </button>
      </div>
    </div>
    <div ref="termContainer" class="flex-1 min-h-[520px] bg-[#0f172a] rounded-lg p-2 border border-slate-800"></div>
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
let fitAddon: any = null
let ws: WebSocket | null = null
let pingTimer: any = null
let reconnectTimer: any = null
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 5
const PING_INTERVAL_MS = 15_000  // Send keepalive every 15 seconds
const RECONNECT_DELAY_MS = 2_000

function initTerminal() {
  if (!termContainer.value) return
  if (term) {
    term.dispose()
    term = null
  }
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
    theme: {
      background: '#0f172a',
      foreground: '#e2e8f0',
      cursor: '#10b981',
      selectionBackground: '#1e3a5f',
      black: '#1e293b',
      brightBlack: '#475569',
      red: '#f87171',
      brightRed: '#fca5a5',
      green: '#34d399',
      brightGreen: '#6ee7b7',
      yellow: '#fbbf24',
      brightYellow: '#fcd34d',
      blue: '#60a5fa',
      brightBlue: '#93c5fd',
      magenta: '#c084fc',
      brightMagenta: '#d8b4fe',
      cyan: '#22d3ee',
      brightCyan: '#67e8f9',
      white: '#e2e8f0',
      brightWhite: '#f8fafc',
    },
  })
  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(termContainer.value)
  fitAddon.fit()
  term.onData((data) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  })
  term.onResize(({ rows, cols }) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', resize: true, rows, cols }))
    }
  })
}

function connect() {
  if (ws) {
    ws.onclose = null
    ws.onerror = null
    try { ws.close() } catch {}
    ws = null
  }

  if (!auth.isAuthenticated) return

  ws = new WebSocket(`${wsBase}/terminal/ws`)

  ws.onopen = () => {
    connected.value = true
    reconnectAttempts = 0
    // Send initial size
    if (fitAddon) {
      fitAddon.fit()
    }
    ws?.send(JSON.stringify({ type: 'resize', resize: true, rows: term?.rows || 24, cols: term?.cols || 80 }))
    // Start sending keepalive pings to prevent proxy/idle timeout disconnects
    if (pingTimer) clearInterval(pingTimer)
    pingTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, PING_INTERVAL_MS)
  }

  ws.onmessage = (evt) => {
    try {
      const parsed = JSON.parse(evt.data)
      // Server keepalive pong – ignore silently
      if (parsed?.type === 'pong' || parsed?.type === 'ping') return
    } catch {
      // Not JSON – raw PTY output
    }
    term?.write(evt.data)
  }

  ws.onclose = (evt) => {
    connected.value = false
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null }

    // Show disconnect reason in terminal
    const reason = evt.code === 4401 ? 'Authentication failed.' :
                   evt.code === 4403 ? 'Permission denied (terminal:execute).' :
                   `Connection closed (code ${evt.code}).`
    term?.writeln(`\r\n\x1b[33m[NexoPanel] ${reason}\x1b[0m`)

    // Auto-reconnect unless intentionally closed or auth failure
    if (evt.code !== 4401 && evt.code !== 4403 && evt.code !== 1000 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++
      const delay = RECONNECT_DELAY_MS * reconnectAttempts
      term?.writeln(`\x1b[33m[NexoPanel] Reconnecting in ${delay / 1000}s (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...\x1b[0m`)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connect, delay)
    } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      term?.writeln(`\x1b[31m[NexoPanel] Max reconnect attempts reached. Click 'Reconnect' to try again.\x1b[0m`)
    }
  }

  ws.onerror = () => {
    term?.writeln('\r\n\x1b[31m[NexoPanel] WebSocket error occurred.\x1b[0m')
  }
}

function reconnect() {
  reconnectAttempts = 0
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  connect()
}

function clearTerminal() {
  term?.clear()
}

onMounted(() => {
  if (!termContainer.value || !auth.isAuthenticated) return
  initTerminal()
  connect()
})

onUnmounted(() => {
  if (pingTimer) clearInterval(pingTimer)
  if (reconnectTimer) clearTimeout(reconnectTimer)
  ws?.close(1000)
  term?.dispose()
})
</script>
