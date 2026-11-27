<template>
  <div class="flex h-screen overflow-hidden bg-slate-100">
    <!-- Fixed Collapsible Left Sidebar -->
    <aside
      :class="collapsed ? 'w-16' : 'w-56'"
      class="bg-[#161b26] text-slate-300 flex flex-col transition-all duration-200 shrink-0 border-r border-slate-800"
    >
      <div class="h-12 flex items-center justify-between px-3 border-b border-slate-800">
        <div v-if="!collapsed" class="flex items-center gap-2">
          <div class="w-6 h-6 rounded bg-emerald-500 flex items-center justify-center text-white font-bold text-xs">N</div>
          <span class="font-semibold text-white text-sm tracking-tight">NexoPanel</span>
        </div>
        <button @click="collapsed = !collapsed" class="p-1 rounded hover:bg-slate-800 text-slate-400">
          <PanelLeftClose v-if="!collapsed" class="w-4 h-4" />
          <PanelLeftOpen v-else class="w-4 h-4" />
        </button>
      </div>

      <nav class="flex-1 overflow-y-auto py-2 space-y-0.5 px-2 text-xs">
        <NuxtLink
          v-for="item in visibleNav"
          :key="item.to"
          :to="item.to"
          active-class="bg-emerald-600/20 text-emerald-400 border-l-2 border-emerald-500"
          class="flex items-center gap-2.5 px-2.5 py-2 rounded hover:bg-slate-800/70 transition-colors"
        >
          <component :is="item.icon" class="w-4 h-4 shrink-0" />
          <span v-if="!collapsed" class="truncate">{{ item.label }}</span>
        </NuxtLink>
      </nav>

      <div class="p-2 border-t border-slate-800 text-[11px] text-slate-500 flex items-center justify-between">
        <span v-if="!collapsed">v1.0.0 · Single Node</span>
        <span v-else>v1</span>
      </div>
    </aside>

    <!-- Main Workspace -->
    <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
      <!-- Top Telemetry & Status Bar -->
      <header class="h-12 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 text-xs">
        <div class="flex items-center gap-3 overflow-x-auto">
          <span class="font-semibold text-slate-800">{{ telemetry?.hostname || 'localhost' }}</span>
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
            {{ telemetry?.os || 'Linux' }}
          </span>
          <span v-if="telemetry" class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
            Load: {{ telemetry.load_average.join(' / ') }}
          </span>
          <span v-if="telemetry" class="text-slate-500">
            Uptime: {{ Math.floor(telemetry.uptime_seconds / 3600) }}h
          </span>
        </div>

        <div class="flex items-center gap-3">
          <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
            {{ auth.user?.username || 'admin' }} ({{ auth.user?.role || 'Administrator' }})
          </span>
          <button @click="handleLogout" class="np-btn-secondary">
            <LogOut class="w-3.5 h-3.5" />
            <span>Logout</span>
          </button>
        </div>
      </header>

      <main class="flex-1 overflow-y-auto p-4">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Activity,
  Archive,
  Clock,
  Container,
  Cpu,
  Database,
  FileCode2,
  Flame,
  Globe,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Mail,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  Store,
  Terminal,
  Users,
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch } = useApi()
const collapsed = ref(false)
const telemetry = ref<any>(null)

const navItems = [
  { label: 'Dashboard', to: '/', icon: LayoutDashboard, perm: 'dashboard:read' },
  { label: 'Websites', to: '/websites', icon: Globe, perm: 'websites:read' },
  { label: 'Databases', to: '/databases', icon: Database, perm: 'databases:read' },
  { label: 'Mail', to: '/mail', icon: Mail, perm: 'mail:read' },
  { label: 'DNS', to: '/dns', icon: Activity, perm: 'dns:read' },
  { label: 'SSL / ACME', to: '/ssl', icon: KeyRound, perm: 'ssl:read' },
  { label: 'Files', to: '/files', icon: FileCode2, perm: 'files:read' },
  { label: 'FTP', to: '/ftp', icon: HardDrive, perm: 'ftp:read' },
  { label: 'Terminal', to: '/terminal', icon: Terminal, perm: 'terminal:execute' },
  { label: 'Backups', to: '/backups', icon: Archive, perm: 'backups:read' },
  { label: 'App Store', to: '/apps', icon: Store, perm: 'apps:read' },
  { label: 'Docker', to: '/docker', icon: Container, perm: 'docker:read' },
  { label: 'Cron Jobs', to: '/cron', icon: Clock, perm: 'cron:read' },
  { label: 'Processes', to: '/processes', icon: Cpu, perm: 'processes:read' },
  { label: 'Firewall', to: '/firewall', icon: Flame, perm: 'firewall:read' },
  { label: 'Packages', to: '/packages', icon: Package, perm: 'packages:read' },
  { label: 'Security & Audit', to: '/security', icon: ShieldCheck, perm: 'security:read' },
  { label: 'RBAC & Users', to: '/rbac', icon: Users, perm: 'rbac:read' },
  { label: 'Settings', to: '/settings', icon: Settings, perm: 'settings:read' },
]

const visibleNav = computed(() =>
  // Default-deny: with no loaded user/permissions show nothing instead of
  // falling back to "show every entry" (!auth.user used to bypass the filter).
  navItems.filter((item) => auth.user && auth.can(item.perm))
)

async function loadHeaderState() {
  if (!auth.isAuthenticated) {
    navigateTo('/login')
    return
  }
  try {
    if (!auth.user) {
      auth.setUser(await apiFetch('/auth/me'))
    }
    telemetry.value = await apiFetch('/system/telemetry')
  } catch {
    // Handled by apiFetch
  }
}

async function handleLogout() {
  try {
    // Clear the HttpOnly access_token cookie as well as the in-memory token,
    // otherwise the cookie would silently restore the session on the next
    // navigation.
    await apiFetch('/auth/logout', { method: 'POST' })
  } catch {
    // Local logout must still succeed if the server call fails.
  }
  auth.clearSession()
  navigateTo('/login')
}

onMounted(loadHeaderState)
</script>
