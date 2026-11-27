<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <!-- Left Navigation Sidebar -->
    <aside class="w-52 shrink-0 border-r border-slate-200 bg-slate-50/70 py-3 flex flex-col justify-between">
      <div>
        <div class="px-4 pb-3 mb-2 border-b border-slate-200">
          <div class="flex items-center gap-2 font-bold text-slate-900 text-sm">
            <ShieldCheck class="w-4 h-4 text-emerald-600" />
            <span>Host Firewall</span>
          </div>
          <p class="text-[10px] text-slate-500 mt-0.5 font-medium">UFW · Ports · Services · GeoIP · Fail2Ban</p>
        </div>

        <nav class="space-y-0.5">
          <button
            v-for="item in navSections"
            :key="item.key"
            @click="activeSection = item.key"
            :class="activeSection === item.key ? 'text-emerald-700 bg-emerald-50/80 border-r-2 border-emerald-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
            class="w-full flex items-center gap-2 text-left px-4 py-2.5 transition-colors"
          >
            <component :is="item.icon" class="w-3.5 h-3.5" />
            <span class="truncate">{{ item.label }}</span>
            <span v-if="item.key === 'rules' && rules.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-slate-200/80 text-slate-700 text-[10px] font-medium">{{ rules.length }}</span>
            <span v-else-if="item.key === 'ports' && listeningPorts.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-semibold">{{ listeningPorts.length }}</span>
            <span v-else-if="item.key === 'ip_block' && blockedIps.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-700 text-[10px] font-semibold">{{ blockedIps.length }}</span>
            <span v-else-if="item.key === 'countries' && countryBlocks.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold">{{ countryBlocks.length }}</span>
            <span v-else-if="item.key === 'fail2ban' && fail2ban?.banned_ips?.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-700 text-[10px] font-semibold">{{ fail2ban.banned_ips.length }}</span>
          </button>
        </nav>
      </div>

      <!-- Quick Server Info Widget -->
      <div class="mx-3 mt-4 space-y-2">
        <div class="rounded border border-slate-200 bg-white p-2.5 space-y-1.5 shadow-2xs">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-medium text-slate-500">Firewall Engine</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-semibold" :class="fwStatus.active ? 'text-emerald-600' : 'text-rose-600'">
              <span class="w-2 h-2 rounded-full" :class="fwStatus.active ? 'bg-emerald-500' : 'bg-rose-500'"></span>
              {{ fwStatus.active ? 'Active' : 'Disabled' }}
            </span>
          </div>
          <div class="text-[10px] text-slate-600 flex justify-between">
            <span>Incoming:</span>
            <span class="font-semibold uppercase text-slate-800">{{ fwStatus.default_incoming || 'deny' }}</span>
          </div>
          <div class="text-[10px] text-slate-600 flex justify-between">
            <span>Outgoing:</span>
            <span class="font-semibold uppercase text-slate-800">{{ fwStatus.default_outgoing || 'allow' }}</span>
          </div>
        </div>

        <button
          @click="toggleUfw(!fwStatus.active)"
          :disabled="busy === 'toggle_ufw'"
          :class="fwStatus.active ? 'text-rose-700 border-rose-200 hover:bg-rose-50' : 'text-emerald-700 border-emerald-200 hover:bg-emerald-50'"
          class="w-full flex items-center justify-center gap-1.5 rounded border bg-white py-1.5 px-2 text-[11px] font-medium transition-colors disabled:opacity-50"
        >
          <Power class="w-3 h-3" />
          <span>{{ fwStatus.active ? 'Disable Firewall' : 'Enable Firewall' }}</span>
        </button>
      </div>
    </aside>

    <!-- Main Content Area -->
    <div class="flex-1 p-5 flex flex-col min-w-0 overflow-y-auto">
      <!-- Top Action Bar -->
      <div class="flex flex-wrap items-start justify-between gap-3 pb-3 mb-4 border-b border-slate-200">
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-sm font-bold text-slate-900">{{ sectionTitle }}</h1>
            <span v-if="fwStatus.active" class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Filtering Active
            </span>
            <span v-else class="px-2 py-0.5 rounded bg-rose-50 text-rose-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> Firewall Inactive
            </span>
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">{{ sectionSubtitle }}</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button @click="reloadFirewall" :disabled="busy === 'reload'" class="np-btn-secondary" title="Reload UFW configuration rules">
            <RotateCw :class="{ 'animate-spin': busy === 'reload' }" class="w-3.5 h-3.5 text-slate-600" />
            <span>Reload Firewall</span>
          </button>
          <button @click="refreshAll" :disabled="loading" class="np-btn-secondary" title="Refresh all firewall data">
            <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>

          <!-- Contextual Action Buttons -->
          <button v-if="activeSection === 'rules'" @click="showAddRuleModal = true" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Port Rule</span>
          </button>
          <button v-else-if="activeSection === 'ip_block'" @click="showAddIpModal = true" class="np-btn-danger">
            <Ban class="w-3.5 h-3.5" />
            <span>Block IP / Subnet</span>
          </button>
          <button v-else-if="activeSection === 'countries'" @click="showAddCountryModal = true" class="np-btn-primary">
            <Globe class="w-3.5 h-3.5" />
            <span>Block Country</span>
          </button>
          <button v-else-if="activeSection === 'fail2ban'" @click="showBanIpModal = true" class="np-btn-danger">
            <Lock class="w-3.5 h-3.5" />
            <span>Ban IP Manually</span>
          </button>
        </div>
      </div>

      <!-- Alerts / Feedback -->
      <div v-if="errorMessage" class="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><AlertTriangle class="w-3.5 h-3.5 shrink-0" />{{ errorMessage }}</span>
        <button @click="errorMessage = ''" class="text-rose-500 hover:text-rose-700"><X class="w-3.5 h-3.5" /></button>
      </div>
      <div v-if="noticeMessage" class="mb-3 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><CheckCircle2 class="w-3.5 h-3.5 shrink-0" />{{ noticeMessage }}</span>
        <button @click="noticeMessage = ''" class="text-emerald-500 hover:text-emerald-700"><X class="w-3.5 h-3.5" /></button>
      </div>

      <!-- 1. OVERVIEW & HEALTH SECTION -->
      <div v-if="activeSection === 'overview'" class="space-y-4">
        <!-- Metric Overview Cards -->
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">UFW Engine</div>
            <div class="mt-1 text-lg font-bold" :class="fwStatus.active ? 'text-emerald-600' : 'text-rose-600'">
              {{ fwStatus.active ? 'Active & Running' : 'Disabled' }}
            </div>
            <div class="text-[10px] text-slate-500 mt-0.5">Logging: {{ fwStatus.logging || 'low' }}</div>
          </div>

          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs cursor-pointer hover:border-slate-300 transition-colors" @click="activeSection = 'ports'">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Listening Ports</div>
            <div class="mt-1 text-lg font-bold text-slate-900">{{ listeningPorts.length }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Host listening sockets</div>
          </div>

          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs cursor-pointer hover:border-slate-300 transition-colors" @click="activeSection = 'rules'">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Ingress Rules</div>
            <div class="mt-1 text-lg font-bold text-slate-900">{{ rules.length }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Configured port rules</div>
          </div>

          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs cursor-pointer hover:border-slate-300 transition-colors" @click="activeSection = 'ip_block'">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Blocked IPs / CIDR</div>
            <div class="mt-1 text-lg font-bold text-rose-600">{{ blockedIps.length }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Blacklisted addresses</div>
          </div>

          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs cursor-pointer hover:border-slate-300 transition-colors" @click="activeSection = 'countries'">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Country Blocks</div>
            <div class="mt-1 text-lg font-bold text-amber-600">{{ countryBlocks.length }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">GeoIP restricted regions</div>
          </div>
        </div>

        <!-- Master Policy & Quick Configuration -->
        <div class="grid gap-4 xl:grid-cols-2">
          <!-- Policy Settings Card -->
          <div class="rounded border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between border-b border-slate-200 pb-2">
              <span class="font-bold text-slate-900 flex items-center gap-1.5">
                <Sliders class="w-4 h-4 text-emerald-600" /> Default Traffic Policies
              </span>
              <span class="text-[10px] text-slate-500">System-wide default packet handling</span>
            </div>

            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <div>
                  <div class="font-semibold text-slate-800">Incoming Traffic</div>
                  <div class="text-[10px] text-slate-500">Packets destined for this server without an explicit allow rule</div>
                </div>
                <select
                  :value="fwStatus.default_incoming || 'deny'"
                  @change="updateDefaultPolicy('incoming', ($event.target as HTMLSelectElement).value)"
                  class="np-input w-28 font-semibold uppercase text-xs"
                >
                  <option value="deny">DENY</option>
                  <option value="reject">REJECT</option>
                  <option value="allow">ALLOW</option>
                </select>
              </div>

              <div class="flex items-center justify-between pt-2 border-t border-slate-100">
                <div>
                  <div class="font-semibold text-slate-800">Outgoing Traffic</div>
                  <div class="text-[10px] text-slate-500">Packets initiated by this host toward remote external networks</div>
                </div>
                <select
                  :value="fwStatus.default_outgoing || 'allow'"
                  @change="updateDefaultPolicy('outgoing', ($event.target as HTMLSelectElement).value)"
                  class="np-input w-28 font-semibold uppercase text-xs"
                >
                  <option value="allow">ALLOW</option>
                  <option value="deny">DENY</option>
                  <option value="reject">REJECT</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Quick Security Status Card -->
          <div class="rounded border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between border-b border-slate-200 pb-2">
              <span class="font-bold text-slate-900 flex items-center gap-1.5">
                <Shield class="w-4 h-4 text-emerald-600" /> Host Security Posture
              </span>
              <span class="text-[10px] font-semibold text-emerald-600 flex items-center gap-1">
                <CheckCircle2 class="w-3 h-3" /> Guarded
              </span>
            </div>

            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between py-1">
                <span class="text-slate-600">SSH Remote Shell Port (22)</span>
                <span class="font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-semibold">Protected (UFW + Fail2Ban)</span>
              </div>
              <div class="flex items-center justify-between py-1 border-t border-slate-100">
                <span class="text-slate-600">NexoPanel Console Port (8443)</span>
                <span class="font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-semibold">Active & Listening</span>
              </div>
              <div class="flex items-center justify-between py-1 border-t border-slate-100">
                <span class="text-slate-600">Database Direct Network Exposure</span>
                <span class="font-mono text-slate-600 bg-slate-100 px-2 py-0.5 rounded font-semibold">Local-Only (127.0.0.1)</span>
              </div>
              <div class="flex items-center justify-between py-1 border-t border-slate-100">
                <span class="text-slate-600">Fail2Ban SSH Protection</span>
                <span class="font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded font-semibold">Enabled ({{ fail2ban?.currently_banned || 0 }} banned)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Raw UFW Status Output Card -->
        <div class="rounded border border-slate-200 bg-white shadow-2xs">
          <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-slate-800 flex items-center justify-between">
            <span class="flex items-center gap-1.5"><Terminal class="w-3.5 h-3.5 text-slate-500" /> Kernel UFW Status Dump</span>
            <span class="text-[10px] text-slate-400 font-mono">/usr/sbin/ufw status verbose</span>
          </div>
          <pre class="p-3 bg-slate-900 text-slate-200 font-mono text-[11px] overflow-x-auto max-h-48 leading-relaxed">{{ fwStatus.raw || 'No raw output available' }}</pre>
        </div>
      </div>

      <!-- 2. SERVICES SECTION -->
      <div v-if="activeSection === 'services'" class="space-y-4">
        <!-- Service Category Filters -->
        <div class="flex items-center justify-between">
          <div class="flex flex-wrap gap-1">
            <button
              v-for="cat in ['All', 'Web', 'System', 'Database', 'Mail', 'Transfer', 'Networking']"
              :key="cat"
              @click="serviceFilter = cat"
              :class="serviceFilter === cat ? 'bg-slate-800 text-white font-medium' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
              class="px-2.5 py-1 rounded text-[11px] transition-colors"
            >
              {{ cat }}
            </button>
          </div>
          <span class="text-[10px] text-slate-500">{{ filteredServices.length }} services</span>
        </div>

        <!-- Service Cards Grid -->
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="svc in filteredServices"
            :key="svc.key"
            class="rounded border border-slate-200 bg-white p-3.5 shadow-2xs space-y-2.5 flex flex-col justify-between"
          >
            <div>
              <div class="flex items-start justify-between gap-2">
                <div>
                  <div class="font-bold text-slate-900 text-xs">{{ svc.name }}</div>
                  <div class="text-[10px] text-slate-500 mt-0.5">{{ svc.description }}</div>
                </div>
                <span class="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase bg-slate-100 text-slate-600 shrink-0">
                  {{ svc.category }}
                </span>
              </div>

              <div class="mt-2 flex flex-wrap gap-1">
                <span v-for="p in svc.ports" :key="p" class="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">
                  Port {{ p }} ({{ svc.protocol }})
                </span>
              </div>
            </div>

            <div class="pt-2 border-t border-slate-100 flex items-center justify-between">
              <span class="text-[10px] font-semibold flex items-center gap-1.5" :class="svc.enabled ? 'text-emerald-700' : 'text-slate-500'">
                <span class="w-2 h-2 rounded-full" :class="svc.enabled ? 'bg-emerald-500' : 'bg-slate-300'"></span>
                {{ svc.enabled ? 'Firewall Open' : 'Blocked' }}
              </span>

              <button
                @click="toggleService(svc.key, !svc.enabled)"
                :disabled="busy === `svc-${svc.key}`"
                :class="svc.enabled ? 'text-rose-700 border-rose-200 hover:bg-rose-50' : 'text-emerald-700 border-emerald-200 hover:bg-emerald-50'"
                class="px-2.5 py-1 rounded border text-[11px] font-semibold transition-colors disabled:opacity-50"
              >
                <span v-if="busy === `svc-${svc.key}`">Updating...</span>
                <span v-else>{{ svc.enabled ? 'Close Port' : 'Allow Traffic' }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 3. HOST LISTENING PORTS SECTION -->
      <div v-if="activeSection === 'ports'" class="space-y-4">
        <!-- Search and Live Info -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="relative w-64">
            <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input v-model="portSearch" placeholder="Search port, process or IP..." class="np-input pl-8" />
          </div>
          <div class="text-[11px] text-slate-500 flex items-center gap-2">
            <span class="inline-flex items-center gap-1 text-emerald-600 font-medium">
              <Radio class="w-3.5 h-3.5" /> Live Host Sockets (ss -tulpn)
            </span>
            <span>·</span>
            <span>Total: {{ filteredListeningPorts.length }}</span>
          </div>
        </div>

        <div class="np-card overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Protocol</th>
                <th>Local Address</th>
                <th>Port</th>
                <th>Process / Daemon</th>
                <th>PID</th>
                <th>State</th>
                <th>Firewall Status</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, idx) in filteredListeningPorts" :key="idx" class="hover:bg-slate-50/70">
                <td><span class="font-mono font-bold uppercase text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700">{{ p.protocol }}</span></td>
                <td class="font-mono font-medium">{{ p.local_address || '*' }}</td>
                <td class="font-mono font-bold text-slate-900">{{ p.port }}</td>
                <td class="font-semibold text-slate-800">{{ p.process }}</td>
                <td class="font-mono text-slate-500">{{ p.pid }}</td>
                <td><span class="text-[10px] uppercase font-mono text-slate-500">{{ p.state }}</span></td>
                <td>
                  <span v-if="p.firewall_status === 'allowed'" class="bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded font-bold uppercase text-[10px]">Allowed</span>
                  <span v-else-if="p.firewall_status === 'blocked'" class="bg-rose-50 text-rose-700 px-2 py-0.5 rounded font-bold uppercase text-[10px]">Blocked</span>
                  <span v-else-if="p.firewall_status === 'loopback_only'" class="bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-medium uppercase text-[10px]">Loopback Only</span>
                  <span v-else class="bg-amber-50 text-amber-700 px-2 py-0.5 rounded font-medium uppercase text-[10px]">Default Policy</span>
                </td>
                <td class="text-right">
                  <div class="flex items-center justify-end gap-1.5">
                    <button
                      v-if="p.firewall_status !== 'allowed'"
                      @click="quickAllowPort(p.port, p.protocol, p.process)"
                      class="text-emerald-600 hover:text-emerald-800 hover:underline font-semibold"
                    >
                      Allow
                    </button>
                    <button
                      v-if="p.firewall_status !== 'blocked'"
                      @click="quickBlockPort(p.port, p.protocol, p.process)"
                      class="text-rose-600 hover:text-rose-800 hover:underline font-semibold"
                    >
                      Block
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredListeningPorts.length">
                <td colspan="8" class="text-center py-6 text-slate-400">No active listening sockets matching your search.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 4. INGRESS RULES SECTION -->
      <div v-if="activeSection === 'rules'" class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="relative w-64">
            <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input v-model="rulesSearch" placeholder="Search port, IP or comment..." class="np-input pl-8" />
          </div>
          <div class="flex items-center gap-1.5">
            <button
              v-for="f in ['all', 'allow', 'deny']"
              :key="f"
              @click="rulesActionFilter = f"
              :class="rulesActionFilter === f ? 'bg-slate-800 text-white font-medium' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
              class="px-2.5 py-1 rounded text-[11px] uppercase transition-colors"
            >
              {{ f }}
            </button>
          </div>
        </div>

        <div class="np-card overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Port / Range</th>
                <th>Protocol</th>
                <th>Source IP / Subnet</th>
                <th>Description / Comment</th>
                <th>Created</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in filteredRules" :key="r.id" class="hover:bg-slate-50/70">
                <td>
                  <span
                    :class="r.action === 'allow' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'"
                    class="px-2 py-0.5 rounded uppercase text-[10px] font-bold"
                  >
                    {{ r.action }}
                  </span>
                </td>
                <td class="font-mono font-bold text-slate-900">{{ r.port }}</td>
                <td class="uppercase font-mono text-slate-600">{{ r.protocol }}</td>
                <td class="font-mono text-slate-700">{{ r.source_ip }}</td>
                <td class="text-slate-600">{{ r.comment || '—' }}</td>
                <td class="text-slate-400 text-[10px]">{{ formatDate(r.created_at) }}</td>
                <td class="text-right">
                  <button @click="deleteRule(r.id)" class="text-rose-600 hover:text-rose-800 hover:underline">
                    Delete
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredRules.length">
                <td colspan="7" class="text-center py-6 text-slate-400">No firewall rules found. Click "+ Add Port Rule" to create one.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 5. IP ACCESS CONTROL SECTION -->
      <div v-if="activeSection === 'ip_block'" class="space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-slate-600">
            Block malicious scanners, botnets, and abusive client IPs or allow trusted subnets directly in the host firewall.
          </p>
          <button @click="showAddIpModal = true" class="np-btn-danger">
            <Ban class="w-3.5 h-3.5" />
            <span>Block IP or Subnet</span>
          </button>
        </div>

        <div class="np-card overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Action</th>
                <th>IP / CIDR Network</th>
                <th>Target Port</th>
                <th>Protocol</th>
                <th>Reason / Comment</th>
                <th>Added Date</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in ipRules" :key="r.id" class="hover:bg-slate-50/70">
                <td>
                  <span
                    :class="r.action === 'deny' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'"
                    class="px-2 py-0.5 rounded uppercase text-[10px] font-bold"
                  >
                    {{ r.action === 'deny' ? 'BLOCKED' : 'ALLOWED' }}
                  </span>
                </td>
                <td class="font-mono font-bold text-slate-900">{{ r.source_ip }}</td>
                <td class="font-mono text-slate-600">{{ r.port }}</td>
                <td class="uppercase font-mono text-slate-600">{{ r.protocol }}</td>
                <td class="text-slate-600">{{ r.comment || '—' }}</td>
                <td class="text-slate-400 text-[10px]">{{ formatDate(r.created_at) }}</td>
                <td class="text-right">
                  <button @click="deleteRule(r.id)" class="text-rose-600 hover:text-rose-800 hover:underline">
                    Unblock
                  </button>
                </td>
              </tr>
              <tr v-if="!ipRules.length">
                <td colspan="7" class="text-center py-6 text-slate-400">No IP or subnet access rules configured yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 6. COUNTRY BLOCKING SECTION -->
      <div v-if="activeSection === 'countries'" class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-xs font-bold text-slate-900">Geographic Access Restrictions</h2>
            <p class="text-slate-500 mt-0.5">Restrict entire nations by ISO country code to prevent cross-border malicious traffic.</p>
          </div>
          <button @click="showAddCountryModal = true" class="np-btn-primary">
            <Globe class="w-3.5 h-3.5" />
            <span>Block Country</span>
          </button>
        </div>

        <!-- Quick Popular Country Toggles -->
        <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs space-y-2">
          <div class="font-semibold text-slate-800 text-[11px]">Quick Action - Select Frequently Blocked Regions:</div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="c in quickCountries"
              :key="c.code"
              @click="toggleQuickCountry(c)"
              :class="isCountryBlocked(c.code) ? 'bg-rose-100 text-rose-800 border-rose-300' : 'bg-slate-50 text-slate-700 hover:bg-slate-100 border-slate-200'"
              class="px-2.5 py-1 rounded border text-xs flex items-center gap-1.5 transition-colors"
            >
              <span>{{ c.flag }}</span>
              <span class="font-semibold">{{ c.name }}</span>
              <span class="text-[10px] uppercase font-mono text-slate-400">({{ c.code }})</span>
              <span v-if="isCountryBlocked(c.code)" class="text-[10px] font-bold text-rose-700 ml-1">✕</span>
            </button>
          </div>
        </div>

        <!-- Active Country Blocks Table -->
        <div class="np-card overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Region</th>
                <th>ISO Code</th>
                <th>Country Name</th>
                <th>Action</th>
                <th>Date Blocked</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in countryBlocks" :key="b.id" class="hover:bg-slate-50/70">
                <td class="text-base">{{ getCountryFlag(b.country_code) }}</td>
                <td class="font-mono font-bold text-slate-900">{{ b.country_code }}</td>
                <td class="font-semibold text-slate-800">{{ b.country_name }}</td>
                <td>
                  <span class="bg-rose-50 text-rose-700 px-2 py-0.5 rounded uppercase font-bold text-[10px]">
                    {{ b.action }}
                  </span>
                </td>
                <td class="text-slate-400 text-[10px]">{{ formatDate(b.created_at) }}</td>
                <td class="text-right">
                  <button @click="deleteCountryBlock(b.id)" class="text-rose-600 hover:text-rose-800 hover:underline">
                    Remove Block
                  </button>
                </td>
              </tr>
              <tr v-if="!countryBlocks.length">
                <td colspan="6" class="text-center py-6 text-slate-400">No countries blocked. All global traffic is accepted by default.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 7. FAIL2BAN INTRUSION DEFENSE SECTION -->
      <div v-if="activeSection === 'fail2ban'" class="space-y-4">
        <!-- Fail2Ban Metrics -->
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Currently Banned</div>
            <div class="mt-1 text-xl font-bold text-rose-600">{{ fail2ban?.currently_banned || 0 }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Active blacklisted IPs</div>
          </div>
          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Total Banned</div>
            <div class="mt-1 text-xl font-bold text-slate-800">{{ fail2ban?.total_banned || 0 }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Historical intrusion blocks</div>
          </div>
          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Currently Failed</div>
            <div class="mt-1 text-xl font-bold text-amber-600">{{ fail2ban?.currently_failed || 0 }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Active authentication failures</div>
          </div>
          <div class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">Monitored Jail</div>
            <div class="mt-1 text-base font-bold text-slate-800 font-mono">{{ fail2ban?.jail || 'sshd' }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">Service intrusion guard</div>
          </div>
        </div>

        <!-- Banned IPs List with 1-Click Unban -->
        <div class="np-card overflow-hidden">
          <div class="px-4 py-2.5 border-b border-slate-200 font-semibold text-slate-800 flex items-center justify-between">
            <div class="flex items-center gap-1.5">
              <Lock class="w-3.5 h-3.5 text-rose-600" />
              <span>Currently Banned Remote IP Addresses (Jail: {{ fail2ban?.jail || 'sshd' }})</span>
            </div>
            <button @click="showBanIpModal = true" class="np-btn-secondary text-[11px]">
              + Ban IP Manually
            </button>
          </div>

          <table class="np-table">
            <thead>
              <tr>
                <th>IP Address</th>
                <th>Target Jail</th>
                <th>Status</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ip in (fail2ban?.banned_ips || [])" :key="ip" class="hover:bg-slate-50/70">
                <td class="font-mono font-bold text-slate-900">{{ ip }}</td>
                <td class="font-mono text-slate-600">{{ fail2ban?.jail || 'sshd' }}</td>
                <td><span class="bg-rose-50 text-rose-700 px-2 py-0.5 rounded font-bold uppercase text-[10px]">Active Ban</span></td>
                <td class="text-right">
                  <button @click="unbanIp(ip)" :disabled="busy === `unban-${ip}`" class="text-rose-600 hover:text-rose-800 hover:underline font-semibold disabled:opacity-50">
                    {{ busy === `unban-${ip}` ? 'Unbanning...' : 'Unban IP' }}
                  </button>
                </td>
              </tr>
              <tr v-if="!(fail2ban?.banned_ips || []).length">
                <td colspan="4" class="text-center py-6 text-slate-400">No IP addresses currently banned in this jail.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Raw Fail2Ban Output -->
        <div class="np-card overflow-hidden">
          <div class="px-4 py-2 border-b border-slate-200 font-semibold text-slate-800 text-[11px]">Fail2Ban Client Status</div>
          <pre class="bg-slate-900 text-slate-200 p-3 rounded-b text-[11px] font-mono overflow-x-auto">{{ fail2ban?.raw || 'Fail2Ban service status unavailable' }}</pre>
        </div>
      </div>

      <!-- 8. LIVE UFW LOGS SECTION -->
      <div v-if="activeSection === 'logs'" class="space-y-4">
        <!-- Log Filter Controls -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <div class="relative w-64">
              <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input v-model="logSearch" placeholder="Search IP or port in logs..." class="np-input pl-8" />
            </div>
            <select v-model="logActionFilter" class="np-input w-28">
              <option value="ALL">All Actions</option>
              <option value="BLOCK">Blocked Only</option>
              <option value="ALLOW">Allowed Only</option>
            </select>
          </div>

          <div class="flex items-center gap-2">
            <select v-model="logLines" @change="loadLogs" class="np-input w-24">
              <option :value="25">25 lines</option>
              <option :value="50">50 lines</option>
              <option :value="100">100 lines</option>
              <option :value="200">200 lines</option>
            </select>
            <button @click="loadLogs" :disabled="logsLoading" class="np-btn-secondary">
              <RefreshCw :class="{ 'animate-spin': logsLoading }" class="w-3.5 h-3.5" />
              <span>Refresh Logs</span>
            </button>
          </div>
        </div>

        <!-- Logs Table -->
        <div class="np-card overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Source IP</th>
                <th>Target Port</th>
                <th>Protocol</th>
                <th>Raw Event Log</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(l, idx) in filteredLogs" :key="idx" class="hover:bg-slate-50/70">
                <td class="font-mono text-slate-500 whitespace-nowrap">{{ l.timestamp }}</td>
                <td>
                  <span
                    :class="l.action === 'BLOCK' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'"
                    class="px-1.5 py-0.5 rounded font-bold uppercase text-[10px]"
                  >
                    {{ l.action }}
                  </span>
                </td>
                <td class="font-mono font-bold text-slate-800">{{ l.src_ip }}</td>
                <td class="font-mono text-slate-900">{{ l.dst_port }}</td>
                <td class="font-mono uppercase text-slate-600">{{ l.proto }}</td>
                <td class="font-mono text-[10px] text-slate-500 truncate max-w-xs" :title="l.raw">{{ l.raw }}</td>
              </tr>
              <tr v-if="!filteredLogs.length">
                <td colspan="6" class="text-center py-6 text-slate-400">No log entries found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- MODAL: ADD PORT RULE -->
    <div v-if="showAddRuleModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-4 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Add Firewall Ingress Rule</h3>
          <button @click="showAddRuleModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Port or Port Range</label>
            <input v-model="ruleForm.port" placeholder="e.g. 80, 443, or 8000:8100" class="np-input" />
            <span class="text-[10px] text-slate-400">Single port (80) or range (8000:8100). Use 'any' for all ports.</span>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Protocol</label>
              <select v-model="ruleForm.protocol" class="np-input">
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="any">Any (TCP + UDP)</option>
              </select>
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Action</label>
              <select v-model="ruleForm.action" class="np-input font-semibold">
                <option value="allow">ALLOW (Accept)</option>
                <option value="deny">DENY (Drop)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Source IP or Subnet (Optional)</label>
            <input v-model="ruleForm.source_ip" placeholder="any or 198.51.100.23 or 10.0.0.0/24" class="np-input" />
            <span class="text-[10px] text-slate-400">Leave 'any' for worldwide access, or restrict to a specific IP/CIDR.</span>
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Comment / Label</label>
            <input v-model="ruleForm.comment" placeholder="e.g. HTTPS Web Traffic" class="np-input" />
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showAddRuleModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createRule" :disabled="busy === 'create_rule'" class="np-btn-primary">
            {{ busy === 'create_rule' ? 'Adding...' : 'Create Rule' }}
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: BLOCK IP / CIDR -->
    <div v-if="showAddIpModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-4 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2">
          <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5 text-rose-700">
            <Ban class="w-4 h-4" /> Block Malicious IP or Subnet
          </h3>
          <button @click="showAddIpModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Target IP Address or CIDR Subnet</label>
            <input v-model="ipForm.source_ip" placeholder="e.g. 198.51.100.55 or 192.0.2.0/24" class="np-input font-mono" />
            <span class="text-[10px] text-slate-400">Blocks incoming traffic from this specific remote host or CIDR block.</span>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Target Port</label>
              <input v-model="ipForm.port" placeholder="any or 22" class="np-input font-mono" />
              <span class="text-[10px] text-slate-400">'any' blocks all traffic</span>
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Action</label>
              <select v-model="ipForm.action" class="np-input font-semibold text-rose-700">
                <option value="deny">DENY (Block)</option>
                <option value="allow">ALLOW (Whitelist)</option>
              </select>
            </div>
          </div>

          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Reason / Notes</label>
            <input v-model="ipForm.comment" placeholder="e.g. WordPress login brute force bot" class="np-input" />
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showAddIpModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createIpRule" :disabled="busy === 'create_ip'" class="np-btn-danger">
            {{ busy === 'create_ip' ? 'Saving...' : 'Apply Block Rule' }}
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: BLOCK COUNTRY -->
    <div v-if="showAddCountryModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-4 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2">
          <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">
            <Globe class="w-4 h-4 text-emerald-600" /> Block Country Traffic
          </h3>
          <button @click="showAddCountryModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Select Country</label>
            <select v-model="selectedCountryCode" @change="onCountrySelected" class="np-input text-xs">
              <option value="" disabled>Choose a country...</option>
              <option v-for="c in countryCatalog" :key="c.code" :value="c.code">
                {{ c.flag }} {{ c.name }} ({{ c.code }})
              </option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">ISO Code</label>
              <input v-model="countryForm.country_code" readonly class="np-input font-mono bg-slate-100" />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Action</label>
              <input value="DENY" readonly class="np-input font-semibold text-rose-700 bg-slate-100" />
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showAddCountryModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createCountryBlock" :disabled="!countryForm.country_code || busy === 'create_country'" class="np-btn-primary">
            {{ busy === 'create_country' ? 'Blocking...' : 'Block Country' }}
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: BAN IP IN FAIL2BAN -->
    <div v-if="showBanIpModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-4 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2">
          <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5 text-rose-700">
            <Lock class="w-4 h-4" /> Ban IP in Fail2Ban
          </h3>
          <button @click="showBanIpModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="space-y-3">
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">IP Address to Ban</label>
            <input v-model="banIpForm.ip" placeholder="e.g. 198.51.100.89" class="np-input font-mono" />
          </div>
          <div>
            <label class="block text-[11px] font-semibold text-slate-700 mb-1">Target Jail</label>
            <select v-model="banIpForm.jail" class="np-input font-mono">
              <option v-for="j in (fail2ban?.jails || ['sshd'])" :key="j" :value="j">{{ j }}</option>
            </select>
          </div>
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showBanIpModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="banIpManually" :disabled="!banIpForm.ip || busy === 'ban_ip'" class="np-btn-danger">
            {{ busy === 'ban_ip' ? 'Banning...' : 'Confirm Ban' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Globe,
  Lock,
  Plus,
  Power,
  Radio,
  RefreshCw,
  RotateCw,
  Search,
  Shield,
  ShieldCheck,
  Sliders,
  Terminal,
  X,
} from 'lucide-vue-next'

type Section = 'overview' | 'services' | 'ports' | 'rules' | 'ip_block' | 'countries' | 'fail2ban' | 'logs'

const { apiFetch } = useApi()

const activeSection = ref<Section>('overview')
const loading = ref(false)
const busy = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

const fwStatus = ref<any>({ active: false, default_incoming: 'deny', default_outgoing: 'allow' })
const rules = ref<any[]>([])
const listeningPorts = ref<any[]>([])
const services = ref<any[]>([])
const countryBlocks = ref<any[]>([])
const countryCatalog = ref<any[]>([])
const fail2ban = ref<any>({ jail: 'sshd', currently_banned: 0, total_banned: 0, banned_ips: [] })
const logs = ref<any[]>([])
const logsLoading = ref(false)

// Modals
const showAddRuleModal = ref(false)
const showAddIpModal = ref(false)
const showAddCountryModal = ref(false)
const showBanIpModal = ref(false)

// Search & filters
const portSearch = ref('')
const rulesSearch = ref('')
const rulesActionFilter = ref('all')
const serviceFilter = ref('All')
const logSearch = ref('')
const logActionFilter = ref('ALL')
const logLines = ref(50)

// Forms
const ruleForm = reactive({
  port: '443',
  protocol: 'tcp',
  action: 'allow',
  source_ip: 'any',
  comment: '',
})

const ipForm = reactive({
  port: 'any',
  protocol: 'any',
  action: 'deny',
  source_ip: '',
  comment: '',
})

const selectedCountryCode = ref('')
const countryForm = reactive({
  country_code: '',
  country_name: '',
  action: 'deny',
})

const banIpForm = reactive({
  jail: 'sshd',
  ip: '',
})

const navSections = [
  { key: 'overview' as Section, label: 'Overview & Health', icon: ShieldCheck },
  { key: 'services' as Section, label: 'Common Services', icon: Sliders },
  { key: 'ports' as Section, label: 'Listening Ports', icon: Radio },
  { key: 'rules' as Section, label: 'Ingress Rules', icon: Shield },
  { key: 'ip_block' as Section, label: 'IP Access Control', icon: Ban },
  { key: 'countries' as Section, label: 'Country Blocking', icon: Globe },
  { key: 'fail2ban' as Section, label: 'Fail2Ban Defense', icon: Lock },
  { key: 'logs' as Section, label: 'Live UFW Logs', icon: Terminal },
]

const quickCountries = [
  { code: 'CN', name: 'China', flag: '🇨🇳' },
  { code: 'RU', name: 'Russia', flag: '🇷🇺' },
  { code: 'IR', name: 'Iran', flag: '🇮🇷' },
  { code: 'KP', name: 'North Korea', flag: '🇰🇵' },
  { code: 'US', name: 'United States', flag: '🇺🇸' },
  { code: 'DE', name: 'Germany', flag: '🇩🇪' },
]

const sectionTitle = computed(() => {
  switch (activeSection.value) {
    case 'overview':
      return 'Firewall Overview & Host Security'
    case 'services':
      return 'Common Server Services'
    case 'ports':
      return 'Host OS Listening Sockets'
    case 'rules':
      return 'Port Ingress Filtering Rules'
    case 'ip_block':
      return 'IP & Subnet Access Blacklist'
    case 'countries':
      return 'Country & GeoIP Protection'
    case 'fail2ban':
      return 'Fail2Ban Intrusion Prevention'
    case 'logs':
      return 'Real-Time Firewall Logs'
    default:
      return 'Firewall'
  }
})

const sectionSubtitle = computed(() => {
  switch (activeSection.value) {
    case 'overview':
      return 'Master firewall status, traffic policies, and system-wide security overview.'
    case 'services':
      return '1-click enable or disable network ingress for standard server daemons.'
    case 'ports':
      return 'Real-time open network sockets detected on the host operating system.'
    case 'rules':
      return 'Fine-grained port and protocol firewall rules with source IP restrictions.'
    case 'ip_block':
      return 'Deny or allow specific client IP addresses or entire CIDR subnets.'
    case 'countries':
      return 'Block or restrict inbound traffic originating from specific nations.'
    case 'fail2ban':
      return 'Monitored intrusion jails and real-time banned brute-force attackers.'
    case 'logs':
      return 'Live tail of kernel UFW packet drops and connection attempts.'
    default:
      return ''
  }
})

const blockedIps = computed(() => {
  return rules.value.filter((r) => r.action === 'deny' || r.source_ip !== 'any')
})

const ipRules = computed(() => {
  return rules.value.filter((r) => r.port === 'any' || r.source_ip !== 'any' || r.action === 'deny')
})

const filteredRules = computed(() => {
  return rules.value.filter((r) => {
    if (rulesActionFilter.value !== 'all' && r.action !== rulesActionFilter.value) return false
    if (!rulesSearch.value) return true
    const q = rulesSearch.value.toLowerCase()
    return (
      r.port.toLowerCase().includes(q) ||
      r.source_ip.toLowerCase().includes(q) ||
      (r.comment && r.comment.toLowerCase().includes(q))
    )
  })
})

const filteredListeningPorts = computed(() => {
  if (!portSearch.value) return listeningPorts.value
  const q = portSearch.value.toLowerCase()
  return listeningPorts.value.filter((p) => {
    return (
      p.port.includes(q) ||
      p.process.toLowerCase().includes(q) ||
      p.local_address.includes(q) ||
      p.protocol.toLowerCase().includes(q)
    )
  })
})

const filteredServices = computed(() => {
  if (serviceFilter.value === 'All') return services.value
  return services.value.filter((s) => s.category.toLowerCase() === serviceFilter.value.toLowerCase())
})

const filteredLogs = computed(() => {
  return logs.value.filter((l) => {
    if (logActionFilter.value !== 'ALL' && l.action !== logActionFilter.value) return false
    if (!logSearch.value) return true
    const q = logSearch.value.toLowerCase()
    return (
      l.src_ip.toLowerCase().includes(q) ||
      l.dst_port.toLowerCase().includes(q) ||
      l.raw.toLowerCase().includes(q)
    )
  })
})

function notify(msg: string) {
  noticeMessage.value = msg
  errorMessage.value = ''
  setTimeout(() => {
    if (noticeMessage.value === msg) noticeMessage.value = ''
  }, 4000)
}

function fail(e: any) {
  errorMessage.value = e?.data?.detail || e?.message || 'Operation failed'
  noticeMessage.value = ''
}

function formatDate(iso: string) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function getCountryFlag(code: string) {
  const match = countryCatalog.value.find((c) => c.code === code)
  return match?.flag || '🌐'
}

function isCountryBlocked(code: string) {
  return countryBlocks.value.some((b) => b.country_code === code)
}

function onCountrySelected() {
  const c = countryCatalog.value.find((x) => x.code === selectedCountryCode.value)
  if (c) {
    countryForm.country_code = c.code
    countryForm.country_name = c.name
  }
}

async function load() {
  loading.value = true
  try {
    const [statusData, rulesData, portsData, servicesData, countriesData, catalogData, f2bData] = await Promise.all([
      apiFetch<any>('/firewall/status'),
      apiFetch<any[]>('/firewall/rules'),
      apiFetch<any[]>('/firewall/listening-ports'),
      apiFetch<any[]>('/firewall/services'),
      apiFetch<any[]>('/firewall/countries'),
      apiFetch<any[]>('/firewall/countries/catalog'),
      apiFetch<any>('/firewall/fail2ban?jail=sshd'),
    ])
    fwStatus.value = statusData || {}
    rules.value = rulesData || []
    listeningPorts.value = portsData || []
    services.value = servicesData || []
    countryBlocks.value = countriesData || []
    countryCatalog.value = catalogData || []
    fail2ban.value = f2bData || {}
  } catch (e: any) {
    fail(e)
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await load()
  if (activeSection.value === 'logs') {
    await loadLogs()
  }
  notify('Firewall state refreshed')
}

async function toggleUfw(enable: boolean) {
  const actionText = enable ? 'enable' : 'disable'
  if (!window.confirm(`Are you sure you want to ${actionText} the host UFW firewall?`)) return
  busy.value = 'toggle_ufw'
  try {
    await apiFetch(`/firewall/toggle?enable=${enable}`, { method: 'POST' })
    notify(`Firewall ${enable ? 'enabled' : 'disabled'} successfully`)
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function reloadFirewall() {
  busy.value = 'reload'
  try {
    await apiFetch('/firewall/reload', { method: 'POST' })
    notify('Firewall configuration rules reloaded')
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function updateDefaultPolicy(direction: string, policy: string) {
  try {
    await apiFetch('/firewall/default-policy', {
      method: 'POST',
      body: { direction, policy },
    })
    notify(`Default ${direction} policy set to ${policy.toUpperCase()}`)
    await load()
  } catch (e: any) {
    fail(e)
  }
}

async function toggleService(serviceKey: string, enable: boolean) {
  busy.value = `svc-${serviceKey}`
  try {
    await apiFetch('/firewall/services/toggle', {
      method: 'POST',
      body: { service_key: serviceKey, enable, source_ip: 'any' },
    })
    notify(`Service port ${enable ? 'opened' : 'closed'} successfully`)
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function quickAllowPort(port: string, protocol: string, processName: string) {
  try {
    await apiFetch('/firewall/rules', {
      method: 'POST',
      body: {
        port,
        protocol: protocol || 'tcp',
        action: 'allow',
        source_ip: 'any',
        comment: processName ? `Allow ${processName}` : `Port ${port}`,
      },
    })
    notify(`Port ${port}/${protocol} opened in firewall`)
    await load()
  } catch (e: any) {
    fail(e)
  }
}

async function quickBlockPort(port: string, protocol: string, processName: string) {
  try {
    await apiFetch('/firewall/rules', {
      method: 'POST',
      body: {
        port,
        protocol: protocol || 'tcp',
        action: 'deny',
        source_ip: 'any',
        comment: processName ? `Block ${processName}` : `Block port ${port}`,
      },
    })
    notify(`Port ${port}/${protocol} blocked in firewall`)
    await load()
  } catch (e: any) {
    fail(e)
  }
}

async function createRule() {
  busy.value = 'create_rule'
  try {
    await apiFetch('/firewall/rules', { method: 'POST', body: ruleForm })
    showAddRuleModal.value = false
    notify(`Rule for port ${ruleForm.port} created`)
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function createIpRule() {
  if (!ipForm.source_ip) return
  busy.value = 'create_ip'
  try {
    await apiFetch('/firewall/rules', { method: 'POST', body: ipForm })
    showAddIpModal.value = false
    notify(`Rule for ${ipForm.source_ip} applied`)
    ipForm.source_ip = ''
    ipForm.comment = ''
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function deleteRule(id: number) {
  if (!window.confirm('Delete this firewall rule?')) return
  try {
    await apiFetch(`/firewall/rules/${id}`, { method: 'DELETE' })
    notify('Firewall rule deleted')
    await load()
  } catch (e: any) {
    fail(e)
  }
}

async function createCountryBlock() {
  busy.value = 'create_country'
  try {
    await apiFetch('/firewall/countries', { method: 'POST', body: countryForm })
    showAddCountryModal.value = false
    notify(`Country ${countryForm.country_name} (${countryForm.country_code}) blocked`)
    selectedCountryCode.value = ''
    countryForm.country_code = ''
    countryForm.country_name = ''
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function toggleQuickCountry(c: { code: string; name: string }) {
  const existing = countryBlocks.value.find((b) => b.country_code === c.code)
  if (existing) {
    await deleteCountryBlock(existing.id)
  } else {
    try {
      await apiFetch('/firewall/countries', {
        method: 'POST',
        body: { country_code: c.code, country_name: c.name, action: 'deny' },
      })
      notify(`Country ${c.name} blocked`)
      await load()
    } catch (e: any) {
      fail(e)
    }
  }
}

async function deleteCountryBlock(id: number) {
  try {
    await apiFetch(`/firewall/countries/${id}`, { method: 'DELETE' })
    notify('Country block removed')
    await load()
  } catch (e: any) {
    fail(e)
  }
}

async function unbanIp(ip: string) {
  busy.value = `unban-${ip}`
  try {
    await apiFetch('/firewall/fail2ban/unban', {
      method: 'POST',
      body: { jail: fail2ban.value?.jail || 'sshd', ip },
    })
    notify(`IP ${ip} unbanned successfully`)
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function banIpManually() {
  if (!banIpForm.ip) return
  busy.value = 'ban_ip'
  try {
    await apiFetch('/firewall/fail2ban/ban', {
      method: 'POST',
      body: banIpForm,
    })
    showBanIpModal.value = false
    notify(`IP ${banIpForm.ip} banned in ${banIpForm.jail}`)
    banIpForm.ip = ''
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res = await apiFetch<any[]>(`/firewall/logs?lines=${logLines.value}`)
    logs.value = res || []
  } catch (e: any) {
    fail(e)
  } finally {
    logsLoading.value = false
  }
}

watch(activeSection, (sec) => {
  if (sec === 'logs' && !logs.value.length) {
    loadLogs()
  }
})

onMounted(load)
</script>
