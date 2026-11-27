<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <aside class="w-44 shrink-0 border-r border-slate-200 bg-slate-50/60 py-3">
      <div class="px-4 pb-3 mb-2 border-b border-slate-200">
        <div class="flex items-center gap-2 font-bold text-slate-900">
          <Mail class="w-4 h-4 text-emerald-600" />
          <span>Mail Server</span>
        </div>
        <p class="text-[10px] text-slate-500 mt-0.5">SMTP · IMAP · DKIM</p>
      </div>
      <button
        v-for="item in sections"
        :key="item.key"
        @click="setSection(item.key)"
        :class="activeSection === item.key ? 'text-emerald-700 bg-emerald-50 border-r-2 border-emerald-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
        class="w-full flex items-center gap-2 text-left px-4 py-2.5 transition-colors"
      >
        <component :is="item.icon" class="w-3.5 h-3.5" />
        <span>{{ item.label }}</span>
        <span v-if="item.key === 'queue' && queue.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold">{{ queue.length }}</span>
      </button>
      <div class="mt-4 mx-3 rounded border border-slate-200 bg-white p-2.5 space-y-1">
        <div class="flex items-center justify-between">
          <span class="text-[10px] text-slate-500">Mail host</span>
          <span class="w-2 h-2 rounded-full" :class="stackHealthy ? 'bg-emerald-500' : 'bg-amber-500'"></span>
        </div>
        <div class="font-mono text-[10px] text-slate-700 break-all">{{ mailHost }}</div>
        <div class="font-mono text-[10px] text-slate-500">{{ status?.public_ip || 'IP pending' }}</div>
      </div>
    </aside>

    <div class="flex-1 p-5 flex flex-col min-w-0">
      <div class="flex flex-wrap items-start justify-between gap-3 pb-3 mb-4 border-b border-slate-200">
        <div>
          <h1 class="text-sm font-bold text-slate-900">Mail Server Console</h1>
          <p class="text-[11px] text-slate-500">Configure domains, manage inboxes and aliases, route outbound mail and verify deliverability.</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button @click="refreshAll" :disabled="loading" class="np-btn-secondary">
            <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
          <button @click="openCreateMailbox()" class="np-btn-secondary">
            <MailPlus class="w-3.5 h-3.5" />
            <span>New Mailbox</span>
          </button>
          <button @click="showDomainModal = true" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Domain</span>
          </button>
        </div>
      </div>

      <div v-if="error" class="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><XCircle class="w-3.5 h-3.5 shrink-0" />{{ error }}</span>
        <button @click="error = ''" class="text-rose-500 hover:text-rose-700"><X class="w-3.5 h-3.5" /></button>
      </div>
      <div v-if="notice" class="mb-3 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-700 flex items-center justify-between gap-3">
        <span class="flex items-center gap-1.5"><CheckCircle2 class="w-3.5 h-3.5 shrink-0" />{{ notice }}</span>
        <button @click="notice = ''" class="text-emerald-500 hover:text-emerald-700"><X class="w-3.5 h-3.5" /></button>
      </div>

      <div v-if="activeSection === 'overview'" class="space-y-4">
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="card in serviceCards" :key="card.key" class="rounded border border-slate-200 bg-white p-3">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-slate-800">{{ card.label }}</span>
              <span class="w-2 h-2 rounded-full" :class="stateDot(card.state)"></span>
            </div>
            <div class="mt-1 flex items-center gap-1.5 text-[11px]" :class="stateText(card.state)">
              <Activity class="w-3 h-3" />
              <span>{{ stateLabel(card.state) }}</span>
            </div>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div v-for="stat in statCards" :key="stat.label" class="rounded border border-slate-200 bg-white p-3">
            <div class="text-[10px] uppercase tracking-wider text-slate-500">{{ stat.label }}</div>
            <div class="mt-1 text-xl font-bold text-slate-900">{{ stat.value }}</div>
            <div class="text-[10px] text-slate-500">{{ stat.hint }}</div>
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-3">
          <div class="xl:col-span-2 rounded border border-slate-200 bg-white">
            <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center gap-1.5">
              <ListChecks class="w-3.5 h-3.5 text-emerald-600" />
              <span>Readiness checklist</span>
            </div>
            <div class="divide-y divide-slate-100">
              <div v-for="(item, idx) in healthItems" :key="idx" class="px-3 py-2.5 flex items-start gap-2">
                <component :is="healthIcon(item.level)" class="w-3.5 h-3.5 mt-0.5 shrink-0" :class="healthIconClass(item.level)" />
                <div>
                  <div class="font-semibold text-slate-800">{{ item.title }}</div>
                  <div class="text-[11px] text-slate-500">{{ item.detail }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded border border-slate-200 bg-white">
            <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center gap-1.5">
              <Zap class="w-3.5 h-3.5 text-amber-500" />
              <span>Quick actions</span>
            </div>
            <div class="p-3 space-y-2">
              <button @click="setSection('domains')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50">
                <span class="flex items-center gap-2"><Server class="w-3.5 h-3.5 text-slate-500" />Manage domains</span>
                <ArrowRight class="w-3.5 h-3.5 text-slate-400" />
              </button>
              <button @click="setSection('mailboxes')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50">
                <span class="flex items-center gap-2"><Inbox class="w-3.5 h-3.5 text-slate-500" />Manage inboxes</span>
                <ArrowRight class="w-3.5 h-3.5 text-slate-400" />
              </button>
              <button @click="setSection('queue')" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50">
                <span class="flex items-center gap-2"><Send class="w-3.5 h-3.5 text-slate-500" />Postfix queue</span>
                <span class="text-[10px] text-slate-500">{{ queue.length }} items</span>
              </button>
              <button @click="setSection('diagnostics'); runEgress()" class="w-full flex items-center justify-between rounded border border-slate-200 px-2.5 py-2 hover:bg-slate-50">
                <span class="flex items-center gap-2"><ShieldCheck class="w-3.5 h-3.5 text-slate-500" />Run deliverability test</span>
                <ArrowRight class="w-3.5 h-3.5 text-slate-400" />
              </button>
              <button @click="flushQueue" :disabled="busy === 'queue'" class="w-full flex items-center justify-between rounded border border-amber-200 bg-amber-50 px-2.5 py-2 text-amber-800 hover:bg-amber-100 disabled:opacity-50">
                <span class="flex items-center gap-2"><RefreshCw class="w-3.5 h-3.5" />Flush mail queue</span>
                <span class="text-[10px]">postqueue -f</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'domains'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="relative">
            <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
            <input v-model="domainSearch" placeholder="Search domains" class="np-input w-64 pl-8" />
          </div>
          <button @click="showDomainModal = true" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Mail Domain</span>
          </button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Domain</th>
                <th>Mailboxes</th>
                <th>Aliases</th>
                <th>Outbound</th>
                <th>Catch-all</th>
                <th>DKIM</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in filteredDomains" :key="d.id" class="hover:bg-slate-50/70">
                <td>
                  <div class="font-semibold text-slate-900">{{ d.domain }}</div>
                  <div class="text-[10px] text-slate-500">Created domain</div>
                </td>
                <td>{{ d.mailbox_count }}</td>
                <td>{{ d.alias_count }}</td>
                <td>
                  <span v-if="d.outbound_mode === 'relay'" class="px-2 py-0.5 rounded bg-sky-50 text-sky-700 text-[10px] font-medium">Relay</span>
                  <span v-else class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-medium">Direct</span>
                  <div v-if="d.outbound_mode === 'relay'" class="font-mono text-[10px] text-slate-500 mt-0.5">{{ d.relay_host || 'host missing' }}:{{ d.relay_port || 587 }}</div>
                </td>
                <td>
                  <span v-if="d.catchall_address" class="font-mono text-[10px] text-slate-700">{{ d.catchall_address }}</span>
                  <span v-else class="text-slate-400 text-[10px]">Disabled</span>
                </td>
                <td>
                  <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700">{{ d.dkim_selector }}</span>
                </td>
                <td class="text-right">
                  <div class="inline-flex flex-wrap justify-end gap-1">
                    <button @click="openDns(d)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">DNS</button>
                    <button @click="openRoute(d)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">Route</button>
                    <button @click="openCatchall(d)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">Catch-all</button>
                    <button @click="openCreateMailbox(d.id)" class="px-2 py-1 rounded border border-emerald-600 text-emerald-700 bg-emerald-50/50 hover:bg-emerald-50">+ Mailbox</button>
                    <button @click="deleteDomain(d)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredDomains.length">
                <td colspan="7" class="text-center py-8 text-slate-500">
                  <Server class="w-6 h-6 mx-auto mb-1 text-slate-300" />
                  No mail domains yet. Add a domain to start receiving mail.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="activeSection === 'mailboxes'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <div class="relative">
              <Search class="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
              <input v-model="mailboxSearch" placeholder="Search inboxes" class="np-input w-56 pl-8" />
            </div>
            <select v-model.number="mailboxDomainFilter" class="np-input w-48">
              <option :value="0">All domains</option>
              <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
            </select>
          </div>
          <button @click="openCreateMailbox()" :disabled="!domains.length" class="np-btn-primary">
            <MailPlus class="w-3.5 h-3.5" />
            <span>Create Mailbox</span>
          </button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Email address</th>
                <th>Domain</th>
                <th>Quota</th>
                <th>Status</th>
                <th>Created</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in filteredMailboxes" :key="m.id" class="hover:bg-slate-50/70">
                <td class="font-mono text-slate-900">{{ m.email }}</td>
                <td>{{ domainName(m.mail_domain_id) }}</td>
                <td>{{ m.quota_mb }} MB</td>
                <td>
                  <span v-if="m.is_active" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-medium">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Active
                  </span>
                  <span v-else class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-medium">
                    <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>Disabled
                  </span>
                </td>
                <td class="text-slate-500">{{ m.created_at ? formatDate(m.created_at) : '—' }}</td>
                <td class="text-right">
                  <div class="inline-flex flex-wrap justify-end gap-1">
                    <button @click="openEditMailbox(m)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">Edit</button>
                    <button @click="toggleMailbox(m)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">{{ m.is_active ? 'Disable' : 'Enable' }}</button>
                    <button @click="deleteMailbox(m)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredMailboxes.length">
                <td colspan="6" class="text-center py-8 text-slate-500">
                  <Inbox class="w-6 h-6 mx-auto mb-1 text-slate-300" />
                  No mailboxes found. Create an inbox for a domain.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="activeSection === 'aliases'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-[11px] text-slate-500">Forward a source address to another mailbox. Catch-all addresses are configured per domain.</div>
          <button @click="openAliasModal" :disabled="!domains.length" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Add Alias</span>
          </button>
        </div>
        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr><th>Source address</th><th>Destination</th><th>Domain</th><th class="text-right">Actions</th></tr>
            </thead>
            <tbody>
              <tr v-for="a in aliases" :key="a.id" class="hover:bg-slate-50/70">
                <td class="font-mono">{{ a.source_email }}</td>
                <td class="font-mono">{{ a.destination_email }}</td>
                <td>{{ domainName(a.mail_domain_id) }}</td>
                <td class="text-right">
                  <button @click="deleteAlias(a)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50">Delete</button>
                </td>
              </tr>
              <tr v-if="!aliases.length">
                <td colspan="4" class="text-center py-8 text-slate-500">
                  <AtSign class="w-6 h-6 mx-auto mb-1 text-slate-300" />
                  No aliases configured.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="activeSection === 'queue'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2 text-[11px]">
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-700">Total: {{ queueCounts.total }}</span>
            <span class="px-2 py-1 rounded bg-emerald-50 text-emerald-700">Active: {{ queueCounts.active }}</span>
            <span class="px-2 py-1 rounded bg-amber-50 text-amber-700">Deferred: {{ queueCounts.deferred }}</span>
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-600">Held: {{ queueCounts.held }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button @click="loadQueue" :disabled="queueLoading" class="np-btn-secondary">
              <RefreshCw :class="{ 'animate-spin': queueLoading }" class="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
            <button @click="flushQueue" :disabled="busy === 'queue'" class="np-btn-primary">
              <Send class="w-3.5 h-3.5" />
              <span>Flush Queue</span>
            </button>
          </div>
        </div>

        <div v-if="queueError" class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">{{ queueError }}</div>

        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr><th>Queue ID</th><th>State</th><th>Size</th><th>Arrival</th><th>Sender</th><th>Recipients</th><th class="text-right">Actions</th></tr>
            </thead>
            <tbody>
              <tr v-for="q in queue" :key="q.queue_id" class="hover:bg-slate-50/70">
                <td class="font-mono text-[10px]">{{ q.queue_id }}</td>
                <td>
                  <span class="px-2 py-0.5 rounded text-[10px] font-medium" :class="queueStateClass(q.queue_name)">{{ q.queue_name || 'unknown' }}</span>
                </td>
                <td>{{ formatSize(q.message_size) }}</td>
                <td class="text-slate-500">{{ formatEpoch(q.arrival_time) }}</td>
                <td class="font-mono text-[10px] break-all">{{ q.sender || '—' }}</td>
                <td class="font-mono text-[10px] break-all">{{ recipientsOf(q) }}</td>
                <td class="text-right">
                  <div class="inline-flex gap-1">
                    <button @click="queueAction('hold', q)" class="px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50">Hold</button>
                    <button @click="queueAction('delete', q)" class="px-2 py-1 rounded border border-rose-200 text-rose-600 hover:bg-rose-50">Delete</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!queue.length">
                <td colspan="7" class="text-center py-8 text-slate-500">
                  <CheckCircle2 class="w-6 h-6 mx-auto mb-1 text-emerald-400" />
                  Queue is empty.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="activeSection === 'logs'" class="space-y-3 flex-1 flex flex-col">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <select v-model.number="logTail" @change="loadLogs" class="np-input w-32">
              <option :value="100">Last 100</option>
              <option :value="200">Last 200</option>
              <option :value="500">Last 500</option>
              <option :value="1000">Last 1000</option>
            </select>
            <span v-if="logSource" class="font-mono text-[10px] text-slate-500">{{ logSource }}</span>
          </div>
          <button @click="loadLogs" :disabled="logsLoading" class="np-btn-secondary">
            <RefreshCw :class="{ 'animate-spin': logsLoading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
        <div v-if="logError" class="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">{{ logError }}</div>
        <pre class="flex-1 min-h-[24rem] overflow-auto rounded border border-slate-800 bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-200 font-mono">{{ logs.length ? logs.join('\n') : 'No log lines available.' }}</pre>
      </div>

      <div v-else-if="activeSection === 'diagnostics'" class="space-y-4">
        <div class="grid gap-4 xl:grid-cols-2">
          <div class="rounded border border-slate-200 bg-white">
            <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center justify-between">
              <span class="flex items-center gap-1.5"><ShieldCheck class="w-3.5 h-3.5 text-emerald-600" />Outbound egress</span>
              <button @click="runEgress" :disabled="egressLoading" class="np-btn-secondary">
                <RefreshCw :class="{ 'animate-spin': egressLoading }" class="w-3.5 h-3.5" />
                <span>{{ egress ? 'Re-test' : 'Run test' }}</span>
              </button>
            </div>
            <div class="p-3 space-y-2 text-[11px]">
              <div class="flex items-center justify-between">
                <span class="text-slate-500">Mail hostname</span>
                <span class="font-mono text-slate-800">{{ egress?.hostname || mailHost }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-slate-500">Public IP</span>
                <span class="font-mono text-slate-800">{{ egress?.public_ip || status?.public_ip || '—' }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-slate-500">Port 25 egress</span>
                <span v-if="egress" class="inline-flex items-center gap-1 font-medium" :class="egress.port_25_egress_reachable ? 'text-emerald-700' : 'text-rose-700'">
                  <component :is="egress.port_25_egress_reachable ? CheckCircle2 : XCircle" class="w-3.5 h-3.5" />
                  {{ egress.port_25_egress_reachable ? 'Reachable' : 'Blocked' }}
                </span>
                <span v-else class="text-slate-400">Not tested</span>
              </div>
              <div class="flex items-start justify-between gap-3">
                <span class="text-slate-500 shrink-0">PTR records</span>
                <span class="font-mono text-slate-800 text-right break-all">{{ egress?.ptr_records?.length ? egress.ptr_records.join(', ') : '—' }}</span>
              </div>
              <div v-if="egress" class="rounded border border-slate-200 bg-slate-50 p-2 space-y-1">
                <div v-for="(rec, i) in egress.recommendations" :key="i" class="flex items-start gap-1.5 text-slate-600">
                  <Info class="w-3.5 h-3.5 text-sky-500 mt-0.5 shrink-0" />
                  <span>{{ rec }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="rounded border border-slate-200 bg-white">
            <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center gap-1.5">
              <Terminal class="w-3.5 h-3.5 text-slate-600" />Useful commands
            </div>
            <div class="p-3 space-y-2">
              <div v-for="cmd in commands" :key="cmd.cmd" class="rounded border border-slate-200 p-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-semibold text-slate-700">{{ cmd.label }}</span>
                  <button @click="copyText(cmd.cmd, cmd.cmd)" class="text-emerald-700 hover:underline flex items-center gap-1">
                    <Copy class="w-3 h-3" />{{ copiedKey === cmd.cmd ? 'Copied' : 'Copy' }}
                  </button>
                </div>
                <div class="font-mono text-[10px] text-slate-500 break-all mt-0.5">{{ cmd.cmd }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="rounded border border-slate-200 bg-white">
          <div class="px-3 py-2 border-b border-slate-200 font-semibold text-slate-800 flex items-center gap-1.5">
            <ShieldCheck class="w-3.5 h-3.5 text-emerald-600" />DNS readiness by domain
          </div>
          <div class="divide-y divide-slate-100">
            <div v-for="d in domains" :key="d.id" class="px-3 py-2 flex items-center justify-between gap-3">
              <div>
                <div class="font-semibold text-slate-800">{{ d.domain }}</div>
                <div class="text-[10px] text-slate-500">DKIM selector {{ d.dkim_selector }} · {{ d.mailbox_count }} mailbox(es)</div>
              </div>
              <button @click="openDns(d)" class="np-btn-secondary">Inspect DNS</button>
            </div>
            <div v-if="!domains.length" class="px-3 py-6 text-center text-slate-500">Add a mail domain to inspect DNS records.</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showDomainModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showDomainModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Add Mail Domain</h3>
          <button @click="showDomainModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Domain</label>
        <input v-model="newDomain.domain" placeholder="example.com" class="np-input" />
        <label class="block text-[11px] font-medium text-slate-600">DKIM selector</label>
        <input v-model="newDomain.dkim_selector" placeholder="default" class="np-input" />
        <p class="text-[10px] text-slate-500">A 2048-bit DKIM keypair is generated automatically. Publish the DNS records from the domain's DNS readiness panel.</p>
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showDomainModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createDomain" :disabled="busy === 'domain'" class="np-btn-primary">{{ busy === 'domain' ? 'Creating…' : 'Create Domain' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showMboxModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showMboxModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Create Mailbox</h3>
          <button @click="showMboxModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Address</label>
        <div class="flex items-center gap-1.5">
          <input v-model="newMbox.local_part" placeholder="info" class="np-input" />
          <span class="text-slate-400">@</span>
          <select v-model.number="newMbox.mail_domain_id" class="np-input">
            <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
          </select>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Password</label>
        <div class="flex items-center gap-1.5">
          <input v-model="newMbox.password" :type="showNewPassword ? 'text' : 'password'" placeholder="Minimum 8 characters" class="np-input" />
          <button @click="showNewPassword = !showNewPassword" class="np-btn-secondary !px-2" :title="showNewPassword ? 'Hide' : 'Show'">
            <component :is="showNewPassword ? EyeOff : Eye" class="w-3.5 h-3.5" />
          </button>
          <button @click="newMbox.password = generatePassword()" class="np-btn-secondary !px-2" title="Generate password">Generate</button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Quota (MB)</label>
        <input v-model.number="newMbox.quota_mb" type="number" min="50" class="np-input" />
        <p class="text-[10px] text-slate-500">Inbox: IMAP {{ mailHost }}:993 (SSL) · SMTP {{ mailHost }}:587 (STARTTLS).</p>
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showMboxModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createMailbox" :disabled="busy === 'mailbox'" class="np-btn-primary">{{ busy === 'mailbox' ? 'Creating…' : 'Create Mailbox' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showEditMboxModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showEditMboxModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Edit Mailbox</h3>
          <button @click="showEditMboxModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <div class="rounded bg-slate-50 border border-slate-200 px-2.5 py-2 font-mono text-[11px] text-slate-700">{{ editMbox.email }}</div>
        <label class="block text-[11px] font-medium text-slate-600">Quota (MB)</label>
        <input v-model.number="editMbox.quota_mb" type="number" min="50" class="np-input" />
        <label class="flex items-center gap-2 text-[11px] text-slate-700">
          <input v-model="editMbox.is_active" type="checkbox" class="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500" />
          Mailbox active (allows IMAP/SMTP login)
        </label>
        <label class="block text-[11px] font-medium text-slate-600">New password (optional)</label>
        <div class="flex items-center gap-1.5">
          <input v-model="editMbox.password" :type="showEditPassword ? 'text' : 'password'" placeholder="Leave blank to keep current" class="np-input" />
          <button @click="showEditPassword = !showEditPassword" class="np-btn-secondary !px-2">
            <component :is="showEditPassword ? EyeOff : Eye" class="w-3.5 h-3.5" />
          </button>
          <button @click="editMbox.password = generatePassword()" class="np-btn-secondary !px-2">Generate</button>
        </div>
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showEditMboxModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveMailbox" :disabled="busy === 'mailbox'" class="np-btn-primary">{{ busy === 'mailbox' ? 'Saving…' : 'Save Changes' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showAliasModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showAliasModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Add Alias</h3>
          <button @click="showAliasModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Source address</label>
        <div class="flex items-center gap-1.5">
          <input v-model="newAlias.source_local" placeholder="sales" class="np-input" />
          <span class="text-slate-400">@</span>
          <select v-model.number="newAlias.mail_domain_id" class="np-input">
            <option v-for="d in domains" :key="d.id" :value="d.id">{{ d.domain }}</option>
          </select>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Forward to</label>
        <input v-model="newAlias.destination_email" placeholder="inbox@example.com" class="np-input" />
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showAliasModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createAlias" :disabled="busy === 'alias'" class="np-btn-primary">{{ busy === 'alias' ? 'Creating…' : 'Create Alias' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showRouteModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showRouteModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Outbound Route · {{ routeForm.domain }}</h3>
          <button @click="showRouteModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Mode</label>
        <select v-model="routeForm.outbound_mode" class="np-input">
          <option value="direct">Direct egress (send from this server)</option>
          <option value="relay">SMTP relay</option>
        </select>
        <template v-if="routeForm.outbound_mode === 'relay'">
          <label class="block text-[11px] font-medium text-slate-600">Relay host</label>
          <input v-model="routeForm.relay_host" placeholder="smtp.provider.com" class="np-input" />
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] font-medium text-slate-600">Port</label>
              <input v-model.number="routeForm.relay_port" type="number" min="1" max="65535" class="np-input" />
            </div>
            <div>
              <label class="block text-[11px] font-medium text-slate-600">Username</label>
              <input v-model="routeForm.relay_username" placeholder="apikey" class="np-input" />
            </div>
          </div>
          <label class="block text-[11px] font-medium text-slate-600">Password</label>
          <input v-model="routeForm.relay_password" type="password" placeholder="Leave blank to keep current" class="np-input" />
        </template>
        <p v-else class="text-[10px] text-slate-500">Direct mode requires outbound port 25. If your provider blocks port 25, switch to an SMTP relay.</p>
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showRouteModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveRoute" :disabled="busy === 'route'" class="np-btn-primary">{{ busy === 'route' ? 'Saving…' : 'Save Route' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showCatchallModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showCatchallModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Catch-all · {{ catchallForm.domain }}</h3>
          <button @click="showCatchallModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>
        <label class="block text-[11px] font-medium text-slate-600">Forward unknown recipients to</label>
        <input v-model="catchallForm.catchall_address" placeholder="catchall@example.com" class="np-input" />
        <p class="text-[10px] text-slate-500">Leave blank to disable catch-all. This creates a Postfix virtual alias for @{{ catchallForm.domain }}.</p>
        <div class="flex justify-end gap-2 pt-1">
          <button @click="showCatchallModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveCatchall" :disabled="busy === 'catchall'" class="np-btn-primary">{{ busy === 'catchall' ? 'Saving…' : 'Save Catch-all' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDnsModal" class="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto" @click.self="showDnsModal = false">
      <div class="bg-white rounded-lg p-5 w-full max-w-3xl space-y-3 my-6">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-bold text-slate-900">DNS Readiness · {{ dnsDomain?.domain }}</h3>
            <p class="text-[11px] text-slate-500">Publish these records at your DNS provider. Mail host: <span class="font-mono">{{ dnsReport?.mail_host || mailHost }}</span></p>
          </div>
          <button @click="showDnsModal = false" class="text-slate-400 hover:text-slate-700"><X class="w-4 h-4" /></button>
        </div>

        <div v-if="dnsLoading" class="py-10 text-center text-slate-500">Loading DNS readiness…</div>
        <template v-else-if="dnsReport">
          <div class="flex flex-wrap items-center gap-2 text-[11px]">
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-700">Mail host: <span class="font-mono">{{ dnsReport.mail_host }}</span></span>
            <span class="px-2 py-1 rounded bg-slate-100 text-slate-700">Public IP: <span class="font-mono">{{ dnsReport.public_ip }}</span></span>
            <span class="px-2 py-1 rounded" :class="dnsReport.live_checks_enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'">
              {{ dnsReport.live_checks_enabled ? 'Live propagation checks enabled' : 'Live checks disabled' }}
            </span>
          </div>

          <div class="space-y-2">
            <div v-for="rec in dnsReport.required_records" :key="recKey(rec)" class="rounded border border-slate-200 p-3 space-y-1">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <span class="px-1.5 py-0.5 rounded bg-slate-900 text-white font-mono text-[10px]">{{ rec.type }}</span>
                  <span class="font-mono text-[11px] text-slate-800">{{ rec.name }}</span>
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
                  <span v-else class="text-[10px] text-slate-400">Live checks off</span>
                  <button @click="copyText(rec.value, recKey(rec))" class="inline-flex items-center gap-1 text-emerald-700 hover:underline">
                    <Copy class="w-3 h-3" />{{ copiedKey === recKey(rec) ? 'Copied' : 'Copy' }}
                  </button>
                </div>
              </div>
              <div class="font-mono text-[11px] break-all text-slate-700 bg-slate-50 rounded p-2">{{ rec.value }}</div>
              <div class="text-[11px] text-slate-500">{{ rec.purpose }}</div>
              <div v-if="dnsReport.live_checks_enabled && dnsCheckFor(rec) && !dnsCheckFor(rec).propagated" class="rounded bg-amber-50 border border-amber-200 px-2 py-1.5 text-[11px] text-amber-800">
                {{ rec.fix }}
              </div>
              <div v-if="dnsCheckFor(rec)?.observed?.length" class="text-[10px] text-slate-500 font-mono break-all">
                Observed: {{ dnsCheckFor(rec).observed.join(' | ') }}
              </div>
            </div>
          </div>
        </template>
        <div v-else class="py-10 text-center text-rose-600">Unable to load DNS readiness.</div>

        <div class="flex justify-end">
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
  Search,
  Send,
  Server,
  ShieldCheck,
  Terminal,
  X,
  XCircle,
  Zap,
} from 'lucide-vue-next'

type Section = 'overview' | 'domains' | 'mailboxes' | 'aliases' | 'queue' | 'logs' | 'diagnostics'

const { apiFetch } = useApi()

const sections: { key: Section; label: string; icon: any }[] = [
  { key: 'overview', label: 'Overview', icon: Gauge },
  { key: 'domains', label: 'Domains', icon: Server },
  { key: 'mailboxes', label: 'Mailboxes', icon: Inbox },
  { key: 'aliases', label: 'Aliases', icon: AtSign },
  { key: 'queue', label: 'Queue', icon: Send },
  { key: 'logs', label: 'Logs', icon: FileText },
  { key: 'diagnostics', label: 'Diagnostics', icon: ShieldCheck },
]

const commands = [
  { label: 'Inspect Postfix queue', cmd: 'postqueue -p' },
  { label: 'Flush deferred queue', cmd: 'postsuper -d ALL deferred' },
  { label: 'Service status', cmd: 'systemctl status postfix dovecot opendkim rspamd --no-pager' },
  { label: 'Follow mail log', cmd: 'tail -f /var/log/mail.log' },
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
const queue = ref<any[]>([])
const queueError = ref('')
const queueLoading = ref(false)
const logs = ref<string[]>([])
const logSource = ref<string | null>(null)
const logError = ref('')
const logsLoading = ref(false)
const logTail = ref(100)
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

const domainById = computed(() => {
  const map: Record<number, any> = {}
  for (const d of domains.value) map[d.id] = d
  return map
})

const mailHost = computed(() => status.value?.hostname || egress.value?.hostname || 'mail server')

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

const serviceCards = computed(() => {
  const s = status.value?.services || {}
  return [
    { key: 'postfix', label: 'Postfix · SMTP', state: s.postfix || 'unknown' },
    { key: 'dovecot', label: 'Dovecot · IMAP/POP3', state: s.dovecot || 'unknown' },
    { key: 'opendkim', label: 'OpenDKIM · signing', state: s.opendkim || 'unknown' },
    { key: 'rspamd', label: 'Rspamd · filtering', state: s.rspamd || 'unknown' },
  ]
})

const statCards = computed(() => {
  const c = status.value?.counts || {}
  return [
    { label: 'Domains', value: c.domains ?? domains.value.length, hint: 'Mail domains configured' },
    { label: 'Mailboxes', value: c.mailboxes ?? mailboxes.value.length, hint: 'Inboxes provisioned' },
    { label: 'Active', value: c.active_mailboxes ?? mailboxes.value.filter((m) => m.is_active).length, hint: 'Login-enabled inboxes' },
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
      items.push({ level: 'error', title: `${card.label} is ${stateLabel(card.state).toLowerCase()}`, detail: 'Start the service from the Services page or restart the mail stack.' })
    }
  }
  if (!domains.value.length) {
    items.push({ level: 'warn', title: 'No mail domains', detail: 'Add a domain to generate DKIM keys and DNS records.' })
  } else {
    if (!mailboxes.value.length) {
      items.push({ level: 'warn', title: 'No mailboxes', detail: 'Create at least one inbox so the domain can receive mail.' })
    }
    const relayBroken = domains.value.filter((d) => d.outbound_mode === 'relay' && !d.relay_host)
    if (relayBroken.length) {
      items.push({ level: 'error', title: 'Relay host missing', detail: `${relayBroken.map((d) => d.domain).join(', ')} use relay mode without a host.` })
    }
    if (domains.value.every((d) => !d.catchall_address)) {
      items.push({ level: 'info', title: 'No catch-all configured', detail: 'Optional: forward unknown recipients to a mailbox under Domains → Catch-all.' })
    }
  }
  if (status.value?.public_ip === '127.0.0.1') {
    items.push({ level: 'warn', title: 'Public IP not detected', detail: 'DNS records may be generated with a loopback address. Set the server public IP.' })
  }
  if (egress.value) {
    if (!egress.value.port_25_egress_reachable) {
      items.push({ level: 'warn', title: 'Outbound port 25 blocked', detail: 'Configure an SMTP relay under Domains → Route to send mail.' })
    }
    if (!egress.value.ptr_matches_hostname) {
      items.push({ level: 'warn', title: 'PTR record mismatch', detail: `Reverse DNS for ${egress.value.public_ip} does not match ${egress.value.hostname}.` })
    }
  }
  if (!items.length) {
    items.push({ level: 'ok', title: 'Mail stack looks healthy', detail: 'Services are running and no obvious configuration gaps were found.' })
  }
  return items
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [st, ds, mb, al] = await Promise.all([
      apiFetch<any>('/mail/status'),
      apiFetch<any[]>('/mail/domains'),
      apiFetch<any[]>('/mail/mailboxes'),
      apiFetch<any[]>('/mail/aliases'),
    ])
    status.value = st
    domains.value = ds
    mailboxes.value = mb
    aliases.value = al
    if (!newMbox.mail_domain_id && ds.length) newMbox.mail_domain_id = ds[0].id
    if (!newAlias.mail_domain_id && ds.length) newAlias.mail_domain_id = ds[0].id
  } catch (e: any) {
    error.value = e?.message || 'Failed to load mail server data'
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  await load()
  if (activeSection.value === 'queue') await loadQueue()
  if (activeSection.value === 'logs') await loadLogs()
  if (activeSection.value === 'diagnostics') await runEgress()
}

function setSection(section: Section) {
  activeSection.value = section
  if (section === 'queue') loadQueue()
  if (section === 'logs') loadLogs()
  if (section === 'diagnostics' && !egress.value) runEgress()
}

function notify(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3000)
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

function formatDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
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
    error.value = 'Enter a mail domain'
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
    notify('Mail domain created. Publish the DNS records from the DNS panel.')
  } catch (e: any) {
    fail(e)
  } finally {
    busy.value = ''
  }
}

async function deleteDomain(domain: any) {
  if (!window.confirm(`Delete ${domain.domain}? All mailboxes and aliases for this domain will be removed.`)) return
  busy.value = 'domain'
  try {
    await apiFetch(`/mail/domains/${domain.id}`, { method: 'DELETE' })
    await load()
    notify(`${domain.domain} deleted`)
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
    error.value = 'Choose a domain, local part and password'
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
    notify('Mailbox created')
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
    notify('Mailbox updated')
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
  if (!window.confirm(`Delete mailbox ${mailbox.email}? Existing mail files are kept on disk.`)) return
  try {
    await apiFetch(`/mail/mailboxes/${mailbox.id}`, { method: 'DELETE' })
    await load()
    notify('Mailbox deleted')
  } catch (e: any) {
    fail(e)
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
    error.value = 'Choose a domain, source address and destination'
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
    notify('Alias created')
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
    notify('Outbound route updated')
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
    notify('Catch-all updated')
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

async function queueAction(action: 'hold' | 'delete', item: any) {
  const label = action === 'hold' ? 'Hold' : 'Delete'
  if (!window.confirm(`${label} queue item ${item.queue_id}?`)) return
  try {
    await apiFetch(`/mail/queue/${action}?queue_id=${encodeURIComponent(item.queue_id)}`, { method: 'POST' })
    await loadQueue()
    notify(`Queue item ${item.queue_id}: ${label.toLowerCase()} requested`)
  } catch (e: any) {
    fail(e)
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
