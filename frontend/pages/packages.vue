<template>
  <div class="space-y-4 text-xs">
    <!-- Header Title & Quick Actions -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-base font-bold text-slate-900">Software & Package Manager</h1>
        <p class="text-xs text-slate-500">Global Linux package store, source compiler, and security-hardened PHP & Python runtime managers.</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button @click="updateRepoCache" :disabled="isStreaming" class="np-btn-secondary flex items-center gap-1.5">
          <RefreshCw :class="{ 'animate-spin': isStreaming }" class="w-3.5 h-3.5 text-slate-600" />
          <span>Update Repo Cache (apt update)</span>
        </button>
        <button @click="openCustomInstallModal" :disabled="isStreaming" class="np-btn-primary flex items-center gap-1.5">
          <Plus class="w-3.5 h-3.5" />
          <span>Quick Install APT</span>
        </button>
      </div>
    </div>

    <!-- Main Navigation Tabs -->
    <div class="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 text-xs font-medium overflow-x-auto rounded-t-lg">
      <button
        v-for="tab in mainTabs"
        :key="tab.id"
        @click="switchMainTab(tab.id)"
        :class="activeMainTab === tab.id ? 'text-emerald-600 font-semibold border-b-2 border-emerald-600 bg-emerald-50/50' : 'text-slate-600 hover:text-slate-900 border-b-2 border-transparent'"
        class="pb-2 pt-1 px-3 whitespace-nowrap transition-colors flex items-center gap-1.5 rounded-t"
      >
        <component :is="tab.icon" class="w-3.5 h-3.5" />
        <span>{{ tab.label }}</span>
        <span v-if="tab.badge" class="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-mono">
          {{ tab.badge }}
        </span>
      </button>
    </div>

    <!-- TAB 1: CURATED STACK CATALOG -->
    <div v-if="activeMainTab === 'curated'" class="space-y-3">
      <!-- Category Filter Pills -->
      <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px]">
        <button
          v-for="cat in categories"
          :key="cat.id"
          @click="activeCategory = cat.id; loadCatalog()"
          :class="activeCategory === cat.id ? 'bg-emerald-600 text-white font-medium' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
          class="px-2.5 py-1 rounded-full whitespace-nowrap transition-colors"
        >
          {{ cat.label }}
        </button>
      </div>

      <!-- Search & Status Legend -->
      <div class="np-card p-2.5 flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <input
            v-model="search"
            @input="onSearchInput"
            placeholder="Filter software by name or package..."
            class="np-input w-72"
          />
          <button @click="loadCatalog" class="np-btn-secondary">Filter</button>
        </div>
        <div class="flex items-center gap-3 text-slate-500 text-[11px]">
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span>Running</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-amber-500"></span>
            <span>Stopped</span>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-slate-300"></span>
            <span>Not Installed</span>
          </div>
        </div>
      </div>

      <!-- Curated Catalog Table -->
      <div class="np-card overflow-hidden">
        <div v-if="loadingCatalog" class="p-8 text-center text-slate-400">
          <RefreshCw class="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-600" />
          <p>Inspecting software catalog and service states...</p>
        </div>
        <table v-else class="np-table">
          <thead>
            <tr>
              <th class="w-64">Software Name</th>
              <th class="w-28">Category</th>
              <th>Description & APT Packages</th>
              <th class="w-36 text-center">Service Status</th>
              <th class="w-40 text-center">Service Control</th>
              <th class="w-32 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in catalog" :key="item.slug" class="hover:bg-slate-50/80">
              <td>
                <div class="flex items-center gap-2.5">
                  <div class="w-8 h-8 rounded bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 font-bold text-xs shrink-0 font-mono">
                    <span v-if="item.category === 'PHP'" class="text-indigo-600">PHP</span>
                    <span v-else-if="item.category === 'Python'" class="text-amber-600">PY</span>
                    <span v-else-if="item.category === 'Web Server'" class="text-emerald-600">WEB</span>
                    <span v-else-if="item.category === 'Database'" class="text-amber-600">DB</span>
                    <span v-else-if="item.category === 'FTP'" class="text-blue-600">FTP</span>
                    <span v-else class="text-slate-600">APP</span>
                  </div>
                  <div>
                    <div class="flex items-center gap-1.5">
                      <span class="font-semibold text-slate-900">{{ item.name }}</span>
                      <span v-if="item.version" class="text-[10px] font-mono px-1 py-0.2 rounded bg-slate-100 text-slate-600">
                        v{{ item.version.split('+')[0].split('-')[0] }}
                      </span>
                    </div>
                    <span class="text-[10px] font-mono text-slate-400">{{ item.slug }}</span>
                  </div>
                </div>
              </td>
              <td>
                <span class="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200">
                  {{ item.category }}
                </span>
              </td>
              <td>
                <p class="text-slate-700 font-normal">{{ item.description }}</p>
                <div class="text-[10px] font-mono text-slate-400 mt-1 flex flex-wrap gap-1">
                  <span v-for="pkg in item.apt_packages" :key="pkg" class="bg-slate-50 px-1 py-0.2 rounded border border-slate-200">
                    {{ pkg }}
                  </span>
                </div>
              </td>
              <td class="text-center">
                <div v-if="item.is_installed">
                  <span
                    v-if="item.service_status === 'active'"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    Running
                  </span>
                  <span
                    v-else-if="item.service_status === 'inactive' && item.service"
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                    Stopped
                  </span>
                  <span
                    v-else
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200"
                  >
                    Installed
                  </span>
                </div>
                <div v-else>
                  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-400">
                    Not Installed
                  </span>
                </div>
              </td>
              <td class="text-center">
                <div v-if="item.is_installed && item.service" class="flex items-center justify-center gap-1">
                  <button
                    @click="controlService(item.slug, 'restart')"
                    :disabled="isStreaming"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium"
                    title="Restart service"
                  >
                    Restart
                  </button>
                  <button
                    v-if="item.service_status === 'active'"
                    @click="controlService(item.slug, 'stop')"
                    :disabled="isStreaming"
                    class="px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-700 text-[11px] font-medium"
                    title="Stop service"
                  >
                    Stop
                  </button>
                  <button
                    v-else
                    @click="controlService(item.slug, 'start')"
                    :disabled="isStreaming"
                    class="px-2 py-1 rounded bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-[11px] font-medium"
                    title="Start service"
                  >
                    Start
                  </button>
                </div>
                <span v-else class="text-slate-400 text-[11px]">-</span>
              </td>
              <td class="text-right">
                <button
                  v-if="!item.is_installed"
                  @click="confirmInstall(item)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium shadow-sm transition-colors"
                >
                  Install
                </button>
                <button
                  v-else
                  @click="confirmUninstall(item)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 text-[11px] font-medium transition-colors"
                >
                  Uninstall
                </button>
              </td>
            </tr>
            <tr v-if="catalog.length === 0">
              <td colspan="6" class="p-8 text-center text-slate-400">
                No software found matching the selected filter or search term.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 2: GLOBAL LINUX & UBUNTU STORE SEARCH -->
    <div v-else-if="activeMainTab === 'global'" class="space-y-3">
      <div class="np-card p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">
              <Box class="w-4 h-4 text-emerald-600" />
              <span>Ubuntu & Debian Global Package Repository Store</span>
            </h2>
            <p class="text-xs text-slate-500">Instant real-time search across 60,000+ official system packages from Ubuntu & Debian repositories.</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400">Showing top 50 results</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <input
            v-model="globalQuery"
            @keyup.enter="searchGlobalStore"
            placeholder="Search package name or keyword (e.g. redis, postgresql, certbot, ffmpeg, zsh, htop, curl)..."
            class="np-input flex-1 font-mono text-xs"
          />
          <button @click="searchGlobalStore" :disabled="loadingGlobal || !globalQuery.trim()" class="np-btn-primary flex items-center gap-1.5">
            <RefreshCw v-if="loadingGlobal" class="w-3.5 h-3.5 animate-spin" />
            <Search v-else class="w-3.5 h-3.5" />
            <span>Search Global Store</span>
          </button>
        </div>
      </div>

      <!-- Global Results Table -->
      <div class="np-card overflow-hidden">
        <div v-if="loadingGlobal" class="p-12 text-center text-slate-400 space-y-2">
          <RefreshCw class="w-7 h-7 animate-spin mx-auto text-emerald-600" />
          <p class="text-xs">Querying APT package cache repository...</p>
        </div>
        <div v-else-if="globalResults.length === 0 && hasSearchedGlobal" class="p-12 text-center text-slate-400">
          <p class="font-medium text-slate-700">No packages found matching "{{ globalQuery }}"</p>
          <p class="text-xs mt-1">Try searching for broader keywords like <code class="bg-slate-100 px-1 py-0.5 rounded font-mono">redis</code>, <code class="bg-slate-100 px-1 py-0.5 rounded font-mono">python</code>, or <code class="bg-slate-100 px-1 py-0.5 rounded font-mono">nginx</code>.</p>
        </div>
        <div v-else-if="!hasSearchedGlobal" class="p-12 text-center text-slate-400">
          <Search class="w-8 h-8 mx-auto mb-2 text-slate-300" />
          <p class="font-medium text-slate-600">Enter a package name above to query the online Linux repository</p>
          <p class="text-[11px] text-slate-400 mt-1">Popular: <button @click="globalQuery='redis'; searchGlobalStore()" class="text-emerald-600 hover:underline">redis</button>, <button @click="globalQuery='wireguard'; searchGlobalStore()" class="text-emerald-600 hover:underline">wireguard</button>, <button @click="globalQuery='ffmpeg'; searchGlobalStore()" class="text-emerald-600 hover:underline">ffmpeg</button>, <button @click="globalQuery='postgresql'; searchGlobalStore()" class="text-emerald-600 hover:underline">postgresql</button></p>
        </div>
        <table v-else class="np-table">
          <thead>
            <tr>
              <th class="w-64">Package Name</th>
              <th>Description</th>
              <th class="w-32 text-center">Status</th>
              <th class="w-48 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pkg in globalResults" :key="pkg.name" class="hover:bg-slate-50/80">
              <td class="font-mono font-semibold text-slate-900">
                <div class="flex items-center gap-1.5">
                  <Box class="w-3.5 h-3.5 text-slate-400" />
                  <span>{{ pkg.name }}</span>
                </div>
              </td>
              <td class="text-slate-700">
                <p>{{ pkg.description || 'No description provided in package metadata' }}</p>
              </td>
              <td class="text-center">
                <span
                  v-if="pkg.is_installed"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  Installed
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-500"
                >
                  Available
                </span>
              </td>
              <td class="text-right">
                <div class="flex items-center justify-end gap-1.5">
                  <button
                    @click="inspectPackageDetails(pkg.name)"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium"
                    title="View package details"
                  >
                    Details
                  </button>
                  <button
                    v-if="!pkg.is_installed"
                    @click="installGlobalPackage(pkg.name)"
                    :disabled="isStreaming"
                    class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium shadow-sm"
                  >
                    Install
                  </button>
                  <button
                    v-else
                    @click="removeRawApt(pkg.name)"
                    :disabled="isStreaming"
                    class="px-2.5 py-1 rounded border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 text-[11px] font-medium"
                  >
                    Remove
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 3: INSTALL FROM SOURCE COMPILER -->
    <div v-else-if="activeMainTab === 'source'" class="space-y-4">
      <!-- Source Build Presets -->
      <div class="space-y-2">
        <h3 class="text-xs font-bold text-slate-900 uppercase tracking-wider">Popular Source Build Presets (1-Click Compile)</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <div
            v-for="preset in sourcePresets"
            :key="preset.name"
            class="np-card p-3 flex flex-col justify-between space-y-2 hover:border-emerald-300 transition-colors"
          >
            <div>
              <div class="flex items-center justify-between">
                <span class="font-bold text-slate-900">{{ preset.name }}</span>
                <span class="text-[10px] font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-600">{{ preset.build_tool }}</span>
              </div>
              <p class="text-[11px] text-slate-500 mt-1">{{ preset.desc }}</p>
              <div class="text-[10px] font-mono text-slate-400 mt-2 truncate" :title="preset.url">
                {{ preset.url }}
              </div>
            </div>
            <div class="flex items-center justify-between pt-2 border-t border-slate-100">
              <button
                @click="populateSourceForm(preset)"
                class="text-[11px] text-emerald-600 hover:underline font-medium"
              >
                Customize
              </button>
              <button
                @click="triggerSourceInstall(preset)"
                :disabled="isStreaming"
                class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium shadow-sm"
              >
                Compile & Install
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Custom Source Build Form -->
      <div class="np-card p-4 space-y-3">
        <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">
          <Terminal class="w-4 h-4 text-emerald-600" />
          <span>Compile & Install Any Software from Source</span>
        </h3>
        <p class="text-xs text-slate-500">Provide an upstream Git repository or official tarball release. NexoPanel automatically prepares build dependencies (<code class="bg-slate-100 px-1 py-0.5 rounded font-mono">build-essential</code>, <code class="bg-slate-100 px-1 py-0.5 rounded font-mono">cmake</code>, <code class="bg-slate-100 px-1 py-0.5 rounded font-mono">gcc</code>), runs configure/build/install, and streams compilation output live.</p>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Package Name</label>
            <input v-model="sourceForm.name" placeholder="e.g. redis-7.4 or nginx-custom" class="np-input font-mono" />
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Source Type</label>
            <select v-model="sourceForm.source_type" class="np-input">
              <option value="tarball">Archive Tarball (.tar.gz, .tar.xz)</option>
              <option value="git">Git Repository (.git)</option>
            </select>
          </div>
          <div class="md:col-span-2">
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Download / Clone URL</label>
            <input v-model="sourceForm.url" placeholder="https://download.redis.io/redis-stable.tar.gz or https://github.com/..." class="np-input font-mono" />
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Git Branch / Tag (optional)</label>
            <input v-model="sourceForm.branch_or_tag" placeholder="e.g. master, main, v1.2.3" class="np-input font-mono" />
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Build System</label>
            <select v-model="sourceForm.build_tool" class="np-input">
              <option value="make">Make (./configure && make && make install)</option>
              <option value="cmake">CMake (cmake -B build && cmake --build)</option>
            </select>
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Configure Flags (optional)</label>
            <input v-model="sourceForm.configure_flags" placeholder="e.g. --prefix=/usr/local --enable-optimizations" class="np-input font-mono" />
          </div>
          <div>
            <label class="block text-[11px] font-medium text-slate-700 mb-1">Install Command</label>
            <input v-model="sourceForm.install_command" placeholder="default: make install or make altinstall" class="np-input font-mono" />
          </div>
        </div>

        <div class="flex justify-end pt-2">
          <button
            @click="triggerSourceInstall(sourceForm)"
            :disabled="isStreaming || !sourceForm.name || !sourceForm.url"
            class="np-btn-primary flex items-center gap-1.5"
          >
            <RefreshCw v-if="isStreaming" class="w-3.5 h-3.5 animate-spin" />
            <Download v-else class="w-3.5 h-3.5" />
            <span>Start Source Build & Installation</span>
          </button>
        </div>
      </div>
    </div>

    <!-- TAB 4: PHP RUNTIMES & SECURITY -->
    <div v-else-if="activeMainTab === 'php'" class="space-y-3">
      <!-- PHP Security Patch Banner -->
      <div class="np-card p-4 bg-gradient-to-r from-indigo-50 to-white border-indigo-200 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-indigo-950 flex items-center gap-1.5">
            <ShieldCheck class="w-4 h-4 text-indigo-600" />
            <span>PHP Security Patch Manager & Version Control</span>
          </h2>
          <p class="text-xs text-indigo-800/80">Keep all installed PHP runtimes updated with the latest CVE security patches via the Ondřej Surý official repository.</p>
        </div>
        <button
          @click="updatePhpSecurity"
          :disabled="isStreaming"
          class="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-sm flex items-center gap-1.5"
        >
          <RefreshCw :class="{ 'animate-spin': isStreaming }" class="w-3.5 h-3.5" />
          <span>Apply Security Updates to All PHP Versions</span>
        </button>
      </div>

      <!-- PHP Runtimes Table -->
      <div class="np-card overflow-hidden">
        <table class="np-table">
          <thead>
            <tr>
              <th class="w-44">PHP Version</th>
              <th class="w-32 text-center">Status</th>
              <th>UNIX Domain Socket Path</th>
              <th class="w-40 text-center">Service Actions</th>
              <th class="w-32 text-right">Package Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in phpRuntimes" :key="r.version" class="hover:bg-slate-50/80">
              <td class="font-semibold text-slate-900">
                <div class="flex items-center gap-2">
                  <div class="w-7 h-7 rounded bg-indigo-50 border border-indigo-200 flex items-center justify-center font-mono font-bold text-[11px] text-indigo-700">
                    {{ r.version }}
                  </div>
                  <div>
                    <span class="block">PHP {{ r.version }}</span>
                    <span v-if="r.version === '8.5'" class="text-[10px] text-amber-600 font-medium">Next-Gen Preview</span>
                    <span v-else-if="r.version === '8.4'" class="text-[10px] text-emerald-600 font-medium">Latest Active Stable</span>
                    <span v-else-if="r.version === '8.3'" class="text-[10px] text-emerald-600 font-medium">LTS Production</span>
                    <span v-else class="text-[10px] text-slate-400">Security LTS</span>
                  </div>
                </div>
              </td>
              <td class="text-center">
                <span
                  v-if="r.service_status === 'active'"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  Running
                </span>
                <span
                  v-else-if="r.is_installed"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200"
                >
                  Stopped
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-400"
                >
                  Not Installed
                </span>
              </td>
              <td class="font-mono text-[11px] text-slate-600">
                <span v-if="r.is_installed">{{ r.socket }}</span>
                <span v-else class="text-slate-400">-</span>
              </td>
              <td class="text-center">
                <div v-if="r.is_installed" class="flex items-center justify-center gap-1">
                  <button
                    @click="controlService(`php${r.version}`, 'restart')"
                    :disabled="isStreaming"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium"
                  >
                    Restart
                  </button>
                  <button
                    v-if="r.service_status === 'active'"
                    @click="controlService(`php${r.version}`, 'stop')"
                    :disabled="isStreaming"
                    class="px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 text-rose-700 text-[11px] font-medium"
                  >
                    Stop
                  </button>
                </div>
                <span v-else class="text-slate-400 text-[11px]">-</span>
              </td>
              <td class="text-right">
                <button
                  v-if="!r.is_installed"
                  @click="installPhpVersion(r.version)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium shadow-sm"
                >
                  Install PHP {{ r.version }}
                </button>
                <button
                  v-else
                  @click="uninstallPhpVersion(r.version)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700 text-[11px] font-medium"
                >
                  Uninstall
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 5: PYTHON RUNTIMES & SECURITY -->
    <div v-else-if="activeMainTab === 'python'" class="space-y-3">
      <!-- Python Security Banner -->
      <div class="np-card p-4 bg-gradient-to-r from-amber-50 to-white border-amber-200 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-bold text-amber-950 flex items-center gap-1.5">
            <ShieldCheck class="w-4 h-4 text-amber-600" />
            <span>Python Runtimes & Security Versions</span>
          </h2>
          <p class="text-xs text-amber-800/80">Manage modern Python environments (3.14, 3.13, 3.12, 3.11, 3.10) with automatic virtualenv toolchain and security updates.</p>
        </div>
        <button
          @click="updatePythonSecurity"
          :disabled="isStreaming"
          class="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-medium text-xs shadow-sm flex items-center gap-1.5"
        >
          <RefreshCw :class="{ 'animate-spin': isStreaming }" class="w-3.5 h-3.5" />
          <span>Apply Python Security Upgrades</span>
        </button>
      </div>

      <!-- Python Runtimes Table -->
      <div class="np-card overflow-hidden">
        <table class="np-table">
          <thead>
            <tr>
              <th class="w-44">Python Version</th>
              <th class="w-32 text-center">Status</th>
              <th>Binary Path & Installed Details</th>
              <th class="w-32 text-center">venv Support</th>
              <th class="w-36 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="py in pythonRuntimes" :key="py.version" class="hover:bg-slate-50/80">
              <td class="font-semibold text-slate-900">
                <div class="flex items-center gap-2">
                  <div class="w-7 h-7 rounded bg-amber-50 border border-amber-200 flex items-center justify-center font-mono font-bold text-[11px] text-amber-700">
                    {{ py.version }}
                  </div>
                  <div>
                    <span class="block">Python {{ py.version }}</span>
                    <span v-if="py.version === '3.13'" class="text-[10px] text-emerald-600 font-medium">Latest Stable (JIT)</span>
                    <span v-else-if="py.version === '3.12'" class="text-[10px] text-emerald-600 font-medium">Production Recommended</span>
                    <span v-else class="text-[10px] text-slate-400">Stable Runtime</span>
                  </div>
                </div>
              </td>
              <td class="text-center">
                <span
                  v-if="py.is_installed"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  Installed
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-400"
                >
                  Not Installed
                </span>
              </td>
              <td>
                <div v-if="py.is_installed">
                  <span class="font-mono text-[11px] text-slate-700 font-medium">{{ py.detailed_version }}</span>
                  <span class="block text-[10px] font-mono text-slate-400">{{ py.binary_path }}</span>
                </div>
                <span v-else class="text-slate-400 text-xs">Available for installation via Deadsnakes / APT</span>
              </td>
              <td class="text-center">
                <span
                  v-if="py.has_venv"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700"
                >
                  Ready
                </span>
                <span v-else class="text-slate-400 text-[11px]">-</span>
              </td>
              <td class="text-right">
                <button
                  v-if="!py.is_installed"
                  @click="installPythonVersion(py.version)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-medium shadow-sm"
                >
                  Install Python {{ py.version }}
                </button>
                <button
                  v-else
                  @click="reinstallPythonVersion(py.version)"
                  :disabled="isStreaming"
                  class="px-2.5 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-[11px] font-medium"
                >
                  Update/Reinstall
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 6: INSTALLED LOCAL DPKG PACKAGES -->
    <div v-else-if="activeMainTab === 'installed'" class="space-y-3">
      <div class="np-card p-2.5 flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <input
            v-model="installedSearch"
            @input="onInstalledSearchInput"
            placeholder="Search installed package names..."
            class="np-input w-72 font-mono"
          />
          <button @click="loadInstalledPackages" class="np-btn-secondary">Search</button>
        </div>
        <span class="text-xs text-slate-400">Total packages scanned: {{ rawPackages.length }}</span>
      </div>

      <div class="np-card overflow-hidden">
        <div v-if="loadingApt" class="p-8 text-center text-slate-400">
          <RefreshCw class="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-600" />
          <p>Scanning installed host packages...</p>
        </div>
        <table v-else class="np-table">
          <thead>
            <tr>
              <th>Package Name</th>
              <th>Installed Version</th>
              <th>Status</th>
              <th class="text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in rawPackages" :key="p.name" class="hover:bg-slate-50/80">
              <td class="font-mono font-semibold text-slate-900">{{ p.name }}</td>
              <td class="font-mono text-[11px] text-slate-600">{{ p.version }}</td>
              <td>
                <span class="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-700 font-mono">
                  {{ p.status }}
                </span>
              </td>
              <td class="text-right">
                <button
                  @click="removeRawApt(p.name)"
                  :disabled="isStreaming"
                  class="text-rose-600 hover:underline font-medium text-[11px]"
                >
                  Remove
                </button>
              </td>
            </tr>
            <tr v-if="rawPackages.length === 0">
              <td colspan="4" class="p-8 text-center text-slate-400">
                No installed packages match your filter.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Live Execution / Terminal Log Modal -->
    <div v-if="showLogModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div class="bg-slate-900 text-slate-100 rounded-lg shadow-2xl w-full max-w-3xl h-[72vh] flex flex-col border border-slate-700 overflow-hidden">
        <!-- Terminal Header -->
        <div class="px-4 py-2.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span
              :class="isStreaming ? 'bg-amber-500 animate-pulse' : (streamError ? 'bg-rose-500' : 'bg-emerald-500')"
              class="w-2.5 h-2.5 rounded-full"
            ></span>
            <span class="font-mono font-bold text-xs text-slate-200">{{ streamTitle }}</span>
          </div>
          <button
            v-if="!isStreaming"
            @click="showLogModal = false; reloadCurrentTab()"
            class="px-2.5 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 rounded text-slate-200 font-medium"
          >
            Close
          </button>
          <span v-else class="text-[11px] text-amber-400 font-mono flex items-center gap-1.5">
            <RefreshCw class="w-3 h-3 animate-spin" />
            <span>Processing...</span>
          </span>
        </div>

        <!-- Terminal Output -->
        <div ref="logContainer" class="flex-1 p-4 font-mono text-[11px] overflow-y-auto space-y-1 text-emerald-400 bg-slate-900 select-text">
          <div v-for="(line, i) in logLines" :key="i" class="leading-relaxed">
            <span v-if="line.startsWith('✓')" class="text-emerald-300 font-semibold">{{ line }}</span>
            <span v-else-if="line.startsWith('✗') || line.toLowerCase().includes('error')" class="text-rose-400 font-semibold">{{ line }}</span>
            <span v-else-if="line.startsWith('===') || line.startsWith('🎉')" class="text-amber-300 font-bold">{{ line }}</span>
            <span v-else-if="line.startsWith('!') || line.toLowerCase().includes('warning')" class="text-amber-400">{{ line }}</span>
            <span v-else class="text-slate-300">{{ line }}</span>
          </div>
        </div>

        <!-- Terminal Footer -->
        <div class="px-4 py-2 bg-slate-950 border-t border-slate-800 text-[11px] text-slate-500 flex items-center justify-between">
          <span>Execution logs streamed directly from host system package manager.</span>
          <span v-if="!isStreaming" class="text-emerald-400 font-medium">Ready</span>
        </div>
      </div>
    </div>

    <!-- Package Details Inspection Modal -->
    <div v-if="showInfoModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-lg p-5 space-y-3">
        <div class="flex items-center justify-between border-b pb-2">
          <h3 class="text-sm font-bold text-slate-900 flex items-center gap-1.5">
            <Box class="w-4 h-4 text-emerald-600" />
            <span>{{ selectedPackageInfo?.name }}</span>
          </h3>
          <button @click="showInfoModal = false" class="text-slate-400 hover:text-slate-600 text-sm">✕</button>
        </div>
        <div v-if="selectedPackageInfo" class="space-y-2 text-xs">
          <p class="text-slate-700">{{ selectedPackageInfo.description }}</p>
          <div class="grid grid-cols-2 gap-2 pt-2 border-t text-[11px]">
            <div><span class="text-slate-400">Available Version:</span> <span class="font-mono font-medium">{{ selectedPackageInfo.version }}</span></div>
            <div><span class="text-slate-400">Installed Version:</span> <span class="font-mono font-medium">{{ selectedPackageInfo.installed_version || 'Not installed' }}</span></div>
            <div><span class="text-slate-400">Section:</span> <span class="font-mono">{{ selectedPackageInfo.section || 'universe' }}</span></div>
            <div><span class="text-slate-400">Installed Size:</span> <span class="font-mono">{{ selectedPackageInfo.installed_size_kb ? `${selectedPackageInfo.installed_size_kb} KB` : 'N/A' }}</span></div>
            <div class="col-span-2 truncate"><span class="text-slate-400">Maintainer:</span> {{ selectedPackageInfo.maintainer || 'Ubuntu Developers' }}</div>
            <div class="col-span-2 truncate" v-if="selectedPackageInfo.homepage">
              <span class="text-slate-400">Homepage:</span> <a :href="selectedPackageInfo.homepage" target="_blank" class="text-emerald-600 hover:underline">{{ selectedPackageInfo.homepage }}</a>
            </div>
          </div>
        </div>
        <div class="flex justify-end pt-2 border-t">
          <button @click="showInfoModal = false" class="np-btn-secondary">Close</button>
        </div>
      </div>
    </div>

    <!-- Custom Package Install Modal -->
    <div v-if="showCustomModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-5 space-y-3">
        <h3 class="text-sm font-bold text-slate-900">Install Custom APT Package</h3>
        <p class="text-xs text-slate-500">Enter a standard Debian or Ubuntu package name (e.g. <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">htop</code>, <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">iftop</code>, <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700 font-mono">ncdu</code>).</p>
        <div>
          <label class="block text-[11px] font-medium text-slate-700 mb-1">Package Name</label>
          <input
            v-model="customPkgName"
            @keyup.enter="installCustomPackage"
            placeholder="e.g. htop"
            class="np-input font-mono"
          />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="showCustomModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="installCustomPackage" :disabled="!customPkgName.trim()" class="np-btn-primary">
            Install Package
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Box,
  Cpu,
  Download,
  FileCode,
  Layers,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Terminal,
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const { apiFetch, apiBase, authHeaders } = useApi()

const activeMainTab = ref('curated')
const activeCategory = ref('ALL')
const search = ref('')
const installedSearch = ref('')

const catalog = ref<any[]>([])
const rawPackages = ref<any[]>([])
const phpRuntimes = ref<any[]>([])
const pythonRuntimes = ref<any[]>([])

const loadingCatalog = ref(false)
const loadingApt = ref(false)
const loadingGlobal = ref(false)
const hasSearchedGlobal = ref(false)

const globalQuery = ref('')
const globalResults = ref<any[]>([])

const showInfoModal = ref(false)
const selectedPackageInfo = ref<any>(null)

const showLogModal = ref(false)
const streamTitle = ref('Package Operation')
const logLines = ref<string[]>([])
const isStreaming = ref(false)
const streamError = ref(false)
const logContainer = ref<HTMLElement | null>(null)

const showCustomModal = ref(false)
const customPkgName = ref('')

const sourceForm = reactive({
  name: 'redis-7.4',
  source_type: 'tarball',
  url: 'https://download.redis.io/redis-stable.tar.gz',
  branch_or_tag: '',
  configure_flags: '',
  build_tool: 'make',
  install_command: 'make install',
})

const sourcePresets = [
  {
    name: 'Redis Stable',
    desc: 'High performance in-memory database built from latest stable source tarball.',
    source_type: 'tarball',
    url: 'https://download.redis.io/redis-stable.tar.gz',
    branch_or_tag: '',
    configure_flags: '',
    build_tool: 'make',
    install_command: 'make install',
  },
  {
    name: 'Nginx Mainline',
    desc: 'Nginx HTTP server compiled with SSL, HTTP/2, and standard optimizations.',
    source_type: 'tarball',
    url: 'https://nginx.org/download/nginx-1.27.4.tar.gz',
    branch_or_tag: '',
    configure_flags: '--prefix=/usr/local/nginx --with-http_ssl_module --with-http_v2_module',
    build_tool: 'make',
    install_command: 'make install',
  },
  {
    name: 'Python 3.13 Source',
    desc: 'Official Python 3.13 source build compiled with full LTO optimizations.',
    source_type: 'tarball',
    url: 'https://www.python.org/ftp/python/3.13.2/Python-3.13.2.tar.xz',
    branch_or_tag: '',
    configure_flags: '--enable-optimizations --with-lto',
    build_tool: 'make',
    install_command: 'make altinstall',
  },
  {
    name: 'Node.js LTS Source',
    desc: 'Node.js V22 LTS JavaScript runtime compiled from official source archive.',
    source_type: 'tarball',
    url: 'https://nodejs.org/dist/v22.14.0/node-v22.14.0.tar.gz',
    branch_or_tag: '',
    configure_flags: '',
    build_tool: 'make',
    install_command: 'make install',
  },
]

const mainTabs = [
  { id: 'curated', label: 'Curated Stack', icon: Layers },
  { id: 'global', label: 'Linux & Ubuntu Store', icon: Box, badge: '60k+' },
  { id: 'source', label: 'Install from Source', icon: Terminal },
  { id: 'php', label: 'PHP Security & Versions', icon: FileCode },
  { id: 'python', label: 'Python Runtimes', icon: Cpu },
  { id: 'installed', label: 'Installed DPKG Packages', icon: Box },
]

const categories = [
  { id: 'ALL', label: 'All Software' },
  { id: 'Web Server', label: 'Web Servers' },
  { id: 'PHP', label: 'PHP Runtimes' },
  { id: 'Python', label: 'Python Runtimes' },
  { id: 'Database', label: 'Databases & Caches' },
  { id: 'FTP', label: 'FTP Servers' },
  { id: 'Runtime', label: 'Runtimes' },
  { id: 'Security', label: 'Security & Firewalls' },
  { id: 'Tools', label: 'Tools' },
  { id: 'Installed', label: 'Installed Only' },
]

function switchMainTab(tabId: string) {
  activeMainTab.value = tabId
  if (tabId === 'curated') {
    loadCatalog()
  } else if (tabId === 'php') {
    loadPhpRuntimes()
  } else if (tabId === 'python') {
    loadPythonRuntimes()
  } else if (tabId === 'installed') {
    loadInstalledPackages()
  }
}

function reloadCurrentTab() {
  switchMainTab(activeMainTab.value)
}

async function loadCatalog() {
  loadingCatalog.value = true
  try {
    const res = await apiFetch<any[]>(
      `/system/packages/catalog?category=${encodeURIComponent(activeCategory.value)}&search=${encodeURIComponent(search.value)}`
    )
    catalog.value = res || []
  } catch (err) {
    console.error('Failed to load package catalog:', err)
  } finally {
    loadingCatalog.value = false
  }
}

async function loadInstalledPackages() {
  loadingApt.value = true
  try {
    const res = await apiFetch<any>(`/system/packages?search=${encodeURIComponent(installedSearch.value)}`)
    rawPackages.value = res?.packages || []
  } catch (err) {
    console.error('Failed to load installed packages:', err)
  } finally {
    loadingApt.value = false
  }
}

async function loadPhpRuntimes() {
  try {
    const res = await apiFetch<any[]>('/system/runtimes/php')
    phpRuntimes.value = res || []
  } catch (err) {
    console.error('Failed to load PHP runtimes:', err)
  }
}

async function loadPythonRuntimes() {
  try {
    const res = await apiFetch<any[]>('/system/runtimes/python')
    pythonRuntimes.value = res || []
  } catch (err) {
    console.error('Failed to load Python runtimes:', err)
  }
}

async function searchGlobalStore() {
  const q = globalQuery.value.trim()
  if (!q) return
  loadingGlobal.value = true
  hasSearchedGlobal.value = true
  try {
    const res = await apiFetch<any>(`/system/packages/search?query=${encodeURIComponent(q)}&limit=50`)
    globalResults.value = res?.packages || []
  } catch (err) {
    console.error('Failed to query global APT repository:', err)
  } finally {
    loadingGlobal.value = false
  }
}

async function inspectPackageDetails(pkgName: string) {
  try {
    const res = await apiFetch<any>(`/system/packages/info/${encodeURIComponent(pkgName)}`)
    selectedPackageInfo.value = res
    showInfoModal.value = true
  } catch (err: any) {
    alert(`Unable to fetch package details: ${err.message}`)
  }
}

function populateSourceForm(preset: any) {
  sourceForm.name = preset.name.toLowerCase().replace(/\s+/g, '-')
  sourceForm.source_type = preset.source_type
  sourceForm.url = preset.url
  sourceForm.branch_or_tag = preset.branch_or_tag || ''
  sourceForm.configure_flags = preset.configure_flags || ''
  sourceForm.build_tool = preset.build_tool || 'make'
  sourceForm.install_command = preset.install_command || 'make install'
}

function onSearchInput() {
  clearTimeout((onSearchInput as any)._timer)
  ;(onSearchInput as any)._timer = setTimeout(() => {
    loadCatalog()
  }, 300)
}

function onInstalledSearchInput() {
  clearTimeout((onInstalledSearchInput as any)._timer)
  ;(onInstalledSearchInput as any)._timer = setTimeout(() => {
    loadInstalledPackages()
  }, 300)
}

function openCustomInstallModal() {
  customPkgName.value = ''
  showCustomModal.value = true
}

async function installCustomPackage() {
  const pkg = customPkgName.value.trim()
  if (!pkg) return
  showCustomModal.value = false
  await startSseStream(
    `Installing Package: ${pkg}`,
    `${apiBase}/system/packages/install`,
    { packages: [pkg] }
  )
}

async function installGlobalPackage(pkgName: string) {
  if (!confirm(`Install ${pkgName} from official Ubuntu/Debian repository?`)) return
  await startSseStream(
    `Installing Global Package: ${pkgName}`,
    `${apiBase}/system/packages/install`,
    { packages: [pkgName] }
  )
}

async function confirmInstall(item: any) {
  if (!confirm(`Are you sure you want to install ${item.name}?\n\nThis will install packages: ${item.apt_packages.join(', ')} and start any required services.`)) {
    return
  }
  await startSseStream(
    `Installing ${item.name}`,
    `${apiBase}/system/packages/curated/${item.slug}/install`,
    {}
  )
}

async function confirmUninstall(item: any) {
  if (!confirm(`Warning: Are you sure you want to uninstall ${item.name}?\n\nThis will stop its service and remove packages: ${item.apt_packages.join(', ')}.`)) {
    return
  }
  await startSseStream(
    `Uninstalling ${item.name}`,
    `${apiBase}/system/packages/curated/${item.slug}/uninstall`,
    {}
  )
}

async function installPhpVersion(version: string) {
  await startSseStream(
    `Installing PHP ${version} Runtime`,
    `${apiBase}/system/packages/curated/php${version}/install`,
    {}
  )
}

async function uninstallPhpVersion(version: string) {
  if (!confirm(`Are you sure you want to uninstall PHP ${version}?`)) return
  await startSseStream(
    `Uninstalling PHP ${version}`,
    `${apiBase}/system/packages/curated/php${version}/uninstall`,
    {}
  )
}

async function installPythonVersion(version: string) {
  await startSseStream(
    `Installing Python ${version} Runtime`,
    `${apiBase}/system/packages/curated/python${version}/install`,
    {}
  )
}

async function reinstallPythonVersion(version: string) {
  await startSseStream(
    `Reinstalling / Updating Python ${version}`,
    `${apiBase}/system/packages/curated/python${version}/install`,
    {}
  )
}

async function updatePhpSecurity() {
  if (!confirm('This will refresh Ondřej Surý PHP repository and install the latest security updates across all installed PHP runtimes. Proceed?')) return
  await startSseStream(
    'Updating PHP Runtimes with Latest Security Patches',
    `${apiBase}/system/packages/php/security-update`,
    {}
  )
}

async function updatePythonSecurity() {
  if (!confirm('This will update all installed Python runtimes to their latest security releases. Proceed?')) return
  await startSseStream(
    'Updating Python Runtimes with Security Patches',
    `${apiBase}/system/packages/python/security-update`,
    {}
  )
}

async function triggerSourceInstall(recipe: any) {
  if (!confirm(`Compile and install ${recipe.name} from source (${recipe.url})?`)) return
  await startSseStream(
    `Compiling & Installing ${recipe.name} from Source`,
    `${apiBase}/system/packages/source/install`,
    {
      name: recipe.name,
      source_type: recipe.source_type,
      url: recipe.url,
      branch_or_tag: recipe.branch_or_tag || null,
      configure_flags: recipe.configure_flags || null,
      build_tool: recipe.build_tool || 'make',
      install_command: recipe.install_command || 'make install',
    }
  )
}

async function removeRawApt(pkgName: string) {
  if (!confirm(`Are you sure you want to remove package ${pkgName}?`)) return
  await startSseStream(
    `Removing ${pkgName}`,
    `${apiBase}/system/packages/remove`,
    { packages: [pkgName] }
  )
}

async function updateRepoCache() {
  await startSseStream(
    'Updating APT Package Index (apt-get update)',
    `${apiBase}/system/packages/update-cache`,
    {}
  )
}

async function controlService(slug: string, action: string) {
  try {
    await apiFetch(`/system/packages/curated/${slug}/control`, {
      method: 'POST',
      body: { service: slug, action },
    })
    reloadCurrentTab()
  } catch (err: any) {
    alert(`Service action failed: ${err.data?.detail || err.message}`)
  }
}

async function consumeStream(resp: Response) {
  const reader = resp.body?.getReader()
  if (!reader) {
    logLines.value.push('[ERROR] Response body stream unavailable.')
    isStreaming.value = false
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''

    for (const chunk of chunks) {
      if (chunk.startsWith('data: ')) {
        try {
          const parsed = JSON.parse(chunk.slice(6))
          if (parsed.line) {
            logLines.value.push(parsed.line)
          }
          if (parsed.done) {
            if (parsed.returncode !== 0) {
              streamError.value = true
            }
          }
        } catch {
          // Ignore parse errors on partial chunks
        }
      }
    }

    nextTick(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    })
  }
}

