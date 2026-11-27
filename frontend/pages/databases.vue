<template>
  <div class="space-y-3 text-xs">
    <!-- Top Engine Tabs (aaPanel style) -->
    <div class="flex items-center gap-6 border-b border-slate-200 bg-white px-4 py-2 font-medium overflow-x-auto">
      <button
        v-for="tab in engineTabs"
        :key="tab.id"
        @click="activeEngineTab = tab.id; load()"
        :class="activeEngineTab === tab.id ? 'text-emerald-600 font-semibold border-b-2 border-emerald-600' : 'text-slate-600 hover:text-slate-900 border-b-2 border-transparent'"
        class="pb-2 whitespace-nowrap transition-colors"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Main Container -->
    <div class="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-3">
      <!-- Auto Backup Info Banner -->
      <div class="px-3 py-2 rounded bg-slate-50 border border-slate-200 flex items-center gap-3 text-[11px] text-slate-600">
        <span class="font-semibold text-slate-700 flex items-center gap-1.5">
          <span class="w-4 h-4 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center text-[10px] font-bold">i</span>
          Auto Backup Database
        </span>
        <button
          @click="autoBackup = !autoBackup"
          :class="autoBackup ? 'bg-emerald-600' : 'bg-slate-300'"
          class="w-8 h-4 rounded-full relative transition-colors"
        >
          <span :class="autoBackup ? 'translate-x-4' : 'translate-x-0.5'" class="block w-3 h-3 rounded-full bg-white transition-transform"></span>
        </button>
        <span>After adding a database, you can turn on automatic backup to ensure data security.</span>
      </div>

      <!-- Redis / Unsupported Engine Notice if not MySQL/PgSQL -->
      <div v-if="activeEngineTab === 'redis'" class="p-6 border border-slate-200 rounded bg-slate-50/50 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-sm font-bold text-slate-900">Redis In-Memory Store</h3>
            <p class="text-slate-500 mt-0.5">Status: <span :class="engineStatus.active ? 'text-emerald-600 font-semibold' : 'text-amber-600 font-semibold'">{{ engineStatus.active ? '● Running' : '● Stopped / Not Installed' }}</span></p>
          </div>
          <NuxtLink to="/packages" class="np-btn-primary">Manage Redis in Packages</NuxtLink>
        </div>
      </div>

      <!-- MySQL / PgSQL Workspace -->
      <template v-else>
        <!-- Action Toolbar -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-1.5">
            <button v-if="auth.can('databases:write')" @click="openAddDb" class="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">
              Add DB
            </button>
            <button @click="openRootPasswordModal" class="px-2.5 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
              Root password
            </button>
            <button @click="openPhpMyAdminGlobal" class="px-2.5 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
              phpMyAdmin
            </button>
            <button @click="syncFromServer" :disabled="syncing" class="px-2.5 py-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
              {{ syncing ? 'Syncing...' : 'Get DB from server' }}
            </button>
            <span class="px-2.5 py-1.5 rounded border border-slate-200 bg-slate-50 text-slate-700 font-mono text-[11px] flex items-center gap-1.5">
              <span>{{ activeEngineTab === 'mariadb' ? 'Mysql' : 'PgSQL' }} {{ engineStatus.version }}</span>
              <span :class="engineStatus.active ? 'text-emerald-600' : 'text-amber-500'">▶</span>
            </span>
          </div>

          <div class="flex items-center gap-2">
            <select v-model="locationFilter" class="np-input w-28">
              <option value="all">All</option>
              <option value="localhost">Localhost</option>
              <option value="remote">Remote</option>
            </select>
            <div class="relative">
              <input v-model="searchQuery" placeholder="Database search" class="np-input w-48 pr-7" />
              <Search class="w-3.5 h-3.5 text-slate-400 absolute right-2 top-2" />
            </div>
          </div>
        </div>

        <!-- Databases Table -->
        <div class="border border-slate-200 rounded overflow-x-auto">
          <table class="np-table">
            <thead>
              <tr class="bg-slate-50">
                <th class="w-8"><input type="checkbox" @change="toggleAll($event)" /></th>
                <th>Database name</th>
                <th>Username</th>
                <th>Password</th>
                <th>Quota</th>
                <th>Backup</th>
                <th>Location</th>
                <th>Note</th>
                <th class="text-right">Operate</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="db in paginatedDatabases" :key="db.id" class="hover:bg-slate-50/80">
                <td><input type="checkbox" :value="db.id" v-model="selectedIds" /></td>
                <td class="font-semibold text-slate-900">{{ db.db_name }}</td>
                <td class="font-mono text-slate-700">{{ db.db_user }}</td>
                <td>
                  <div class="flex items-center gap-1.5 font-mono text-[11px]">
                    <span>{{ revealedPasswords[db.id] || '••••••••••' }}</span>
                    <button @click="toggleReveal(db.id)" class="text-slate-400 hover:text-slate-700" title="Show/Hide Password">👁</button>
                    <button @click="copyPassword(db.id)" class="text-slate-400 hover:text-emerald-600" title="Copy Password">📋</button>
                  </div>
                </td>
                <td class="text-emerald-600 font-medium">{{ db.quota_mb ? `${db.quota_mb} MB` : 'Not set' }}</td>
                <td>
                  <button @click="openBackupModal(db)" class="text-[11px] hover:underline">
                    <span :class="db.backup_count > 0 ? 'text-emerald-600 font-medium' : 'text-amber-600'">
                      {{ db.backup_count > 0 ? `Exists(${db.backup_count})` : 'Not exist' }}
                    </span>
                    <span class="text-slate-400 mx-1">|</span>
                    <span class="text-emerald-600">Import</span>
                  </button>
                </td>
                <td class="text-slate-600">{{ db.db_host === 'localhost' ? 'Localhost' : db.db_host }}</td>
                <td>
                  <button @click="editNote(db)" class="text-slate-600 hover:text-emerald-600 hover:underline truncate max-w-[120px]">
                    {{ db.note || db.db_name }}
                  </button>
                </td>
                <td class="text-right whitespace-nowrap space-x-2">
                  <button @click="openPhpMyAdmin(db)" class="text-emerald-600 hover:underline font-medium">phpMyAdmin</button>
                  <button @click="openPermissionModal(db)" class="text-emerald-600 hover:underline">Permission</button>
                  <button @click="openToolsModal(db)" class="text-emerald-600 hover:underline">Tools</button>
                  <button @click="openPasswordModal(db)" class="text-emerald-600 hover:underline">Password</button>
                  <button v-if="auth.can('databases:delete')" @click="dropDb(db)" class="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
              <tr v-if="filteredDatabases.length === 0">
                <td colspan="9" class="p-8 text-center text-slate-400">
                  No databases found. Click <strong>Add DB</strong> to create one or <strong>Get DB from server</strong> to import existing databases.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Footer: Batch + Pagination -->
        <div class="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-slate-600">
          <div class="flex items-center gap-2">
            <select v-model="batchAction" class="np-input w-36">
              <option value="">Please choose</option>
              <option value="delete">Delete Selected</option>
            </select>
            <button @click="executeBatch" :disabled="!selectedIds.length || !batchAction" class="np-btn-secondary disabled:opacity-40">
              Execute
            </button>
          </div>

          <div class="flex items-center gap-2">
            <button @click="page = Math.max(1, page - 1)" :disabled="page === 1" class="px-2 py-0.5 border border-slate-300 rounded disabled:opacity-40">&lt;</button>
            <span class="px-2 py-0.5 border border-emerald-600 text-emerald-600 font-semibold rounded bg-emerald-50">{{ page }}</span>
            <button @click="page = Math.min(totalPages, page + 1)" :disabled="page >= totalPages" class="px-2 py-0.5 border border-slate-300 rounded disabled:opacity-40">&gt;</button>
            <select v-model.number="pageSize" class="border border-slate-300 rounded px-1.5 py-0.5 bg-white">
              <option :value="20">20 / page</option>
              <option :value="50">50 / page</option>
            </select>
            <span>Total {{ filteredDatabases.length }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Modal 1: Add DB -->
    <div v-if="showAddModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold text-slate-900">Add Database</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Database Name</label>
          <input v-model="addForm.db_name" @input="syncAddUsername" placeholder="app_prod" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Username</label>
          <input v-model="addForm.db_user" placeholder="app_prod" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Password</label>
          <div class="flex gap-1.5">
            <input v-model="addForm.db_password" placeholder="Strong password (min 6 chars)" class="np-input flex-1 font-mono" />
            <button @click="addForm.db_password = genPassword()" class="np-btn-secondary" title="Generate Random">↻</button>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[11px] font-medium text-slate-600 mb-1">Access Permission</label>
            <select v-model="addForm.db_host" class="np-input">
              <option value="localhost">Local server (localhost)</option>
              <option value="%">Everyone (%)</option>
            </select>
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-600 mb-1">Charset</label>
            <select v-model="addForm.charset" class="np-input">
              <option value="utf8mb4">utf8mb4</option>
              <option value="utf8">utf8</option>
              <option value="UTF8">UTF8 (PgSQL)</option>
            </select>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showAddModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="createDb" class="np-btn-primary">Submit</button>
        </div>
      </div>
    </div>

    <!-- Modal 2: Root Password (Image 2) -->
    <div v-if="showRootPwModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Change database password</h3>
          <button @click="showRootPwModal = false" class="text-slate-400 hover:text-slate-700 font-bold">✕</button>
        </div>
        <div class="flex items-center gap-3">
          <label class="w-28 text-slate-600 font-medium">Root password</label>
          <div class="flex flex-1 border border-slate-300 rounded overflow-hidden">
            <input v-model="rootPasswordInput" class="flex-1 px-2.5 py-1.5 font-mono focus:outline-none" />
            <button @click="rootPasswordInput = genPassword()" class="px-2.5 bg-slate-50 border-l border-slate-300 hover:bg-slate-100" title="Randomize">↻</button>
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="showRootPwModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="saveRootPassword" class="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">Confirm</button>
        </div>
      </div>
    </div>

    <!-- Modal 3: MySQL Toolbox (Image 3) -->
    <div v-if="toolsDb" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-2xl w-full max-w-3xl max-h-[82vh] flex flex-col overflow-hidden">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <h3 class="text-sm font-bold text-slate-800">{{ toolsDb.engine === 'mariadb' ? 'MySQL' : 'PgSQL' }} Toolbox [{{ toolsDb.db_name }}]</h3>
          <button @click="toolsDb = null" class="text-slate-400 hover:text-slate-700 font-bold">✕</button>
        </div>
        <div class="p-4 flex-1 overflow-y-auto space-y-3">
          <div class="inline-flex items-center gap-4 px-3 py-1.5 bg-slate-100 rounded text-xs font-medium text-slate-700">
            <span>Database name: <strong>{{ toolsDb.db_name }}</strong></span>
            <span>Size: <strong>{{ formatBytes(toolsData.total_size_bytes) }}</strong></span>
          </div>
          <div class="border border-slate-200 rounded overflow-hidden">
            <table class="np-table">
              <thead>
                <tr class="bg-slate-50">
                  <th>Table name</th>
                  <th>Engine</th>
                  <th>Character</th>
                  <th>Row number</th>
                  <th>Size</th>
                  <th class="text-right">Operate</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in toolsData.tables" :key="t.name" class="hover:bg-slate-50">
                  <td class="font-mono font-medium text-slate-800">{{ t.name }}</td>
                  <td>{{ t.engine }}</td>
                  <td class="text-[11px] text-slate-500">{{ t.collation }}</td>
                  <td class="font-mono">{{ t.rows }}</td>
                  <td class="font-mono">{{ formatBytes(t.size_bytes) }}</td>
                  <td class="text-right space-x-2 whitespace-nowrap">
                    <button @click="runToolAction(t.name, 'repair')" class="text-emerald-600 hover:underline">Repair</button>
                    <button @click="runToolAction(t.name, 'optimize')" class="text-emerald-600 hover:underline">Optimize</button>
                    <button
                      v-if="toolsDb.engine === 'mariadb'"
                      @click="runToolAction(t.name, t.engine === 'InnoDB' ? 'to_myisam' : 'to_innodb')"
                      class="text-emerald-600 hover:underline"
                    >
                      Convert to {{ t.engine === 'InnoDB' ? 'MyISAM' : 'InnoDB' }}
                    </button>
                  </td>
                </tr>
                <tr v-if="toolsData.tables.length === 0">
                  <td colspan="6" class="p-6 text-center text-slate-400">No tables found in {{ toolsDb.db_name }}.</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ul class="text-[11px] text-slate-500 space-y-1 list-disc pl-4">
            <li><strong>[Repair]</strong> Try to repair damaged tables with the REPAIR command.</li>
            <li><strong>[Optimize]</strong> Execute OPTIMIZE command to recover unreleased disk space.</li>
            <li><strong>[Convert to InnoDB/MyISAM]</strong> Convert database table storage engine.</li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Modal 4: Set Database Permissions (Image 4) -->
    <div v-if="permDb" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Set database permissions [{{ permDb.db_name }}]</h3>
          <button @click="permDb = null" class="text-slate-400 hover:text-slate-700 font-bold">✕</button>
        </div>
        <div class="space-y-2">
          <div class="flex items-center gap-3">
            <label class="w-24 text-slate-600 font-medium">Permission</label>
            <select v-model="permMode" class="np-input flex-1">
              <option value="localhost">Local server</option>
              <option value="%">Everyone (%)</option>
              <option value="custom">Specified IP</option>
            </select>
          </div>
          <div v-if="permMode === 'custom'" class="flex items-center gap-3">
            <label class="w-24 text-slate-600 font-medium">Allowed IP</label>
            <input v-model="permCustomIp" placeholder="e.g. 203.0.113.10" class="np-input flex-1 font-mono" />
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="permDb = null" class="np-btn-secondary">Cancel</button>
          <button @click="savePermission" class="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">Confirm</button>
        </div>
      </div>
    </div>

    <!-- Modal 5: Change Database User Password (Image 5) -->
    <div v-if="pwDb" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Change the database password [{{ pwDb.db_name }}]</h3>
          <button @click="pwDb = null" class="text-slate-400 hover:text-slate-700 font-bold">✕</button>
        </div>
        <div class="space-y-3">
          <div class="flex items-center gap-3">
            <label class="w-24 text-slate-600 font-medium">Username</label>
            <input :value="pwDb.db_user" disabled class="np-input flex-1 bg-slate-100 text-slate-500" />
          </div>
          <div class="flex items-center gap-3">
            <label class="w-24 text-slate-600 font-medium">Password</label>
            <div class="flex flex-1 border border-slate-300 rounded overflow-hidden">
              <input v-model="pwNewInput" class="flex-1 px-2.5 py-1.5 font-mono focus:outline-none" />
              <button @click="pwNewInput = genPassword()" class="px-2.5 bg-slate-50 border-l border-slate-300 hover:bg-slate-100" title="Randomize">↻</button>
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2">
          <button @click="pwDb = null" class="np-btn-secondary">Cancel</button>
          <button @click="saveUserPassword" class="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium">Confirm</button>
        </div>
      </div>
    </div>

    <!-- Modal 6: Backup / Import / Export SQL -->
    <div v-if="backupDb" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-lg space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold text-slate-900">Backup & Import SQL — {{ backupDb.db_name }}</h3>
          <button @click="backupDb = null" class="text-slate-400 hover:text-slate-700 font-bold">✕</button>
        </div>
        <div class="flex gap-2">
          <button @click="exportSqlDump" class="np-btn-primary">Export .SQL Dump</button>
        </div>
        <div class="border-t border-slate-200 pt-3 space-y-2">
          <label class="block text-[11px] font-semibold text-slate-700">Import / Execute SQL Script</label>
          <textarea v-model="importSqlText" rows="8" placeholder="Paste SQL dump or statements here..." class="np-input font-mono text-[11px]"></textarea>
          <div class="flex justify-end gap-2">
            <button @click="backupDb = null" class="np-btn-secondary">Close</button>
            <button @click="runImportSql" :disabled="!importSqlText.trim()" class="np-btn-primary">Import SQL</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal 7: Built-in phpMyAdmin (SQL & Table Explorer) -->
    <div v-if="pmaDb" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-3">
      <div class="bg-white rounded-lg shadow-2xl w-full max-w-6xl h-[88vh] flex flex-col overflow-hidden">
        <!-- phpMyAdmin Header -->
        <div class="px-4 py-2.5 bg-slate-900 text-white flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="px-2 py-0.5 rounded bg-emerald-600 font-bold text-[11px]">phpMyAdmin</span>
            <span class="font-mono text-xs text-slate-200">Server: Localhost » Database: <strong class="text-emerald-400">{{ pmaDb.db_name }}</strong></span>
          </div>
          <div class="flex items-center gap-2">
            <button @click="pmaTab = 'browse'" :class="pmaTab === 'browse' ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-300'" class="px-2.5 py-1 rounded text-[11px]">Browse</button>
            <button @click="pmaTab = 'sql'" :class="pmaTab === 'sql' ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-slate-300'" class="px-2.5 py-1 rounded text-[11px]">SQL Console</button>
            <button @click="pmaDb = null" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px]">Close</button>
          </div>
        </div>

        <div class="flex-1 flex overflow-hidden">
          <!-- Left Tables Tree -->
          <div class="w-56 border-r border-slate-200 bg-slate-50 overflow-y-auto p-2 space-y-1 shrink-0">
            <div class="px-2 py-1 text-[11px] font-bold text-slate-500 uppercase flex items-center justify-between">
              <span>Tables ({{ pmaTables.length }})</span>
              <button @click="loadPmaTables" class="text-emerald-600 hover:underline">↻</button>
            </div>
            <button
              v-for="t in pmaTables"
              :key="t.name"
              @click="selectPmaTable(t.name)"
              :class="pmaSelectedTable === t.name ? 'bg-emerald-600 text-white font-semibold' : 'text-slate-700 hover:bg-slate-200/70'"
              class="w-full text-left px-2.5 py-1.5 rounded font-mono text-[11px] flex items-center justify-between"
            >
              <span class="truncate">{{ t.name }}</span>
              <span class="text-[10px] opacity-75">{{ t.rows }}</span>
            </button>
            <div v-if="pmaTables.length === 0" class="px-2 py-4 text-slate-400 text-[11px] text-center">No tables yet</div>
          </div>

          <!-- Right Workspace -->
          <div class="flex-1 flex flex-col overflow-hidden bg-white">
            <!-- Browse Table Rows -->
            <div v-if="pmaTab === 'browse'" class="flex-1 flex flex-col overflow-hidden">
              <div class="px-4 py-2 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                <span class="font-mono font-bold text-slate-800">{{ pmaSelectedTable ? `SELECT * FROM ${pmaSelectedTable} LIMIT 100` : 'Select a table from the left sidebar or switch to SQL Console' }}</span>
                <span v-if="pmaRowsResult.rows.length" class="text-[11px] text-slate-500">{{ pmaRowsResult.rows.length }} rows shown</span>
              </div>
              <div class="flex-1 overflow-auto p-3">
                <table v-if="pmaRowsResult.columns.length" class="np-table border border-slate-200">
                  <thead>
                    <tr class="bg-slate-100">
                      <th v-for="col in pmaRowsResult.columns" :key="col" class="font-mono text-[11px]">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rIdx) in pmaRowsResult.rows" :key="rIdx" class="hover:bg-slate-50">
                      <td v-for="(cell, cIdx) in row" :key="cIdx" class="font-mono text-[11px] max-w-xs truncate" :title="cell">{{ cell }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="p-10 text-center text-slate-400">
                  {{ pmaSelectedTable ? 'Table is empty or returned 0 rows.' : 'Click any table on the left to inspect its rows.' }}
                </div>
              </div>
            </div>

            <!-- SQL Query Console -->
            <div v-else class="flex-1 flex flex-col overflow-hidden p-4 space-y-3">
              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <label class="font-bold text-slate-700">Run SQL query on database <code class="text-emerald-600">{{ pmaDb.db_name }}</code>:</label>
                  <span v-if="pmaQueryResult" class="text-[11px] text-slate-500">Executed in {{ pmaQueryResult.elapsed_ms }} ms</span>
                </div>
                <textarea v-model="pmaSqlInput" rows="5" class="np-input font-mono text-xs bg-slate-950 text-emerald-300 p-3"></textarea>
                <div class="flex justify-end">
                  <button @click="runPmaQuery" class="np-btn-primary">Go (Execute SQL)</button>
                </div>
              </div>

              <div v-if="pmaQueryResult" class="flex-1 overflow-auto border border-slate-200 rounded p-2">
                <div v-if="pmaQueryResult.stderr && !pmaQueryResult.ok" class="p-3 bg-rose-50 text-rose-700 font-mono text-xs rounded">
                  {{ pmaQueryResult.stderr }}
                </div>
                <table v-else-if="pmaQueryResult.columns?.length" class="np-table">
                  <thead>
                    <tr class="bg-slate-100">
                      <th v-for="col in pmaQueryResult.columns" :key="col" class="font-mono text-[11px]">{{ col }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rIdx) in pmaQueryResult.rows" :key="rIdx">
                      <td v-for="(cell, cIdx) in row" :key="cIdx" class="font-mono text-[11px]">{{ cell }}</td>
                    </tr>
                  </tbody>
                </table>
                <pre v-else class="p-3 text-xs font-mono text-emerald-700 bg-emerald-50 rounded">{{ pmaQueryResult.raw || 'Query executed successfully (0 rows returned).' }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Search } from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch } = useApi()

