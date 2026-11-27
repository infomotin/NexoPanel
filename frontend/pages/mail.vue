<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <!-- Left Navigation Sidebar -->
    <aside class="w-48 shrink-0 border-r border-slate-200 bg-slate-50/70 py-3 flex flex-col justify-between">
      <div>
        <div class="px-4 pb-3 mb-2 border-b border-slate-200">
          <div class="flex items-center gap-2 font-bold text-slate-900 text-sm">
            <Mail class="w-4 h-4 text-emerald-600" />
            <span>Mail Server</span>
          </div>
          <p class="text-[10px] text-slate-500 mt-0.5 font-medium">SMTP · IMAP · Inboxes · Webmail</p>
        </div>

        <nav class="space-y-0.5">
          <button
            v-for="item in sections"
            :key="item.key"
            @click="setSection(item.key)"
            :class="activeSection === item.key ? 'text-emerald-700 bg-emerald-50/80 border-r-2 border-emerald-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
            class="w-full flex items-center gap-2 text-left px-4 py-2.5 transition-colors"
          >
            <component :is="item.icon" class="w-3.5 h-3.5" />
            <span class="truncate">{{ item.label }}</span>
            <span v-if="item.key === 'queue' && queue.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold">{{ queue.length }}</span>
            <span v-else-if="item.key === 'mailboxes' && mailboxes.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-slate-200/80 text-slate-700 text-[10px] font-medium">{{ mailboxes.length }}</span>
          </button>
        </nav>
      </div>

      <!-- Quick Server Info Widget -->
      <div class="mx-3 mt-4 space-y-2">
        <div class="rounded border border-slate-200 bg-white p-2.5 space-y-1 shadow-2xs">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-medium text-slate-500">Stack Status</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-semibold" :class="stackHealthy ? 'text-emerald-600' : 'text-amber-600'">
              <span class="w-2 h-2 rounded-full" :class="stackHealthy ? 'bg-emerald-500' : 'bg-amber-500'"></span>
              {{ stackHealthy ? 'Healthy' : 'Check' }}
            </span>
          </div>
          <div class="font-mono text-[10px] text-slate-700 truncate" :title="mailHost">{{ mailHost }}</div>
          <div class="font-mono text-[10px] text-slate-500">{{ status?.public_ip || 'IP pending' }}</div>
        </div>

        <a
          :href="serverConfig?.webmail_url || '/webmail'"
          target="_blank"
          rel="noopener"
          class="w-full flex items-center justify-center gap-1.5 rounded border border-slate-200 bg-white py-1.5 px-2 text-[11px] font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
        >
          <ExternalLink class="w-3 h-3 text-slate-400" />
          <span>Open Webmail</span>
        </a>
      </div>
    </aside>

    <!-- Main Content Area -->
    <div class="flex-1 p-5 flex flex-col min-w-0 overflow-y-auto">
      <!-- Top Action Bar -->
      <div class="flex flex-wrap items-start justify-between gap-3 pb-3 mb-4 border-b border-slate-200">
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-sm font-bold text-slate-900">{{ sectionTitle }}</h1>
            <span v-if="serverConfig?.max_message_size_mb" class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px]">
              Max: {{ serverConfig.max_message_size_mb }}MB
            </span>
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">{{ sectionSubtitle }}</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button @click="refreshAll" :disabled="loading" class="np-btn-secondary" title="Refresh mail data">
            <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
          <button @click="openTestEmailModal()" class="np-btn-secondary" title="Send a test message to verify delivery">
            <SendHorizontal class="w-3.5 h-3.5 text-slate-600" />
            <span>Send Test Email</span>
          </button>
          <button @click="openCreateMailbox()" :disabled="!domains.length" class="np-btn-secondary" title="Create an email address">
            <MailPlus class="w-3.5 h-3.5 text-emerald-600" />
            <span>New Mailbox</span>
          </button>
          <button @click="showDomainModal = true" class="np-btn-primary" title="Add a domain for mail hosting">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Domain</span>
          </button>
        </div>
      </div>

      <!-- Alerts / Notifications -->
      <div v-if="error" class="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><XCircle class="w-3.5 h-3.5 shrink-0" />{{ error }}</span>
        <button @click="error = ''" class="text-rose-500 hover:text-rose-700"><X class="w-3.5 h-3.5" /></button>
      </div>
      <div v-if="notice" class="mb-3 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><CheckCircle2 class="w-3.5 h-3.5 shrink-0" />{{ notice }}</span>
        <button @click="notice = ''" class="text-emerald-500 hover:text-emerald-700"><X class="w-3.5 h-3.5" /></button>
      </div>

      <!-- 1. OVERVIEW & SERVICES SECTION -->
      <div v-if="activeSection === 'overview'" class="space-y-4">
        <!-- Service Health Cards -->
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="card in serviceCards" :key="card.key" class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-slate-800">{{ card.label }}</span>
              <span class="w-2 h-2 rounded-full" :class="stateDot(card.state)"></span>
            </div>
            <div class="mt-1 flex items-center justify-between text-[11px]">
              <div class="flex items-center gap-1.5" :class="stateText(card.state)">
                <Activity class="w-3 h-3" />
                <span>{{ stateLabel(card.state) }}</span>
              </div>
              <button
                @click="controlService(card.key, 'restart')"
                :disabled="busy === `svc-${card.key}`"
                class="text-[10px] text-slate-500 hover:text-emerald-700 hover:underline flex items-center gap-1 disabled:opacity-50"
                title="Restart service"
              >
                <RotateCw class="w-2.5 h-2.5" :class="{ 'animate-spin': busy === `svc-${card.key}` }" />
                Restart
              </button>
            </div>
          </div>
        </div>

        <!-- Metric Counter Cards -->
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="stat in statCards" :key="stat.label" class="rounded border border-slate-200 bg-white p-3 shadow-2xs">
            <div class="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{{ stat.label }}</div>
            <div class="mt-1 text-xl font-bold text-slate-900">{{ stat.value }}</div>
            <div class="text-[10px] text-slate-500 mt-0.5">{{ stat.hint }}</div>
          </div>
        </div>

        <!-- Two Column Status Grid -->
        <div class="grid gap-4 xl:grid-cols-3">
          <!-- Readiness Checklist -->
          <div class="xl:col-span-2 rounded border border-slate-200 bg-white shadow-2xs">
            <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <ListChecks class="w-3.5 h-3.5 text-emerald-600" />
                <span>Mail Stack Readiness Checklist</span>
              </div>
              <span class="text-[10px] text-slate-400">Automated diagnostic</span>
            </div>
            <div class="divide-y divide-slate-100">
              <div v-for="(item, idx) in healthItems" :key="idx" class="px-3 py-2.5 flex items-start gap-2.5">
                <component :is="healthIcon(item.level)" class="w-3.5 h-3.5 mt-0.5 shrink-0" :class="healthIconClass(item.level)" />
                <div class="flex-1 min-w-0">
                  <div class="font-semibold text-slate-800">{{ item.title }}</div>
                  <div class="text-[11px] text-slate-500 leading-normal">{{ item.detail }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Quick Actions & Webmail Box -->
          <div class="rounded border border-slate-200 bg-white shadow-2xs flex flex-col justify-between">
            <div>
              <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center gap-1.5">
                <Zap class="w-3.5 h-3.5 text-amber-500" />
                <span>Quick Actions</span>
              </div>
              <div class="p-3 space-y-2">
                <button @click="setSection('mailboxes')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50 transition-colors">
                  <span class="flex items-center gap-2"><Inbox class="w-3.5 h-3.5 text-slate-500" />Manage Inboxes</span>
                  <span class="text-[10px] text-slate-500">{{ mailboxes.length }} inboxes</span>
                </button>
                <button @click="setSection('domains')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50 transition-colors">
                  <span class="flex items-center gap-2"><Server class="w-3.5 h-3.5 text-slate-500" />Domains & DNS</span>
                  <span class="text-[10px] text-slate-500">{{ domains.length }} domains</span>
                </button>
                <button @click="openTestEmailModal()" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50 transition-colors">
                  <span class="flex items-center gap-2"><SendHorizontal class="w-3.5 h-3.5 text-slate-500" />Send Test Email</span>
                  <ArrowRight class="w-3.5 h-3.5 text-slate-400" />
                </button>
                <button @click="setSection('queue')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50 transition-colors">
                  <span class="flex items-center gap-2"><Send class="w-3.5 h-3.5 text-slate-500" />Postfix Queue</span>
                  <span class="text-[10px] font-semibold" :class="queue.length ? 'text-amber-600' : 'text-slate-500'">{{ queue.length }} queued</span>
                </button>
                <button @click="setSection('config')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50 transition-colors">
                  <span class="flex items-center gap-2"><Sliders class="w-3.5 h-3.5 text-slate-500" />Server Configuration</span>
                  <ArrowRight class="w-3.5 h-3.5 text-slate-400" />
                </button>
              </div>
            </div>

            <!-- Fast Queue Flush action -->
            <div class="p-3 border-t border-slate-100">
              <button @click="flushQueue" :disabled="busy === 'queue'" class="w-full flex items-center justify-between rounded border border-amber-200 bg-amber-50/80 px-2.5 py-2 text-amber-800 hover:bg-amber-100 disabled:opacity-50 transition-colors">
                <span class="flex items-center gap-2"><RefreshCw class="w-3.5 h-3.5" />Flush Outbound Queue</span>
                <span class="text-[10px] font-mono">postqueue -f</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. INBOXES & MAILBOXES SECTION -->
      <div v-else-if="activeSection === 'mailboxes'" class="space-y-3 flex-1 flex flex-col">
        <!-- Controls & Filters -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <div class="relative">
              <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input v-model="mailboxSearch" placeholder="Search inboxes by email..." class="np-input w-60 pl-8" />
            </div>
            <select v-model.number="mailboxDomainFilter" class="np-input w-48">
              <option :value="0">All domains ({{ domains.length }})</option>
              <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <button @click="openCreateMailbox()" :disabled="!domains.length" class="np-btn-primary">
              <MailPlus class="w-3.5 h-3.5" />
              <span>Create Mailbox</span>
            </button>
          </div>
        </div>

        <!-- Mailboxes Table -->
        <div class="rounded border border-slate-200 overflow-hidden bg-white shadow-2xs flex-1">
          <table class="np-table">
            <thead>
              <tr>
                <th>Email Address</th>
                <th>Domain</th>
                <th>Disk Usage & Quota</th>
                <th>Status</th>
                <th>Client Setup</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in filteredMailboxes" :key="m.id" class="hover:bg-slate-50/80 transition-colors">
                <td>
                  <div class="flex items-center gap-2 font-mono font-medium text-slate-900">
                    <span>{{ m.email }}</span>
                    <button @click="copyText(m.email, `mail-${m.id}`)" class="text-slate-400 hover:text-emerald-700" title="Copy email address">
                      <Copy class="w-3 h-3" />
                    </button>
                  </div>
                </td>
                <td>
                  <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-medium">{{ domainName(m.mail_domain_id) }}</span>
                </td>
                <td class="w-56">
                  <div class="space-y-1">
                    <div class="flex items-center justify-between text-[10px] text-slate-600">
                      <span>{{ m.used_mb !== undefined ? `${m.used_mb} MB` : '0 MB' }} used</span>
                      <span class="font-semibold text-slate-700">{{ m.quota_mb }} MB max</span>
                    </div>
                    <!-- Visual Quota Bar -->
                    <div class="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                      <div
                        class="h-1.5 rounded-full transition-all"
                        :class="quotaBarColor(calcQuotaPercent(m.used_mb || 0, m.quota_mb))"
                        :style="{ width: `${Math.min(100, calcQuotaPercent(m.used_mb || 0, m.quota_mb))}%` }"
                      ></div>
                    </div>
                  </div>
                </td>
                <td>
                  <span v-if="m.is_active" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-medium">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Active
                  </span>
                  <span v-else class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-medium">
                    <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>Disabled
                  </span>
                </td>
                <td>
                  <button @click="openClientConfigModal(m)" class="inline-flex items-center gap-1.5 text-emerald-700 hover:text-emerald-800 font-medium hover:underline text-[11px]">
                    <Smartphone class="w-3 h-3" />
                    <span>Config Instructions</span>
                  </button>
                </td>
                <td class="text-right">
                  <div class="inline-flex flex-wrap justify-end gap-1">
                    <button @click="openSendTestFrom(m)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]" title="Test email sending">Test</button>
                    <button @click="openEditMailbox(m)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]">Edit</button>
                    <button @click="toggleMailbox(m)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]">{{ m.is_active ? 'Disable' : 'Enable' }}</button>
                    <button @click="deleteMailbox(m)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px]">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredMailboxes.length">
                <td colspan="6" class="text-center py-10 text-slate-500">
                  <Inbox class="w-7 h-7 mx-auto mb-1.5 text-slate-300" />
                  <div class="font-medium text-slate-700">No mailboxes found</div>
                  <div class="text-[11px] text-slate-400 mt-0.5">Create your first inbox to begin sending and receiving mail.</div>
                  <button v-if="domains.length" @click="openCreateMailbox()" class="np-btn-primary mt-3 !px-3 !py-1.5">
                    <Plus class="w-3.5 h-3.5" />
                    <span>Create Mailbox</span>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 3. DOMAINS & DNS READINESS SECTION -->
      <div v-else-if="activeSection === 'domains'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="relative">
            <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input v-model="domainSearch" placeholder="Search domains..." class="np-input w-64 pl-8" />
          </div>
          <button @click="showDomainModal = true" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Mail Domain</span>
          </button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden bg-white shadow-2xs">
          <table class="np-table">
            <thead>
              <tr>
                <th>Domain Name</th>
                <th>Inboxes</th>
                <th>Aliases</th>
                <th>Outbound Mode</th>
                <th>Catch-all</th>
                <th>DKIM Key</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in filteredDomains" :key="d.id" class="hover:bg-slate-50/80 transition-colors">
                <td>
                  <div class="font-bold text-slate-900">{{ d.domain }}</div>
                  <div class="text-[10px] text-slate-500">Host: mail.{{ d.domain }}</div>
                </td>
                <td>
                  <button @click="filterByDomain(d.id)" class="text-emerald-700 hover:underline font-semibold">
                    {{ d.mailbox_count }} inboxes
                  </button>
                </td>
                <td>
                  <span class="text-slate-600">{{ d.alias_count }} aliases</span>
                </td>
                <td>
                  <span v-if="d.outbound_mode === 'relay'" class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-50 text-sky-700 text-[10px] font-medium">
                    Relay: {{ d.relay_host || 'missing host' }}
                  </span>
                  <span v-else class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-medium">
                    Direct (Port 25)
                  </span>
                </td>
                <td>
                  <span v-if="d.catchall_address" class="font-mono text-[10px] text-slate-700">{{ d.catchall_address }}</span>
                  <span v-else class="text-[10px] text-slate-400">Disabled</span>
                </td>
                <td>
                  <span class="font-mono text-[10px] text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded">{{ d.dkim_selector }}._domainkey</span>
                </td>
                <td class="text-right">
                  <div class="inline-flex flex-wrap justify-end gap-1">
                    <button @click="openDns(d)" class="px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 text-[11px] font-medium">DNS & DKIM</button>
                    <button @click="openRoute(d)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]">Outbound Route</button>
                    <button @click="openCatchall(d)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]">Catch-all</button>
                    <button @click="openCreateMailbox(d.id)" class="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-[11px]">+ Inbox</button>
                    <button @click="deleteDomain(d)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px]">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredDomains.length">
                <td colspan="7" class="text-center py-10 text-slate-500">
                  <Server class="w-7 h-7 mx-auto mb-1.5 text-slate-300" />
                  <div class="font-medium text-slate-700">No mail domains configured</div>
                  <div class="text-[11px] text-slate-400 mt-0.5">Add a domain to automatically generate 2048-bit DKIM keys and DNS records.</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 4. ALIASES & FORWARDING SECTION -->
      <div v-else-if="activeSection === 'aliases'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-[11px] text-slate-500">
            Forward incoming mail from a source email address to one or more internal/external destination addresses.
          </div>
          <button @click="openAliasModal" :disabled="!domains.length" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Forwarding Alias</span>
          </button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden bg-white shadow-2xs">
          <table class="np-table">
            <thead>
              <tr>
                <th>Source Address (Alias)</th>
                <th>Destination (Forward To)</th>
                <th>Domain</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in aliases" :key="a.id" class="hover:bg-slate-50/80 transition-colors">
                <td class="font-mono font-medium text-slate-900">{{ a.source_email }}</td>
                <td class="font-mono text-slate-700">{{ a.destination_email }}</td>
                <td>{{ domainName(a.mail_domain_id) }}</td>
                <td class="text-right">
                  <button @click="deleteAlias(a)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50 text-[11px]">Delete</button>
                </td>
              </tr>
              <tr v-if="!aliases.length">
                <td colspan="4" class="text-center py-10 text-slate-500">
                  <AtSign class="w-7 h-7 mx-auto mb-1.5 text-slate-300" />
                  <div class="font-medium text-slate-700">No forwarding aliases configured</div>
                  <div class="text-[11px] text-slate-400 mt-0.5">Create aliases like support@ or sales@ that redirect directly to your personal inbox.</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 5. SERVER CONFIGURATION SECTION -->
      <div v-else-if="activeSection === 'config'" class="space-y-4">
        <!-- Service Daemon Management -->
        <div class="rounded border border-slate-200 bg-white shadow-2xs p-4 space-y-3">
          <div class="flex items-center justify-between border-b border-slate-100 pb-2">
            <div>
              <h3 class="font-bold text-slate-900 text-sm flex items-center gap-2">
                <Wrench class="w-4 h-4 text-emerald-600" />
                <span>Mail Stack Daemon Control</span>
              </h3>
              <p class="text-[11px] text-slate-500 mt-0.5">Restart, reload, or inspect individual mail services.</p>
            </div>
            <button @click="loadStatus" class="np-btn-secondary !px-2.5 !py-1">
              <RefreshCw class="w-3 h-3" />
              <span>Check Status</span>
            </button>
          </div>

          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 pt-1">
            <div v-for="svc in serviceCards" :key="svc.key" class="rounded border border-slate-200 p-3 bg-slate-50/50 space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-semibold text-slate-800">{{ svc.label }}</span>
                <span class="w-2 h-2 rounded-full" :class="stateDot(svc.state)"></span>
              </div>
              <div class="text-[11px]" :class="stateText(svc.state)">
                Status: <span class="font-medium">{{ stateLabel(svc.state) }}</span>
              </div>
              <div class="flex items-center gap-1.5 pt-1">
                <button
                  @click="controlService(svc.key, 'restart')"
                  :disabled="busy === `svc-${svc.key}`"
                  class="flex-1 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-[10px] font-medium text-slate-700"
                >
                  Restart
                </button>
                <button
                  @click="controlService(svc.key, 'reload')"
                  :disabled="busy === `svc-${svc.key}`"
                  class="flex-1 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-[10px] font-medium text-slate-700"
                >
                  Reload
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Postfix Core Settings -->
        <div class="rounded border border-slate-200 bg-white shadow-2xs p-4 space-y-3">
          <div class="border-b border-slate-100 pb-2">
            <h3 class="font-bold text-slate-900 text-sm flex items-center gap-2">
              <Sliders class="w-4 h-4 text-emerald-600" />
              <span>Core Mail Server Tuning</span>
            </h3>
            <p class="text-[11px] text-slate-500 mt-0.5">Tune Postfix global message size limits, TLS transport encryption and Webmail link.</p>
          </div>

          <div class="grid gap-4 md:grid-cols-2 pt-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Max Message Size (MB)</label>
              <div class="flex items-center gap-2">
                <input v-model.number="configEditForm.max_message_size_mb" type="number" min="5" max="200" class="np-input w-32" />
                <div class="flex items-center gap-1">
                  <button @click="configEditForm.max_message_size_mb = 25" class="px-2 py-1 rounded border border-slate-200 bg-slate-50 text-[10px]">25MB</button>
                  <button @click="configEditForm.max_message_size_mb = 50" class="px-2 py-1 rounded border border-slate-200 bg-slate-50 text-[10px]">50MB</button>
                  <button @click="configEditForm.max_message_size_mb = 100" class="px-2 py-1 rounded border border-slate-200 bg-slate-50 text-[10px]">100MB</button>
                </div>
              </div>
              <p class="text-[10px] text-slate-500 mt-1">Controls Postfix <code class="font-mono">message_size_limit</code> parameter.</p>
            </div>

            <div>
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Inbound SMTP TLS Security Level</label>
              <select v-model="configEditForm.tls_security_level" class="np-input w-full">
                <option value="may">Opportunistic TLS (may) - Recommended</option>
                <option value="encrypt">Mandatory TLS (encrypt)</option>
              </select>
              <p class="text-[10px] text-slate-500 mt-1">Controls Postfix <code class="font-mono">smtpd_tls_security_level</code>.</p>
            </div>

            <div class="md:col-span-2">
              <label class="block text-[11px] font-semibold text-slate-700 mb-1">Webmail Access URL</label>
              <input v-model="configEditForm.webmail_url" placeholder="/webmail or https://webmail.example.com" class="np-input w-full" />
              <p class="text-[10px] text-slate-500 mt-1">URL used by the "Open Webmail" launcher buttons throughout the panel.</p>
            </div>
          </div>

          <div class="flex justify-end pt-2">
            <button @click="saveServerConfig" :disabled="busy === 'config'" class="np-btn-primary">
              <CheckCircle2 class="w-3.5 h-3.5" />
              <span>{{ busy === 'config' ? 'Saving…' : 'Apply Configuration' }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 6. OUTBOUND & DELIVERABILITY TESTING SECTION -->
      <div v-else-if="activeSection === 'test'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-2">
          <!-- Send Test Email Tool -->
          <div class="rounded border border-slate-200 bg-white shadow-2xs p-4 space-y-3">
            <div class="border-b border-slate-100 pb-2">
              <h3 class="font-bold text-slate-900 text-sm flex items-center gap-2">
                <SendHorizontal class="w-4 h-4 text-emerald-600" />
                <span>Send Outbound Test Email</span>
              </h3>
              <p class="text-[11px] text-slate-500 mt-0.5">Test SMTP handshake and delivery directly from your local MTA.</p>
            </div>

            <div class="space-y-3 pt-1">
              <div>
                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Sender Email</label>
                <select v-if="mailboxes.length" v-model="testEmailForm.sender" class="np-input w-full">
                  <option v-for="m in mailboxes" :key="m.id" :value="m.email">{{ m.email }}</option>
                </select>
                <input v-else v-model="testEmailForm.sender" placeholder="postmaster@yourdomain.com" class="np-input w-full" />
              </div>

              <div>
                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Recipient Email</label>
                <input v-model="testEmailForm.recipient" placeholder="you@gmail.com or test@mail-tester.com" class="np-input w-full" />
              </div>

              <div>
                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Subject</label>
                <input v-model="testEmailForm.subject" class="np-input w-full" />
              </div>

              <div>
                <label class="block text-[11px] font-semibold text-slate-700 mb-1">Message Body</label>
                <textarea v-model="testEmailForm.body" rows="3" class="np-input w-full"></textarea>
              </div>

              <div class="flex justify-end pt-1">
                <button @click="sendTestEmail" :disabled="busy === 'test-email'" class="np-btn-primary">
                  <Send class="w-3.5 h-3.5" :class="{ 'animate-pulse': busy === 'test-email' }" />
                  <span>{{ busy === 'test-email' ? 'Dispatching…' : 'Send Test Message' }}</span>
                </button>
              </div>

              <!-- Test Result Output -->
              <div v-if="testEmailResult" class="mt-3 p-3 rounded border text-[11px] leading-relaxed" :class="testEmailResult.success ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-rose-50 border-rose-200 text-rose-800'">
                <div class="font-semibold flex items-center gap-1.5 mb-1">
                  <component :is="testEmailResult.success ? CheckCircle2 : XCircle" class="w-3.5 h-3.5" />
                  <span>{{ testEmailResult.success ? 'Email Queued Successfully' : 'Delivery Error' }}</span>
                </div>
                <div>{{ testEmailResult.message || testEmailResult.error }}</div>
                <div class="text-[10px] opacity-80 mt-1">Check Postfix Queue or Logs for delivery status.</div>
              </div>
            </div>
          </div>

          <!-- Port 25 & PTR Diagnostics -->
          <div class="rounded border border-slate-200 bg-white shadow-2xs p-4 space-y-3">
            <div class="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 class="font-bold text-slate-900 text-sm flex items-center gap-2">
                <ShieldCheck class="w-4 h-4 text-emerald-600" />
                <span>Egress & Port 25 Diagnostics</span>
              </h3>
              <button @click="runEgress" :disabled="egressLoading" class="np-btn-secondary !px-2.5 !py-1">
                <RefreshCw :class="{ 'animate-spin': egressLoading }" class="w-3 h-3" />
                <span>Re-test</span>
              </button>
            </div>

            <div class="space-y-2.5 text-[11px] pt-1">
              <div class="flex items-center justify-between py-1 border-b border-slate-100">
                <span class="text-slate-500">Mail Hostname</span>
                <span class="font-mono font-medium text-slate-800">{{ egress?.hostname || mailHost }}</span>
              </div>
              <div class="flex items-center justify-between py-1 border-b border-slate-100">
                <span class="text-slate-500">Server Public IP</span>
                <span class="font-mono font-medium text-slate-800">{{ egress?.public_ip || status?.public_ip || '—' }}</span>
              </div>
              <div class="flex items-center justify-between py-1 border-b border-slate-100">
                <span class="text-slate-500">Outbound Port 25</span>
                <span v-if="egress" class="inline-flex items-center gap-1 font-semibold" :class="egress.port_25_egress_reachable ? 'text-emerald-700' : 'text-rose-700'">
                  <component :is="egress.port_25_egress_reachable ? CheckCircle2 : XCircle" class="w-3.5 h-3.5" />
                  {{ egress.port_25_egress_reachable ? 'Open & Reachable' : 'Blocked by Provider' }}
                </span>
                <span v-else class="text-slate-400">Not tested</span>
              </div>
              <div class="flex items-start justify-between py-1 border-b border-slate-100 gap-3">
                <span class="text-slate-500 shrink-0">PTR (Reverse DNS)</span>
                <span class="font-mono text-slate-800 text-right break-all">{{ egress?.ptr_records?.length ? egress.ptr_records.join(', ') : 'No PTR record' }}</span>
              </div>

              <!-- Recommendation Box -->
              <div v-if="egress" class="rounded border border-slate-200 bg-slate-50 p-3 space-y-1.5 mt-2">
                <div v-for="(rec, i) in egress.recommendations" :key="i" class="flex items-start gap-1.5 text-slate-600">
                  <Info class="w-3.5 h-3.5 text-sky-500 mt-0.5 shrink-0" />
                  <span>{{ rec }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 7. POSTFIX QUEUE SECTION -->
      <div v-else-if="activeSection === 'queue'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2 text-[11px]">
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-700 font-medium">Total: {{ queueCounts.total }}</span>
            <span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 font-medium">Active: {{ queueCounts.active }}</span>
            <span class="px-2 py-1 rounded bg-amber-50 text-amber-700 font-medium">Deferred: {{ queueCounts.deferred }}</span>
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-600 font-medium">Held: {{ queueCounts.held }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button @click="loadQueue" :disabled="queueLoading" class="np-btn-secondary">
              <RefreshCw :class="{ 'animate-spin': queueLoading }" class="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
            <button @click="queueBulkAction('requeue')" :disabled="busy === 'queue'" class="np-btn-secondary" title="Re-queue all deferred messages">
              <RotateCw class="w-3.5 h-3.5" />
              <span>Retry All</span>
            </button>
            <button @click="queueBulkAction('delete-deferred')" :disabled="busy === 'queue' || !queueCounts.deferred" class="np-btn-secondary text-rose-600 hover:bg-rose-50" title="Delete all deferred messages">
              <span>Clear Deferred</span>
            </button>
            <button @click="flushQueue" :disabled="busy === 'queue'" class="np-btn-primary">
              <Send class="w-3.5 h-3.5" />
              <span>Flush Queue</span>
            </button>
          </div>
        </div>

        <div v-if="queueError" class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">{{ queueError }}</div>

        <div class="rounded border border-slate-200 overflow-hidden bg-white shadow-2xs flex-1">
          <table class="np-table">
            <thead>
              <tr>
                <th>Queue ID</th>
                <th>State</th>
                <th>Size</th>
                <th>Arrival Time</th>
                <th>Sender</th>
                <th>Recipients</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in queue" :key="q.queue_id" class="hover:bg-slate-50/80 transition-colors">
                <td class="font-mono text-[10px] font-semibold text-slate-800">{{ q.queue_id }}</td>
                <td>
                  <span class="px-2 py-0.5 rounded text-[10px] font-medium" :class="queueStateClass(q.queue_name)">{{ q.queue_name || 'unknown' }}</span>
                </td>
                <td>{{ formatSize(q.message_size) }}</td>
                <td class="text-slate-500">{{ formatEpoch(q.arrival_time) }}</td>
                <td class="font-mono text-[10px] break-all">{{ q.sender || '—' }}</td>
                <td class="font-mono text-[10px] break-all">{{ recipientsOf(q) }}</td>
                <td class="text-right">
                  <div class="inline-flex gap-1">
                    <button v-if="q.queue_name === 'hold'" @click="queueAction('release', q)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-[10px]">Release</button>
                    <button v-else @click="queueAction('hold', q)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-[10px]">Hold</button>
                    <button @click="queueAction('requeue', q)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-[10px]">Re-queue</button>
                    <button @click="queueAction('delete', q)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50 text-[10px]">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!queue.length">
                <td colspan="7" class="text-center py-10 text-slate-500">
                  <CheckCircle2 class="w-7 h-7 mx-auto mb-1.5 text-emerald-400" />
                  <div class="font-medium text-slate-700">Postfix queue is empty</div>
                  <div class="text-[11px] text-slate-400 mt-0.5">All outbound and inbound messages have been delivered or processed.</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 8. LOGS & DIAGNOSTICS SECTION -->
      <div v-else-if="activeSection === 'logs'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <select v-model.number="logTail" @change="loadLogs" class="np-input w-36">
              <option :value="100">Last 100 lines</option>
              <option :value="200">Last 200 lines</option>
              <option :value="500">Last 500 lines</option>
              <option :value="1000">Last 1000 lines</option>
            </select>
            <div class="relative">
              <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2 top-2.5" />
              <input v-model="logFilter" placeholder="Filter log text..." class="np-input w-48 pl-7 text-[11px]" />
            </div>
            <span v-if="logSource" class="font-mono text-[10px] text-slate-500">{{ logSource }}</span>
          </div>
          <button @click="loadLogs" :disabled="logsLoading" class="np-btn-secondary">
            <RefreshCw :class="{ 'animate-spin': logsLoading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>

        <div v-if="logError" class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">{{ logError }}</div>

        <pre class="flex-1 min-h-[22rem] max-h-[36rem] overflow-auto rounded border border-slate-800 bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-200 font-mono shadow-inner">{{ filteredLogs.length ? filteredLogs.join('\n') : 'No matching log lines.' }}</pre>

        <!-- Command Cheat Sheet -->
        <div class="rounded border border-slate-200 bg-white p-3 space-y-2 shadow-2xs">
          <div class="font-semibold text-slate-800 flex items-center gap-1.5 text-xs">
            <Terminal class="w-3.5 h-3.5 text-slate-600" />
            <span>CLI Diagnostic Reference</span>
          </div>
          <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="cmd in commands" :key="cmd.cmd" class="rounded border border-slate-200 p-2 bg-slate-50/50">
              <div class="flex items-center justify-between gap-1">
                <span class="font-medium text-slate-700 text-[11px]">{{ cmd.label }}</span>
                <button @click="copyText(cmd.cmd, cmd.cmd)" class="text-emerald-700 hover:underline flex items-center gap-1 text-[10px]">
                  <Copy class="w-3 h-3" />{{ copiedKey === cmd.cmd ? 'Copied' : 'Copy' }}
                </button>
              </div>
              <div class="font-mono text-[10px] text-slate-500 break-all mt-0.5">{{ cmd.cmd }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- MODAL: ADD MAIL DOMAIN -->
    <div v-if="showDomainModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showDomainModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Add Mail Domain</h3>
          <button @click="showDomainModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-semibold text-slate-700">Domain Name</label>
        <input v-model="newDomain.domain" placeholder="example.com" class="np-input w-full" />
        <label class="block text-[11px] font-semibold text-slate-700">DKIM Selector</label>
        <input v-model="newDomain.dkim_selector" placeholder="default" class="np-input w-full" />
        <p class="text-[10px] text-slate-500">A dedicated 2048-bit RSA DKIM keypair is generated immediately. You can sync or copy DNS records once created.</p>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showDomainModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createDomain" :disabled="busy === 'domain'" class="np-btn-primary">{{ busy === 'domain' ? 'Creating…' : 'Create Domain' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: CREATE MAILBOX -->
    <div v-if="showMboxModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showMboxModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Create New Mailbox</h3>
          <button @click="showMboxModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 mb-1">Email Address</label>
          <div class="flex items-center gap-1.5">
            <input v-model="newMbox.local_part" placeholder="info" class="np-input flex-1" />
            <span class="text-slate-400 font-bold">@</span>
            <select v-model.number="newMbox.mail_domain_id" class="np-input w-44">
              <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
            </select>
          </div>
        </div>
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 mb-1">Mailbox Password</label>
          <div class="flex items-center gap-1.5">
            <input v-model="newMbox.password" :type="showNewPassword ? 'text' : 'password'" placeholder="Minimum 8 characters" class="np-input flex-1" />
            <button @click="showNewPassword = !showNewPassword" class="np-btn-secondary !px-2" :title="showNewPassword ? 'Hide' : 'Show'">
              <component :is="showNewPassword ? EyeOff : Eye" class="w-3.5 h-3.5" />
            </button>
            <button @click="newMbox.password = generatePassword()" class="np-btn-secondary !px-2" title="Generate strong password">Generate</button>
          </div>
        </div>
        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block text-[11px] font-semibold text-slate-700">Storage Quota (MB)</label>
            <div class="flex gap-1">
              <button @click="newMbox.quota_mb = 500" class="text-[10px] text-slate-500 hover:text-emerald-700 underline">500MB</button>
              <button @click="newMbox.quota_mb = 1024" class="text-[10px] text-slate-500 hover:text-emerald-700 underline">1GB</button>
              <button @click="newMbox.quota_mb = 5120" class="text-[10px] text-slate-500 hover:text-emerald-700 underline">5GB</button>
            </div>
          </div>
          <input v-model.number="newMbox.quota_mb" type="number" min="50" class="np-input w-full" />
        </div>
        <p class="text-[10px] text-slate-500">IMAP: {{ mailHost }}:993 (SSL) · SMTP: {{ mailHost }}:587 (STARTTLS).</p>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showMboxModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createMailbox" :disabled="busy === 'mailbox'" class="np-btn-primary">{{ busy === 'mailbox' ? 'Creating…' : 'Create Mailbox' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: EDIT MAILBOX -->
    <div v-if="showEditMboxModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showEditMboxModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Edit Mailbox</h3>
          <button @click="showEditMboxModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <div class="rounded bg-slate-50 border border-slate-200 px-2.5 py-2 font-mono text-[11px] text-slate-800 font-semibold">{{ editMbox.email }}</div>
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 mb-1">Quota (MB)</label>
          <input v-model.number="editMbox.quota_mb" type="number" min="50" class="np-input w-full" />
        </div>
        <label class="flex items-center gap-2 text-[11px] text-slate-700 py-1">
          <input v-model="editMbox.is_active" type="checkbox" class="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500" />
          Mailbox active (allows login and message delivery)
        </label>
        <div>
          <label class="block text-[11px] font-semibold text-slate-700 mb-1">Reset Password (leave blank to keep)</label>
          <div class="flex items-center gap-1.5">
            <input v-model="editMbox.password" :type="showEditPassword ? 'text' : 'password'" placeholder="Enter new password" class="np-input flex-1" />
            <button @click="showEditPassword = !showEditPassword" class="np-btn-secondary !px-2">
              <component :is="showEditPassword ? EyeOff : Eye" class="w-3.5 h-3.5" />
            </button>
            <button @click="editMbox.password = generatePassword()" class="np-btn-secondary !px-2">Generate</button>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showEditMboxModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveMailbox" :disabled="busy === 'mailbox'" class="np-btn-primary">{{ busy === 'mailbox' ? 'Saving…' : 'Save Changes' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: CLIENT CONFIGURATION & MOBILECONFIG DOWNLOAD -->
    <div v-if="showClientModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showClientModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-xl space-y-4 shadow-xl">
        <div class="flex items-start justify-between border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Smartphone class="w-4 h-4 text-emerald-600" />
              <span>Email Client Configuration</span>
            </h3>
            <p class="text-[11px] text-slate-500 font-mono mt-0.5">{{ clientConfigData?.email }}</p>
          </div>
          <button @click="showClientModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>

        <!-- 1-Click Apple Mail Profile Download -->
        <div class="rounded border border-emerald-200 bg-emerald-50/70 p-3 flex items-center justify-between gap-3">
          <div>
            <div class="font-semibold text-emerald-900 text-xs">iOS & macOS 1-Click Setup Profile</div>
            <div class="text-[11px] text-emerald-700">Download the Apple profile to automatically configure your iPhone, iPad, or Mac Mail app.</div>
          </div>
          <a
            :href="`/api/v1/mail/client-config/mobileconfig?email=${encodeURIComponent(clientConfigData?.email || '')}`"
            download
            class="np-btn-primary !bg-emerald-600 hover:!bg-emerald-700 shrink-0"
          >
            <Download class="w-3.5 h-3.5" />
            <span>Download .mobileconfig</span>
          </a>
        </div>

        <!-- Protocols Details -->
        <div class="grid gap-3 sm:grid-cols-2">
          <!-- Incoming IMAP -->
          <div class="rounded border border-slate-200 p-3 bg-slate-50/50 space-y-2">
            <div class="font-bold text-slate-800 text-[11px] flex items-center justify-between">
              <span>Incoming Server (IMAP)</span>
              <span class="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px]">Recommended</span>
            </div>
            <div class="space-y-1 text-[11px]">
              <div class="flex justify-between">
                <span class="text-slate-500">Host:</span>
                <span class="font-mono font-medium text-slate-800">{{ clientConfigData?.mail_host }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">SSL/TLS Port:</span>
                <span class="font-mono font-semibold text-emerald-700">993</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">STARTTLS Port:</span>
                <span class="font-mono text-slate-700">143</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">Username:</span>
                <span class="font-mono text-slate-800 truncate max-w-[12rem]">{{ clientConfigData?.email }}</span>
              </div>
            </div>
          </div>

          <!-- Outgoing SMTP -->
          <div class="rounded border border-slate-200 p-3 bg-slate-50/50 space-y-2">
            <div class="font-bold text-slate-800 text-[11px] flex items-center justify-between">
              <span>Outgoing Server (SMTP)</span>
              <span class="px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px]">Auth Required</span>
            </div>
            <div class="space-y-1 text-[11px]">
              <div class="flex justify-between">
                <span class="text-slate-500">Host:</span>
                <span class="font-mono font-medium text-slate-800">{{ clientConfigData?.mail_host }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">STARTTLS Port:</span>
                <span class="font-mono font-semibold text-emerald-700">587</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">SSL/TLS Port:</span>
                <span class="font-mono text-slate-700">465</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">Authentication:</span>
                <span class="text-slate-700">Same as password</span>
              </div>
            </div>
          </div>
        </div>

        <div class="flex justify-between items-center pt-2 border-t border-slate-100">
          <a
            :href="serverConfig?.webmail_url || '/webmail'"
            target="_blank"
            rel="noopener"
            class="text-emerald-700 hover:underline flex items-center gap-1 text-[11px] font-medium"
          >
            <ExternalLink class="w-3.5 h-3.5" />
            <span>Open in Webmail Client</span>
          </a>
          <button @click="showClientModal = false" class="np-btn-secondary">Close</button>
        </div>
      </div>
    </div>

    <!-- MODAL: ADD ALIAS -->
    <div v-if="showAliasModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showAliasModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Add Forwarding Alias</h3>
          <button @click="showAliasModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-semibold text-slate-700">Source Address</label>
        <div class="flex items-center gap-1.5">
          <input v-model="newAlias.source_local" placeholder="sales" class="np-input flex-1" />
          <span class="text-slate-400 font-bold">@</span>
          <select v-model.number="newAlias.mail_domain_id" class="np-input w-44">
            <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
          </select>
        </div>
        <label class="block text-[11px] font-semibold text-slate-700">Forward To (Destination)</label>
        <input v-model="newAlias.destination_email" placeholder="inbox@example.com" class="np-input w-full" />
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showAliasModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createAlias" :disabled="busy === 'alias'" class="np-btn-primary">{{ busy === 'alias' ? 'Creating…' : 'Create Alias' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: OUTBOUND ROUTE -->
    <div v-if="showRouteModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showRouteModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Outbound Route · {{ routeForm.domain }}</h3>
          <button @click="showRouteModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-semibold text-slate-700">Egress Delivery Mode</label>
        <select v-model="routeForm.outbound_mode" class="np-input w-full">
          <option value="direct">Direct Egress (Send from this host on Port 25)</option>
          <option value="relay">SMTP Relay Service (SendGrid, Mailgun, AWS SES, Postmark)</option>
        </select>
        <template v-if="routeForm.outbound_mode === 'relay'">
          <label class="block text-[11px] font-semibold text-slate-700">Relay Host</label>
          <input v-model="routeForm.relay_host" placeholder="smtp.sendgrid.net" class="np-input w-full" />
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-semibold text-slate-700">Port</label>
              <input v-model.number="routeForm.relay_port" type="number" min="1" max="65535" class="np-input w-full" />
            </div>
            <div>
              <label class="block text-[11px] font-semibold text-slate-700">Username</label>
              <input v-model="routeForm.relay_username" placeholder="apikey" class="np-input w-full" />
            </div>
          </div>
          <label class="block text-[11px] font-semibold text-slate-700">Password / API Key</label>
          <input v-model="routeForm.relay_password" type="password" placeholder="Leave blank to keep existing password" class="np-input w-full" />
        </template>
        <p v-else class="text-[10px] text-slate-500">Direct mode delivers directly to destination MX servers on Port 25. If port 25 is blocked by your hosting provider, switch to an authenticated SMTP relay.</p>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showRouteModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveRoute" :disabled="busy === 'route'" class="np-btn-primary">{{ busy === 'route' ? 'Saving…' : 'Save Route' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: CATCH-ALL -->
    <div v-if="showCatchallModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showCatchallModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3 shadow-xl">
        <div class="flex items-center justify-between border-b border-slate-100 pb-2">
          <h3 class="text-sm font-bold text-slate-900">Catch-all Address · {{ catchallForm.domain }}</h3>
          <button @click="showCatchallModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-semibold text-slate-700">Forward Unknown Recipients To</label>
        <input v-model="catchallForm.catchall_address" placeholder="admin@example.com (leave blank to disable)" class="np-input w-full" />
        <p class="text-[10px] text-slate-500">When enabled, any email sent to an unassigned local part (e.g. random@{{ catchallForm.domain }}) will be delivered to this mailbox.</p>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button @click="showCatchallModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveCatchall" :disabled="busy === 'catchall'" class="np-btn-primary">{{ busy === 'catchall' ? 'Saving…' : 'Save Catch-all' }}</button>
        </div>
      </div>
    </div>

    <!-- MODAL: DNS READINESS & 1-CLICK DNS SYNC -->
    <div v-if="showDnsModal" class="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto" @click.self="showDnsModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-3xl space-y-3 my-6 shadow-xl">
        <div class="flex items-start justify-between gap-3 border-b border-slate-100 pb-2">
          <div>
            <h3 class="text-sm font-bold text-slate-900 flex items-center gap-2">
              <ShieldCheck class="w-4 h-4 text-emerald-600" />
              <span>DNS Records & Authentication · {{ dnsDomain?.domain }}</span>
            </h3>
            <p class="text-[11px] text-slate-500 mt-0.5">Required DNS records for inbound routing, SPF, 2048-bit DKIM, and DMARC alignment.</p>
          </div>
          <button @click="showDnsModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>

        <div v-if="dnsLoading" class="py-10 text-center text-slate-500">Loading DNS records & readiness status…</div>
        <template v-else-if="dnsReport">
          <!-- 1-Click Sync to NexoPanel DNS Zone Banner -->
          <div class="rounded border border-emerald-200 bg-emerald-50/80 p-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="font-bold text-emerald-900 text-xs">Automated DNS Sync</div>
              <div class="text-[11px] text-emerald-700">If this domain is hosted on NexoPanel's DNS Manager, automatically publish all records in one click!</div>
            </div>
            <button @click="syncDnsToZone(dnsDomain)" :disabled="busy === 'sync-dns'" class="np-btn-primary !bg-emerald-600 hover:!bg-emerald-700">
              <RotateCw class="w-3.5 h-3.5" :class="{ 'animate-spin': busy === 'sync-dns' }" />
              <span>Sync to NexoPanel DNS</span>
            </button>
          </div>

          <div class="space-y-2.5">
            <div v-for="rec in dnsReport.required_records" :key="recKey(rec)" class="rounded border border-slate-200 p-3 space-y-1.5 bg-white">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <span class="px-1.5 py-0.5 rounded bg-slate-900 text-white font-mono text-[10px] font-bold">{{ rec.type }}</span>
                  <span class="font-mono text-[11px] font-semibold text-slate-800">{{ rec.name }}</span>
                  <span v-if="rec.priority" class="text-[10px] text-slate-500">priority {{ rec.priority }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <span
                    v-if="dnsReport.live_checks_enabled && dnsCheckFor(rec)"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
                    :class="dnsCheckFor(rec).propagated ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'"
                  >
                    <component :is="dnsCheckFor(rec).propagated ? CheckCircle2 : XCircle" class="w-3 h-3" />
                    {{ dnsCheckFor(rec).propagated ? 'Propagated' : 'Missing' }}
                  </span>
                  <span v-else-if="dnsReport.live_checks_enabled" class="text-[10px] text-slate-400">Not checked</span>
                  <button @click="copyText(rec.value, recKey(rec))" class="inline-flex items-center gap-1 text-emerald-700 hover:underline text-[11px] font-medium">
                    <Copy class="w-3 h-3" />{{ copiedKey === recKey(rec) ? 'Copied' : 'Copy Record' }}
                  </button>
                </div>
              </div>
              <div class="font-mono text-[11px] break-all text-slate-700 bg-slate-50 rounded p-2 select-all border border-slate-100">{{ rec.value }}</div>
              <div class="text-[11px] text-slate-500">{{ rec.purpose }}</div>
              <div v-if="dnsReport.live_checks_enabled && dnsCheckFor(rec) && !dnsCheckFor(rec).propagated" class="rounded bg-amber-50 border border-amber-200 px-2.5 py-1.5 text-[11px] text-amber-800">
                {{ rec.fix }}
              </div>
            </div>
          </div>
        </template>
        <div v-else class="py-10 text-center text-rose-600">Unable to load DNS readiness report.</div>

        <div class="flex justify-end pt-2 border-t border-slate-100">
          <button @click="showDnsModal = false" class="np-btn-secondary">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  AtSign,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  Gauge,
  Inbox,
  Info,
  ListChecks,
  Mail,
  MailPlus,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  Send,
  SendHorizontal,
  Server,
  ShieldCheck,
  Sliders,
  Smartphone,
  Terminal,
  Wrench,
  X,
  XCircle,
  Zap,
} from 'lucide-vue-next'

type Section = 'overview' | 'mailboxes' | 'domains' | 'aliases' | 'config' | 'test' | 'queue' | 'logs'

const { apiFetch } = useApi()

const sections: { key: Section; label: string; icon: any }[] = [
  { key: 'overview', label: 'Overview', icon: Gauge },
  { key: 'mailboxes', label: 'Inboxes & Mailboxes', icon: Inbox },
  { key: 'domains', label: 'Domains & DNS', icon: Server },
  { key: 'aliases', label: 'Aliases & Forwarding', icon: AtSign },
  { key: 'config', label: 'Server Configuration', icon: Sliders },
  { key: 'test', label: 'Test & Deliverability', icon: SendHorizontal },
  { key: 'queue', label: 'Postfix Queue', icon: Send },
  { key: 'logs', label: 'Server Logs', icon: FileText },
]

const commands = [
  { label: 'Inspect Postfix queue', cmd: 'postqueue -p' },
  { label: 'Flush all queues', cmd: 'postqueue -f' },
  { label: 'Clear deferred queue', cmd: 'postsuper -d ALL deferred' },
  { label: 'Restart mail stack', cmd: 'systemctl restart postfix dovecot opendkim rspamd' },
  { label: 'Tail live mail log', cmd: 'tail -f /var/log/mail.log' },
  { label: 'Test SMTP submission', cmd: 'openssl s_client -connect 127.0.0.1:587 -starttls smtp -brief' },
]

const activeSection = ref<Section>('overview')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref('')
const copiedKey = ref('')

const status = ref<any>(null)
const domains = ref<any[]>([])
const mailboxes = ref<any[]>([])
const aliases = ref<any[]>([])
const serverConfig = ref<any>(null)
const queue = ref<any[]>([])
const queueError = ref('')
const queueLoading = ref(false)
const logs = ref<string[]>([])
const logSource = ref<string | null>(null)
const logError = ref('')
const logsLoading = ref(false)
const logTail = ref(100)
const logFilter = ref('')
const egress = ref<any>(null)
const egressLoading = ref(false)

const domainSearch = ref('')
const mailboxSearch = ref('')
const mailboxDomainFilter = ref(0)

const dnsReport = ref<any>(null)
const dnsDomain = ref<any>(null)
const dnsLoading = ref(false)
const showDnsModal = ref(false)

const showDomainModal = ref(false)
const showMboxModal = ref(false)
const showEditMboxModal = ref(false)
const showClientModal = ref(false)
const clientConfigData = ref<any>(null)
const showAliasModal = ref(false)
const showRouteModal = ref(false)
const showCatchallModal = ref(false)
const showNewPassword = ref(false)
const showEditPassword = ref(false)

const newDomain = reactive({ domain: '', dkim_selector: 'default' })
const newMbox = reactive({ mail_domain_id: 0, local_part: '', password: '', quota_mb: 1024 })
const editMbox = reactive({ id: 0, email: '', password: '', quota_mb: 1024, is_active: true })
const newAlias = reactive({ mail_domain_id: 0, source_local: '', destination_email: '' })
const routeForm = reactive({
  id: 0,
  domain: '',
  outbound_mode: 'direct',
  relay_host: '',
  relay_port: 587,
  relay_username: '',
  relay_password: '',
})
const catchallForm = reactive({ id: 0, domain: '', catchall_address: '' })

const configEditForm = reactive({
  max_message_size_mb: 25,
  tls_security_level: 'may',
  webmail_url: '/webmail',
})

const testEmailForm = reactive({
  sender: '',
  recipient: '',
  subject: 'NexoPanel Mail Delivery Verification',
  body: 'Hello,\n\nThis is a verification test message dispatched from NexoPanel Mail Server.\nAll SMTP protocols and delivery maps are operating properly.',
})
const testEmailResult = ref<any>(null)

const domainById = computed(() => {
  const map: Record<number, any> = {}
  for (const d of domains.value) map[d.id] = d
  return map
})

const mailHost = computed(() => status.value?.hostname || egress.value?.hostname || 'mail server')

const sectionTitle = computed(() => {
  switch (activeSection.value) {
    case 'overview':
      return 'Mail Server Dashboard & Services'
    case 'mailboxes':
      return 'Inboxes & Mailbox Accounts'
    case 'domains':
      return 'Mail Domains & DNS Authentication'
    case 'aliases':
      return 'Forwarding Rules & Aliases'
    case 'config':
      return 'Server Daemon Configuration'
    case 'test':
      return 'Deliverability & Outbound Test'
    case 'queue':
      return 'Postfix Outbound Mail Queue'
    case 'logs':
      return 'Mail Server Transaction Logs'
    default:
      return 'Mail Server Console'
  }
})

const sectionSubtitle = computed(() => {
  switch (activeSection.value) {
    case 'overview':
      return 'Live service health, quick metrics and stack readiness diagnostics.'
    case 'mailboxes':
      return 'Create and manage email addresses, monitor disk quota usage, and obtain setup profiles.'
    case 'domains':
      return 'Manage mail domains, generate 2048-bit DKIM keys, and sync DNS records.'
    case 'aliases':
      return 'Forward incoming messages to internal mailboxes or external addresses.'
    case 'config':
      return 'Tune message size limits, TLS transport encryption, and service controls.'
    case 'test':
      return 'Send real test emails to verify SMTP handshakes and inspect port 25 connectivity.'
    case 'queue':
      return 'Monitor active and deferred messages in the Postfix queue.'
    case 'logs':
      return 'Real-time SMTP and IMAP activity log stream.'
    default:
      return ''
  }
})

const filteredDomains = computed(() => {
  const q = domainSearch.value.trim().toLowerCase()
  return q ? domains.value.filter((d) => d.domain.toLowerCase().includes(q)) : domains.value
})

const filteredMailboxes = computed(() => {
  const q = mailboxSearch.value.trim().toLowerCase()
  return mailboxes.value.filter((m) => {
    if (mailboxDomainFilter.value && m.mail_domain_id !== mailboxDomainFilter.value) return false
    return !q || m.email.toLowerCase().includes(q)
  })
})

const filteredLogs = computed(() => {
  if (!logFilter.value.trim()) return logs.value
  const q = logFilter.value.trim().toLowerCase()
  return logs.value.filter((line) => line.toLowerCase().includes(q))
})

const serviceCards = computed(() => {
  const s = status.value?.services || {}
  return [
    { key: 'postfix', label: 'Postfix · SMTP', state: s.postfix || 'unknown' },
    { key: 'dovecot', label: 'Dovecot · IMAP/POP3', state: s.dovecot || 'unknown' },
    { key: 'opendkim', label: 'OpenDKIM · Signing', state: s.opendkim || 'unknown' },
    { key: 'rspamd', label: 'Rspamd · Filtering', state: s.rspamd || 'unknown' },
  ]
})

const statCards = computed(() => {
  const c = status.value?.counts || {}
  return [
    { label: 'Mail Domains', value: c.domains ?? domains.value.length, hint: 'Active mail domains' },
    { label: 'Mailboxes', value: c.mailboxes ?? mailboxes.value.length, hint: 'Configured inboxes' },
    { label: 'Active Inboxes', value: c.active_mailboxes ?? mailboxes.value.filter((m) => m.is_active).length, hint: 'Login-enabled accounts' },
    { label: 'Aliases', value: c.aliases ?? aliases.value.length, hint: 'Forwarding rules' },
  ]
})

const queueCounts = computed(() => {
  const counts = { total: queue.value.length, active: 0, deferred: 0, held: 0 }
  for (const item of queue.value) {
    const name = String(item.queue_name || '').toLowerCase()
    if (name === 'active') counts.active += 1
    else if (name === 'deferred') counts.deferred += 1
    else if (name === 'hold' || name === 'held') counts.held += 1
  }
  return counts
})

const stackHealthy = computed(() => {
  const services = status.value?.services || {}
  return ['postfix', 'dovecot'].every((key) => services[key] === 'active')
})

const healthItems = computed(() => {
  const items: { level: 'ok' | 'warn' | 'error' | 'info'; title: string; detail: string }[] = []
  for (const card of serviceCards.value) {
    if (card.state === 'failed' || card.state === 'inactive') {
      items.push({
        level: 'error',
        title: `${card.label} is ${stateLabel(card.state).toLowerCase()}`,
        detail: 'Service is stopped. Click restart or check service daemon logs.',
      })
    }
  }
  if (!domains.value.length) {
    items.push({ level: 'warn', title: 'No mail domains', detail: 'Add a domain to automatically generate DKIM keys and DNS records.' })
  } else {
    if (!mailboxes.value.length) {
      items.push({ level: 'warn', title: 'No mailboxes created', detail: 'Create at least one mailbox so your domain can receive mail.' })
    }
    const relayBroken = domains.value.filter((d) => d.outbound_mode === 'relay' && !d.relay_host)
    if (relayBroken.length) {
      items.push({ level: 'error', title: 'Relay host missing', detail: `${relayBroken.map((d) => d.domain).join(', ')} configured for relay mode without a host.` })
    }
  }
  if (status.value?.public_ip === '127.0.0.1') {
    items.push({ level: 'warn', title: 'Loopback IP detected', detail: 'Public IP is 127.0.0.1. Ensure DNS A records point to your public IP.' })
  }
  if (egress.value) {
    if (!egress.value.port_25_egress_reachable) {
      items.push({ level: 'warn', title: 'Outbound Port 25 Blocked', detail: 'Your hosting provider blocks port 25. Configure an SMTP Relay under Domains → Outbound Route.' })
    }
    if (!egress.value.ptr_matches_hostname) {
      items.push({ level: 'warn', title: 'PTR record mismatch', detail: `Reverse DNS for ${egress.value.public_ip} does not match hostname ${egress.value.hostname}.` })
    }
  }
  if (!items.length) {
    items.push({ level: 'ok', title: 'Mail stack is healthy', detail: 'Postfix, Dovecot, OpenDKIM, and Rspamd are running cleanly.' })
  }
  return items
})

function calcQuotaPercent(usedMb: number, quotaMb: number): number {
  if (!quotaMb) return 0
  return Math.round(((usedMb || 0) / quotaMb) * 100)
}

function quotaBarColor(percent: number): string {
  if (percent >= 90) return 'bg-rose-500'
  if (percent >= 75) return 'bg-amber-500'
  return 'bg-emerald-500'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [st, ds, mb, al, cfg] = await Promise.all([
      apiFetch<any>('/mail/status'),
      apiFetch<any[]>('/mail/domains'),
      apiFetch<any[]>('/mail/mailboxes'),
      apiFetch<any[]>('/mail/aliases'),
      apiFetch<any>('/mail/config').catch(() => null),
    ])
    status.value = st
    domains.value = ds
    mailboxes.value = mb
    aliases.value = al
    if (cfg) {
      serverConfig.value = cfg
      configEditForm.max_message_size_mb = cfg.max_message_size_mb || 25
      configEditForm.tls_security_level = cfg.tls_security_level || 'may'
      configEditForm.webmail_url = cfg.webmail_url || '/webmail'
    }
    if (!newMbox.mail_domain_id && ds.length) newMbox.mail_domain_id = ds[0].id
    if (!newAlias.mail_domain_id && ds.length) newAlias.mail_domain_id = ds[0].id
    if (!testEmailForm.sender && mb.length) testEmailForm.sender = mb[0].email
  } catch (e: any) {
    error.value = e?.message || 'Failed to load mail server data'
  } finally {
    loading.value = false
  }
}

async function loadStatus() {
  try {
    status.value = await apiFetch<any>('/mail/status')
    notify('Service status refreshed')
  } catch (e: any) {
    fail(e)
  }
}

async function refreshAll() {
  await load()
  if (activeSection.value === 'queue') await loadQueue()
  if (activeSection.value === 'logs') await loadLogs()
  if (activeSection.value === 'test' || activeSection.value === 'overview') await runEgress()
}

function setSection(section: Section) {
  activeSection.value = section
  if (section === 'queue') loadQueue()
  if (section === 'logs') loadLogs()
  if (section === 'test' && !egress.value) runEgress()
}

function filterByDomain(domainId: number) {
  mailboxDomainFilter.value = domainId
  activeSection.value = 'mailboxes'
}

function notify(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3500)
}

function fail(e: any) {
  error.value = e?.message || 'Request failed'
}

function domainName(id: number) {
  return domainById.value[id]?.domain || '—'
}

function stateLabel(state: string) {
  return (
    {
      active: 'Running',
      inactive: 'Stopped',
      failed: 'Failed',
      activating: 'Starting',
      deactivating: 'Stopping',
      unknown: 'Unknown',
    } as Record<string, string>
  )[state] || state
}

function stateDot(state: string) {
  if (state === 'active') return 'bg-emerald-500'
  if (state === 'failed' || state === 'inactive') return 'bg-rose-500'
  if (state === 'activating' || state === 'deactivating') return 'bg-amber-500'
  return 'bg-slate-400'
}

function stateText(state: string) {
  if (state === 'active') return 'text-emerald-700'
  if (state === 'failed' || state === 'inactive') return 'text-rose-700'
  if (state === 'activating' || state === 'deactivating') return 'text-amber-700'
  return 'text-slate-500'
}

function healthIcon(level: string) {
  if (level === 'ok') return CheckCircle2
  if (level === 'error') return XCircle
  if (level === 'warn') return AlertTriangle
  return Info
}

function healthIconClass(level: string) {
  if (level === 'ok') return 'text-emerald-600'
  if (level === 'error') return 'text-rose-600'
  if (level === 'warn') return 'text-amber-600'
  return 'text-sky-600'
}

function formatEpoch(value: any) {
  const n = Number(value)
  if (!n) return '—'
  const date = new Date(n * 1000)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

function formatSize(bytes: any) {
  const n = Number(bytes)
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function recipientsOf(item: any) {
  const list = item?.recipients
  if (!Array.isArray(list) || !list.length) return '—'
  return list.map((r: any) => r.address || r).join(', ')
}

function queueStateClass(state: string) {
  const name = String(state || '').toLowerCase()
  if (name === 'active') return 'bg-emerald-50 text-emerald-700'
  if (name === 'deferred') return 'bg-amber-50 text-amber-700'
  if (name === 'hold' || name === 'held') return 'bg-slate-100 text-slate-700'
  return 'bg-slate-100 text-slate-600'
}

function recKey(rec: any) {
  return `${rec.type}:${rec.name}`
}

function dnsCheckFor(rec: any) {
  const checks = dnsReport.value?.live_propagation || {}
  if (rec.type === 'MX') return checks.mx
  if (rec.type === 'A') return checks.a
  if (rec.type === 'TXT' && rec.name === '@') return checks.spf
  if (rec.type === 'TXT' && String(rec.name).includes('_domainkey')) return checks.dkim
  if (rec.type === 'TXT' && rec.name === '_dmarc') return checks.dmarc
  return null
}

function generatePassword() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*'
  const bytes = new Uint32Array(20)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join('')
}

async function copyText(text: string, key: string) {
  let ok = false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      ok = true
    }
  } catch {
    ok = false
  }
  if (!ok) {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(ta)
  }
  if (ok) {
    copiedKey.value = key
    window.setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = ''
    }, 1500)
  }
}

async function createDomain() {
  if (!newDomain.domain.trim()) {
    error.value = 'Enter a valid mail domain'
    return
  }
  busy.value = 'domain'
  error.value = ''
  try {
    await apiFetch('/mail/domains', {
      method: 'POST',
      body: { domain: newDomain.domain.trim(), dkim_selector: newDomain.dkim_selector.trim() || 'default' },
    })
    showDomainModal.value = false
    newDomain.domain = ''
    await load()
    notify('Mail domain created. Verify DNS records to start receiving mail.')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function deleteDomain(domain: any) {
  if (!window.confirm(`Delete domain ${domain.domain}? All associated inboxes and aliases will be permanently removed.`)) return
  busy.value = 'domain'
  try {
    await apiFetch(`/mail/domains/${domain.id}`, { method: 'DELETE' })
    await load()
    notify(`Mail domain ${domain.domain} deleted`)
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

function openCreateMailbox(domainId?: number) {
  newMbox.mail_domain_id = domainId || domains.value[0]?.id || 0
  newMbox.local_part = ''
  newMbox.password = ''
  newMbox.quota_mb = 1024
  showNewPassword.value = false
  showMboxModal.value = true
}

async function createMailbox() {
  if (!newMbox.mail_domain_id || !newMbox.local_part.trim() || !newMbox.password) {
    error.value = 'Please provide domain, username, and password'
    return
  }
  busy.value = 'mailbox'
  error.value = ''
  try {
    await apiFetch('/mail/mailboxes', {
      method: 'POST',
      body: {
        mail_domain_id: newMbox.mail_domain_id,
        local_part: newMbox.local_part.trim(),
        password: newMbox.password,
        quota_mb: Number(newMbox.quota_mb),
      },
    })
    showMboxModal.value = false
    await load()
    notify('Mailbox created successfully')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

function openEditMailbox(mailbox: any) {
  editMbox.id = mailbox.id
  editMbox.email = mailbox.email
  editMbox.password = ''
  editMbox.quota_mb = mailbox.quota_mb
  editMbox.is_active = mailbox.is_active
  showEditPassword.value = false
  showEditMboxModal.value = true
}

async function saveMailbox() {
  busy.value = 'mailbox'
  error.value = ''
  try {
    await apiFetch(`/mail/mailboxes/${editMbox.id}`, {
      method: 'PUT',
      body: {
        quota_mb: Number(editMbox.quota_mb),
        is_active: editMbox.is_active,
        ...(editMbox.password ? { password: editMbox.password } : {}),
      },
    })
    showEditMboxModal.value = false
    await load()
    notify('Mailbox updated successfully')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function toggleMailbox(mailbox: any) {
  try {
    await apiFetch(`/mail/mailboxes/${mailbox.id}`, { method: 'PUT', body: { is_active: !mailbox.is_active } })
    await load()
    notify(`${mailbox.email} ${mailbox.is_active ? 'disabled' : 'enabled'}`)
  } catch (e: any) {
    fail(e)
  }
}

async function deleteMailbox(mailbox: any) {
  if (!window.confirm(`Delete mailbox ${mailbox.email}? Maildir files on disk will be preserved.`)) return
  try {
    await apiFetch(`/mail/mailboxes/${mailbox.id}`, { method: 'DELETE' })
    await load()
    notify('Mailbox deleted')
  } catch (e: any) {
    fail(e)
  }
}

async function openClientConfigModal(mailbox: any) {
  clientConfigData.value = null
  showClientModal.value = true
  try {
    const data = await apiFetch<any>(`/mail/client-config?email=${encodeURIComponent(mailbox.email)}`)
    clientConfigData.value = data
  } catch (e: any) {
    clientConfigData.value = {
      email: mailbox.email,
      mail_host: mailHost.value,
    }
  }
}

function openAliasModal() {
  newAlias.mail_domain_id = domains.value[0]?.id || 0
  newAlias.source_local = ''
  newAlias.destination_email = ''
  showAliasModal.value = true
}

async function createAlias() {
  const domain = domainById.value[newAlias.mail_domain_id]
  if (!domain || !newAlias.source_local.trim() || !newAlias.destination_email.trim()) {
    error.value = 'Choose domain, source username, and destination address'
    return
  }
  busy.value = 'alias'
  error.value = ''
  try {
    await apiFetch('/mail/aliases', {
      method: 'POST',
      body: {
        mail_domain_id: newAlias.mail_domain_id,
        source_email: `${newAlias.source_local.trim()}@${domain.domain}`,
        destination_email: newAlias.destination_email.trim(),
      },
    })
    showAliasModal.value = false
    await load()
    notify('Forwarding alias created')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function deleteAlias(alias: any) {
  if (!window.confirm(`Delete alias ${alias.source_email} → ${alias.destination_email}?`)) return
  try {
    await apiFetch(`/mail/aliases/${alias.id}`, { method: 'DELETE' })
    await load()
    notify('Alias deleted')
  } catch (e: any) {
    fail(e)
  }
}

function openRoute(domain: any) {
  routeForm.id = domain.id
  routeForm.domain = domain.domain
  routeForm.outbound_mode = domain.outbound_mode || 'direct'
  routeForm.relay_host = domain.relay_host || ''
  routeForm.relay_port = domain.relay_port || 587
  routeForm.relay_username = domain.relay_username || ''
  routeForm.relay_password = ''
  showRouteModal.value = true
}

async function saveRoute() {
  const relay = routeForm.outbound_mode === 'relay'
  if (relay && !routeForm.relay_host.trim()) {
    error.value = 'Relay host is required for relay mode'
    return
  }
  busy.value = 'route'
  error.value = ''
  try {
    await apiFetch(`/mail/domains/${routeForm.id}/outbound-route`, {
      method: 'PUT',
      body: {
        outbound_mode: routeForm.outbound_mode,
        relay_host: relay ? routeForm.relay_host.trim() : null,
        relay_port: Number(routeForm.relay_port) || 587,
        relay_username: relay ? routeForm.relay_username.trim() || null : null,
        ...(routeForm.relay_password ? { relay_password: routeForm.relay_password } : {}),
      },
    })
    showRouteModal.value = false
    await load()
    notify('Outbound route configuration saved')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

function openCatchall(domain: any) {
  catchallForm.id = domain.id
  catchallForm.domain = domain.domain
  catchallForm.catchall_address = domain.catchall_address || ''
  showCatchallModal.value = true
}

async function saveCatchall() {
  busy.value = 'catchall'
  error.value = ''
  try {
    await apiFetch(`/mail/domains/${catchallForm.id}/catchall`, {
      method: 'PUT',
      body: { catchall_address: catchallForm.catchall_address.trim() || null },
    })
    showCatchallModal.value = false
    await load()
    notify('Catch-all settings saved')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function openDns(domain: any) {
  dnsDomain.value = domain
  dnsReport.value = null
  showDnsModal.value = true
  dnsLoading.value = true
  try {
    dnsReport.value = await apiFetch(`/mail/domains/${domain.id}/dns-readiness`)
  } catch (e: any) {
    fail(e)
  } finally {
    dnsLoading.value = false
  }
}

async function syncDnsToZone(domain: any) {
  busy.value = 'sync-dns'
  try {
    const res = await apiFetch<any>(`/mail/domains/${domain.id}/sync-dns`, { method: 'POST' })
    if (res.synced) {
      notify(res.message || 'DNS records synced to NexoPanel DNS Zone')
      await openDns(domain)
    } else {
      error.value = res.message || 'DNS Zone not found for this domain'
    }
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function controlService(service: string, action: string) {
  busy.value = `svc-${service}`
  try {
    const res = await apiFetch<any>(`/mail/services/${service}/${action}`, { method: 'POST' })
    if (res.ok) {
      notify(`${service} ${action} successful`)
      await loadStatus()
    } else {
      error.value = `${service} ${action} failed: ${res.output || 'Unknown error'}`
    }
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function saveServerConfig() {
  busy.value = 'config'
  try {
    await apiFetch('/mail/config', {
      method: 'PUT',
      body: {
        max_message_size_mb: Number(configEditForm.max_message_size_mb),
        tls_security_level: configEditForm.tls_security_level,
        webmail_url: configEditForm.webmail_url.trim() || '/webmail',
      },
    })
    notify('Server configuration updated')
    await load()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

function openTestEmailModal() {
  activeSection.value = 'test'
  if (!testEmailForm.sender && mailboxes.value.length) {
    testEmailForm.sender = mailboxes.value[0].email
  }
}

function openSendTestFrom(mailbox: any) {
  testEmailForm.sender = mailbox.email
  activeSection.value = 'test'
}

async function sendTestEmail() {
  if (!testEmailForm.sender || !testEmailForm.recipient.trim()) {
    error.value = 'Please provide sender and recipient email addresses'
    return
  }
  busy.value = 'test-email'
  testEmailResult.value = null
  try {
    const res = await apiFetch<any>('/mail/test-email', {
      method: 'POST',
      body: {
        sender: testEmailForm.sender.trim(),
        recipient: testEmailForm.recipient.trim(),
        subject: testEmailForm.subject.trim(),
        body: testEmailForm.body.trim(),
      },
    })
    testEmailResult.value = res
    if (res.success) {
      notify('Test email dispatched to MTA')
    } else {
      error.value = res.error || 'Failed to dispatch test message'
    }
  } catch (e: any) {
    fail(e)
    testEmailResult.value = { success: false, error: e?.message || 'Request failed' }
  } finally {
    busy.value = ''
  }
}

async function loadQueue() {
  queueLoading.value = true
  queueError.value = ''
  try {
    const res = await apiFetch<any>('/mail/queue')
    queue.value = res.queue || []
    queueError.value = res.raw_error || ''
  } catch (e: any) {
    queueError.value = e?.message || 'Failed to load queue'
  } finally {
    queueLoading.value = false
  }
}

async function flushQueue() {
  busy.value = 'queue'
  try {
    await apiFetch('/mail/queue/flush', { method: 'POST' })
    await loadQueue()
    notify('Postfix queue flush requested')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function queueAction(action: 'hold' | 'release' | 'requeue' | 'delete', item: any) {
  const label = action.charAt(0).toUpperCase() + action.slice(1)
  if (action === 'delete' && !window.confirm(`Delete queue item ${item.queue_id}?`)) return
  try {
    await apiFetch(`/mail/queue/${action}?queue_id=${encodeURIComponent(item.queue_id)}`, { method: 'POST' })
    await loadQueue()
    notify(`Queue item ${item.queue_id}: ${label} executed`)
  } catch (e: any) {
    fail(e)
  }
}

async function queueBulkAction(type: 'requeue' | 'delete-deferred') {
  busy.value = 'queue'
  try {
    if (type === 'requeue') {
      await apiFetch('/mail/queue/requeue?queue_id=ALL', { method: 'POST' })
      notify('Re-queued all deferred messages')
    } else {
      if (!window.confirm('Delete all deferred queue messages?')) return
      await apiFetch('/mail/queue/delete?queue_id=ALL_DEFERRED', { method: 'POST' })
      notify('Deleted all deferred queue messages')
    }
    await loadQueue()
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function loadLogs() {
  logsLoading.value = true
  logError.value = ''
  try {
    const res = await apiFetch<any>(`/mail/logs?lines=${logTail.value}`)
    logs.value = res.lines || []
    logSource.value = res.source || null
    logError.value = res.lines?.length ? '' : res.error || ''
  } catch (e: any) {
    logError.value = e?.message || 'Failed to read mail logs'
  } finally {
    logsLoading.value = false
  }
}

async function runEgress() {
  egressLoading.value = true
  try {
    egress.value = await apiFetch('/mail/diagnostics/egress')
  } catch (e: any) {
    fail(e)
  } finally {
    egressLoading.value = false
  }
}

onMounted(load)
</script>