async function startSseStream(title: string, url: string, body: any) {
  streamTitle.value = title
  logLines.value = [`[NexoPanel] Initializing operation: ${title}...`]
  showLogModal.value = true
  isStreaming.value = true
  streamError.value = false

  try {
    let requestUrl = url
    if (auth.token && typeof auth.token === 'string' && auth.token.trim()) {
      const sep = requestUrl.includes('?') ? '&' : '?'
      requestUrl = `${requestUrl}${sep}token=${encodeURIComponent(auth.token.trim())}`
    }

    const resp = await fetch(requestUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders('POST'),
      },
      body: JSON.stringify(body),
    })

    if (!resp.ok) {
      if (resp.status === 401) {
        logLines.value.push('[WARN] Stale session token detected. Attempting automatic session revalidation...')
        try {
          const meRes = await fetch(`${apiBase}/auth/me`, {
            method: 'GET',
            credentials: 'same-origin',
          })
          if (meRes.ok) {
            const meData = await meRes.json()
            if (meData?.access_token) {
              auth.setUser(meData, meData.access_token)
              logLines.value.push('[NexoPanel] ✓ Session revalidated successfully. Resuming operation...')
              const sep = url.includes('?') ? '&' : '?'
              const retryUrl = `${url}${sep}token=${encodeURIComponent(meData.access_token)}`
              const retryResp = await fetch(retryUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${meData.access_token}`,
                  ...authHeaders('POST'),
                },
                body: JSON.stringify(body),
              })
              if (retryResp.ok) {
                await consumeStream(retryResp)
                return
              }
            }
          }
        } catch {
          // Revalidation failed
        }

        auth.clearSession()
        logLines.value.push('[ERROR] Session expired or invalid authentication token. Redirecting to login...')
        streamError.value = true
        isStreaming.value = false
        setTimeout(() => {
          window.location.href = '/login'
        }, 1200)
        return
      }

      const errJson = await resp.json().catch(() => ({}))
      logLines.value.push(`[ERROR] Server responded with HTTP ${resp.status}: ${errJson.detail || 'Request failed'}`)
      streamError.value = true
      isStreaming.value = false
      return
    }

    await consumeStream(resp)
  } catch (err: any) {
    logLines.value.push(`[ERROR] Network or connection error: ${err.message}`)
    streamError.value = true
  } finally {
    isStreaming.value = false
  }
}

onMounted(() => {
  loadCatalog()
  loadPhpRuntimes()
  loadPythonRuntimes()
})
</script>