const engineTabs = [
  { id: 'mariadb', label: 'MySQL' },
  { id: 'postgresql', label: 'PgSQL' },
  { id: 'redis', label: 'Redis' },
]
const activeEngineTab = ref('mariadb')
const autoBackup = ref(false)
const syncing = ref(false)

const databases = ref<any[]>([])
const engineStatus = ref<any>({ active: true, version: '10.11' })
const locationFilter = ref('all')
const searchQuery = ref('')
const selectedIds = ref<number[]>([])
const batchAction = ref('')
const page = ref(1)
const pageSize = ref(20)
const revealedPasswords = ref<Record<number, string>>({})

const showAddModal = ref(false)
const addForm = reactive({ engine: 'mariadb', db_name: '', db_user: '', db_password: '', db_host: 'localhost', charset: 'utf8mb4' })

const showRootPwModal = ref(false)
const rootPasswordInput = ref('')

const toolsDb = ref<any>(null)
const toolsData = ref<any>({ total_size_bytes: 0, tables: [] })

const permDb = ref<any>(null)
const permMode = ref('localhost')
const permCustomIp = ref('')

const pwDb = ref<any>(null)
const pwNewInput = ref('')

const backupDb = ref<any>(null)
const importSqlText = ref('')

const pmaDb = ref<any>(null)
const pmaTab = ref<'browse' | 'sql'>('browse')
const pmaTables = ref<any[]>([])
const pmaSelectedTable = ref('')
const pmaRowsResult = ref<{ columns: string[]; rows: string[][] }>({ columns: [], rows: [] })
const pmaSqlInput = ref('SHOW TABLES;')
const pmaQueryResult = ref<any>(null)

const filteredDatabases = computed(() => {
  return databases.value.filter((d) => {
    if (locationFilter.value === 'localhost' && d.db_host !== 'localhost') return false
    if (locationFilter.value === 'remote' && d.db_host === 'localhost') return false
    if (searchQuery.value && !d.db_name.toLowerCase().includes(searchQuery.value.toLowerCase()) && !d.db_user.toLowerCase().includes(searchQuery.value.toLowerCase())) {
      return false
    }
    return true
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredDatabases.value.length / pageSize.value)))
const paginatedDatabases = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredDatabases.value.slice(start, start + pageSize.value)
})

function genPassword() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%'
  return Array.from({ length: 14 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

function formatBytes(bytes: number) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 2)} ${units[i]}`
}

async function load() {
  try {
    engineStatus.value = await apiFetch(`/databases/status?engine=${activeEngineTab.value}`)
  } catch {
    engineStatus.value = { active: false, version: '-' }
  }
  if (activeEngineTab.value === 'mariadb' || activeEngineTab.value === 'postgresql') {
    databases.value = await apiFetch(`/databases?engine=${activeEngineTab.value}`)
  } else {
    databases.value = []
  }
}

function openAddDb() {
  addForm.engine = activeEngineTab.value
  addForm.db_name = ''
  addForm.db_user = ''
  addForm.db_password = genPassword()
  addForm.db_host = 'localhost'
  addForm.charset = activeEngineTab.value === 'postgresql' ? 'UTF8' : 'utf8mb4'
  showAddModal.value = true
}

function syncAddUsername() {
  addForm.db_user = addForm.db_name
}

async function createDb() {
  await apiFetch('/databases', { method: 'POST', body: addForm })
  showAddModal.value = false
  await load()
}

async function syncFromServer() {
  syncing.value = true
  try {
    await apiFetch(`/databases/sync-from-server?engine=${activeEngineTab.value}`, { method: 'POST' })
    await load()
  } finally {
    syncing.value = false
  }
}

function openRootPasswordModal() {
  rootPasswordInput.value = genPassword()
  showRootPwModal.value = true
}

async function saveRootPassword() {
  await apiFetch('/databases/root-password', {
    method: 'POST',
    body: { engine: activeEngineTab.value, password: rootPasswordInput.value },
  })
  showRootPwModal.value = false
}

async function toggleReveal(id: number) {
  if (revealedPasswords.value[id]) {
    delete revealedPasswords.value[id]
    return
  }
  const res = await apiFetch<any>(`/databases/${id}/password/reveal`)
  revealedPasswords.value[id] = res.password || '(not stored)'
}

async function copyPassword(id: number) {
  let pw = revealedPasswords.value[id]
  if (!pw) {
    const res = await apiFetch<any>(`/databases/${id}/password/reveal`)
    pw = res.password
  }
  if (pw) navigator.clipboard?.writeText(pw)
}

function openPermissionModal(db: any) {
  permDb.value = db
  if (db.db_host === 'localhost' || db.db_host === '%') {
    permMode.value = db.db_host
    permCustomIp.value = ''
  } else {
    permMode.value = 'custom'
    permCustomIp.value = db.db_host
  }
}

async function savePermission() {
  const host = permMode.value === 'custom' ? permCustomIp.value.trim() : permMode.value
  if (!host) return
  await apiFetch(`/databases/${permDb.value.id}/permission`, { method: 'PUT', body: { db_host: host } })
  permDb.value = null
  await load()
}

async function openToolsModal(db: any) {
  toolsDb.value = db
  toolsData.value = await apiFetch(`/databases/${db.id}/tools`)
}

async function runToolAction(table_name: string, action: string) {
  await apiFetch(`/databases/${toolsDb.value.id}/tools/action`, { method: 'POST', body: { table_name, action } })
  toolsData.value = await apiFetch(`/databases/${toolsDb.value.id}/tools`)
}

function openPasswordModal(db: any) {
  pwDb.value = db
  pwNewInput.value = genPassword()
}

async function saveUserPassword() {
  await apiFetch(`/databases/${pwDb.value.id}/rotate-password`, { method: 'POST', body: { new_password: pwNewInput.value } })
  delete revealedPasswords.value[pwDb.value.id]
  pwDb.value = null
}

async function editNote(db: any) {
  const note = prompt('Database note:', db.note || db.db_name)
  if (note === null) return
  await apiFetch(`/databases/${db.id}/note`, { method: 'PUT', body: { note } })
  await load()
}

function openBackupModal(db: any) {
  backupDb.value = db
  importSqlText.value = ''
}

async function exportSqlDump() {
  const res = await apiFetch<any>(`/databases/${backupDb.value.id}/export`)
  const blob = new Blob([res.dump || ''], { type: 'application/sql' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${backupDb.value.db_name}.sql`
  a.click()
}

async function runImportSql() {
  await apiFetch(`/databases/${backupDb.value.id}/import`, { method: 'POST', body: { sql_content: importSqlText.value } })
  backupDb.value = null
}

function openPhpMyAdminGlobal() {
  if (databases.value.length > 0) {
    openPhpMyAdmin(databases.value[0])
  } else {
    alert('Please add or sync a database first to open phpMyAdmin.')
  }
}

async function openPhpMyAdmin(db: any) {
  pmaDb.value = db
  pmaTab.value = 'browse'
  pmaSelectedTable.value = ''
  pmaRowsResult.value = { columns: [], rows: [] }
  pmaQueryResult.value = null
  pmaSqlInput.value = db.engine === 'mariadb' ? 'SHOW TABLES;' : 'SELECT tablename FROM pg_tables WHERE schemaname = \'public\';'
  await loadPmaTables()
}

async function loadPmaTables() {
  if (!pmaDb.value) return
  const res = await apiFetch<any>(`/databases/${pmaDb.value.id}/tools`)
  pmaTables.value = res.tables || []
  if (pmaTables.value.length > 0 && !pmaSelectedTable.value) {
    await selectPmaTable(pmaTables.value[0].name)
  }
}

async function selectPmaTable(tbl: string) {
  pmaSelectedTable.value = tbl
  pmaTab.value = 'browse'
  pmaRowsResult.value = await apiFetch(`/databases/${pmaDb.value.id}/tables/${encodeURIComponent(tbl)}/rows`)
}

async function runPmaQuery() {
  pmaQueryResult.value = await apiFetch(`/databases/${pmaDb.value.id}/query`, {
    method: 'POST',
    body: { sql: pmaSqlInput.value },
  })
  await loadPmaTables()
}

async function dropDb(db: any) {
  if (!confirm(`Permanently drop database ${db.db_name}?`)) return
  await apiFetch(`/databases/${db.id}`, { method: 'DELETE' })
  await load()
}

function toggleAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedIds.value = checked ? paginatedDatabases.value.map((d) => d.id) : []
}

async function executeBatch() {
  if (batchAction.value !== 'delete' || !selectedIds.value.length) return
  if (!confirm(`Drop ${selectedIds.value.length} selected databases?`)) return
  for (const id of selectedIds.value) {
    await apiFetch(`/databases/${id}`, { method: 'DELETE' })
  }
  selectedIds.value = []
  batchAction.value = ''
  await load()
}

onMounted(load)
</script>
