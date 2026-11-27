<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <!-- Left Navigation Sidebar -->
    <aside class="w-52 shrink-0 border-r border-slate-200 bg-slate-50/70 py-3 flex flex-col justify-between">
      <div>
        <div class="px-4 pb-3 mb-2 border-b border-slate-200">
          <div class="flex items-center gap-2 font-bold text-slate-900 text-sm">
            <Box class="w-4 h-4 text-blue-600" />
            <span>Docker Manager</span>
          </div>
          <p class="text-[10px] text-slate-500 mt-0.5 font-medium">Containers · Images · Volumes · Stacks</p>
        </div>

        <nav class="space-y-0.5">
          <button
            v-for="item in navSections"
            :key="item.key"
            @click="activeSection = item.key"
            :class="activeSection === item.key ? 'text-blue-700 bg-blue-50/80 border-r-2 border-blue-600 font-semibold' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'"
            class="w-full flex items-center gap-2 text-left px-4 py-2.5 transition-colors"
          >
            <component :is="item.icon" class="w-3.5 h-3.5" />
            <span class="truncate">{{ item.label }}</span>
            <span v-if="item.key === 'containers' && containers.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-slate-200/80 text-slate-700 text-[10px] font-medium">{{ containers.length }}</span>
            <span v-else-if="item.key === 'images' && images.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700 text-[10px] font-semibold">{{ images.length }}</span>
            <span v-else-if="item.key === 'volumes' && volumes.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-semibold">{{ volumes.length }}</span>
            <span v-else-if="item.key === 'networks' && networks.length" class="ml-auto px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 text-[10px] font-semibold">{{ networks.length }}</span>
            <span v-else-if="item.key === 'templates'" class="ml-auto px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 text-[10px] font-semibold">1-Click</span>
          </button>
        </nav>
      </div>

      <!-- Quick Docker Engine Health & Service Controls Widget -->
      <div class="mx-3 mt-4 space-y-2">
        <div class="rounded border border-slate-200 bg-white p-2.5 space-y-1.5 shadow-2xs">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-medium text-slate-500">Docker Engine</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-semibold" :class="dockerStatus.active ? 'text-emerald-600' : (dockerStatus.installed ? 'text-rose-600' : 'text-amber-600')">
              <span class="w-2 h-2 rounded-full" :class="dockerStatus.active ? 'bg-emerald-500' : (dockerStatus.installed ? 'bg-rose-500' : 'bg-amber-500')"></span>
              {{ dockerStatus.active ? 'Running' : (dockerStatus.installed ? 'Stopped' : 'Not Installed') }}
            </span>
          </div>
          <div v-if="serverVersion" class="text-[10px] text-slate-600 flex justify-between">
            <span>Version:</span>
            <span class="font-mono font-semibold text-slate-800">{{ serverVersion }}</span>
          </div>
          <div class="text-[10px] text-slate-600 flex justify-between">
            <span>Containers:</span>
            <span class="font-semibold text-slate-800">{{ runningCount }} running / {{ containers.length }} total</span>
          </div>
        </div>

        <button
          v-if="!dockerStatus.installed"
          @click="installDocker"
          :disabled="busy === 'install_docker'"
          class="w-full flex items-center justify-center gap-1.5 rounded border border-blue-600 bg-blue-600 hover:bg-blue-700 text-white py-1.5 px-2 text-[11px] font-medium transition-colors shadow-2xs disabled:opacity-50"
        >
          <RotateCw :class="{ 'animate-spin': busy === 'install_docker' }" class="w-3 h-3" />
          <span>{{ busy === 'install_docker' ? 'Installing...' : 'Install Docker (1-Click)' }}</span>
        </button>
        <button
          v-else
          @click="controlService(dockerStatus.active ? 'restart' : 'start')"
          :disabled="busy === 'service'"
          :class="dockerStatus.active ? 'text-slate-700 border-slate-200 hover:bg-slate-100' : 'text-emerald-700 border-emerald-300 hover:bg-emerald-50'"
          class="w-full flex items-center justify-center gap-1.5 rounded border bg-white py-1.5 px-2 text-[11px] font-medium transition-colors disabled:opacity-50"
        >
          <Power class="w-3 h-3" />
          <span>{{ dockerStatus.active ? 'Restart Engine' : 'Start Engine' }}</span>
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
            <span v-if="dockerStatus.active" class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Engine Active
            </span>
            <span v-else-if="dockerStatus.installed" class="px-2 py-0.5 rounded bg-rose-50 text-rose-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span> Service Inactive
            </span>
            <span v-else class="px-2 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Engine Not Installed
            </span>
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">{{ sectionSubtitle }}</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button @click="refreshAll" :disabled="loading" class="np-btn-secondary" title="Refresh all Docker data">
            <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>

          <!-- Contextual Action Buttons -->
          <button @click="showDeployModal = true" class="np-btn-primary">
            <Plus class="w-3.5 h-3.5" />
            <span>Deploy Container</span>
          </button>
          <button @click="showPullModal = true" class="np-btn-secondary">
            <Download class="w-3.5 h-3.5" />
            <span>Pull Image</span>
          </button>
          <button @click="activeSection = 'prune'" class="np-btn-secondary text-slate-700">
            <Trash2 class="w-3.5 h-3.5 text-slate-500" />
            <span>Prune</span>
          </button>
        </div>
      </div>

      <!-- Alerts / Feedback Notification -->
      <div v-if="noticeMessage" class="mb-4 p-3 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-[11px] flex items-center justify-between">
        <div class="flex items-center gap-2">
          <CheckCircle2 class="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{{ noticeMessage }}</span>
        </div>
        <button @click="noticeMessage = ''" class="text-emerald-600 hover:text-emerald-800"><X class="w-3.5 h-3.5" /></button>
      </div>

      <div v-if="errorMessage" class="mb-4 p-3 rounded-md bg-rose-50 border border-rose-200 text-rose-800 text-[11px] flex items-center justify-between">
        <div class="flex items-center gap-2">
          <AlertCircle class="w-4 h-4 text-rose-600 shrink-0" />
          <span>{{ errorMessage }}</span>
        </div>
        <button @click="errorMessage = ''" class="text-rose-600 hover:text-rose-800"><X class="w-3.5 h-3.5" /></button>
      </div>

      <!-- Inactive / Not Installed Warning Banner -->
      <div v-if="!dockerStatus.active" class="mb-4 rounded-lg border p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-3" :class="dockerStatus.installed ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-blue-50 border-blue-200 text-blue-900'">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-full flex items-center justify-center shrink-0" :class="dockerStatus.installed ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'">
            <AlertTriangle class="w-5 h-5" />
          </div>
          <div>
            <h3 class="font-bold text-xs">{{ dockerStatus.installed ? 'Docker Service is Stopped' : 'Docker Engine is Not Installed' }}</h3>
            <p class="text-[11px] opacity-80 mt-0.5">
              {{ dockerStatus.installed ? 'Start the Docker daemon to manage running containers and compose stacks.' : 'Install Docker Engine and Docker Compose with 1-click to enable containerized apps.' }}
            </p>
          </div>
        </div>
        <button
          v-if="!dockerStatus.installed"
          @click="installDocker"
          :disabled="busy === 'install_docker'"
          class="shrink-0 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition-colors flex items-center gap-1.5 shadow-2xs disabled:opacity-50"
        >
          <RotateCw :class="{ 'animate-spin': busy === 'install_docker' }" class="w-3.5 h-3.5" />
          <span>{{ busy === 'install_docker' ? 'Installing Engine...' : 'Install Docker Now' }}</span>
        </button>
        <button
          v-else
          @click="controlService('start')"
          :disabled="busy === 'service'"
          class="shrink-0 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs transition-colors flex items-center gap-1.5 shadow-2xs disabled:opacity-50"
        >
          <Play class="w-3.5 h-3.5" />
          <span>Start Docker Service</span>
        </button>
      </div>

      <!-- Metric Cards Banner -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <div class="rounded border border-slate-200 bg-slate-50/50 p-3">
          <div class="flex items-center justify-between text-slate-500 mb-1">
            <span class="text-[11px] font-medium">Containers</span>
            <Box class="w-4 h-4 text-blue-500" />
          </div>
          <div class="text-base font-bold text-slate-900">{{ runningCount }} <span class="text-xs font-normal text-slate-500">/ {{ containers.length }}</span></div>
          <div class="text-[10px] text-slate-500 mt-1 flex items-center gap-1.5">
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500"></span> {{ runningCount }} Running
            <span class="inline-block w-1.5 h-1.5 rounded-full bg-slate-400 ml-1"></span> {{ containers.length - runningCount }} Stopped
          </div>
        </div>

        <div class="rounded border border-slate-200 bg-slate-50/50 p-3">
          <div class="flex items-center justify-between text-slate-500 mb-1">
            <span class="text-[11px] font-medium">Images Cached</span>
            <Layers class="w-4 h-4 text-indigo-500" />
          </div>
          <div class="text-base font-bold text-slate-900">{{ images.length }} <span class="text-xs font-normal text-slate-500">Images</span></div>
          <div class="text-[10px] text-slate-500 mt-1 truncate">
            {{ totalImageSizeFormatted }} Total Size
          </div>
        </div>

        <div class="rounded border border-slate-200 bg-slate-50/50 p-3">
          <div class="flex items-center justify-between text-slate-500 mb-1">
            <span class="text-[11px] font-medium">Storage Volumes</span>
            <HardDrive class="w-4 h-4 text-emerald-500" />
          </div>
          <div class="text-base font-bold text-slate-900">{{ volumes.length }} <span class="text-xs font-normal text-slate-500">Volumes</span></div>
          <div class="text-[10px] text-slate-500 mt-1 truncate">
            {{ networks.length }} Virtual Networks
          </div>
        </div>

        <div class="rounded border border-slate-200 bg-slate-50/50 p-3">
          <div class="flex items-center justify-between text-slate-500 mb-1">
            <span class="text-[11px] font-medium">Host Engine</span>
            <Cpu class="w-4 h-4 text-purple-500" />
          </div>
          <div class="text-base font-bold text-slate-900 truncate">{{ hostInfoText }}</div>
          <div class="text-[10px] text-slate-500 mt-1 font-mono truncate">
            {{ dockerStatus.info?.DockerRootDir || '/var/lib/docker' }}
          </div>
        </div>
      </div>

      <!-- SECTION: CONTAINERS -->
      <div v-if="activeSection === 'containers'" class="space-y-3">
        <!-- Subheader with Filters & Search -->
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-1 bg-slate-100 p-0.5 rounded border border-slate-200">
            <button
              v-for="f in containerFilters"
              :key="f.key"
              @click="containerFilter = f.key"
              :class="containerFilter === f.key ? 'bg-white text-slate-900 font-semibold shadow-2xs' : 'text-slate-600 hover:text-slate-900'"
              class="px-2.5 py-1 rounded text-[11px] transition-colors"
            >
              {{ f.label }} ({{ f.count }})
            </button>
          </div>

          <div class="flex items-center gap-2">
            <div class="relative w-48 sm:w-64">
              <Search class="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400" />
              <input
                v-model="containerSearch"
                type="text"
                placeholder="Search container or image..."
                class="np-input pl-8 py-1 text-xs w-full"
              />
            </div>
            <button @click="showDeployModal = true" class="np-btn-primary py-1">
              <Plus class="w-3.5 h-3.5" />
              <span>New</span>
            </button>
          </div>
        </div>

        <!-- Containers Table -->
        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th class="w-12 text-center">Status</th>
                <th>Name / ID</th>
                <th>Image</th>
                <th>Ports</th>
                <th class="w-36">Resource Usage</th>
                <th>Created / Uptime</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in filteredContainers" :key="c.ID" class="hover:bg-slate-50/80 transition-colors">
                <!-- Status Dot -->
                <td class="text-center">
                  <span
                    class="inline-block w-2.5 h-2.5 rounded-full"
                    :class="c.State === 'running' ? 'bg-emerald-500 ring-2 ring-emerald-100' : (c.State === 'paused' ? 'bg-amber-500' : 'bg-slate-300')"
                    :title="c.State || c.Status"
                  ></span>
                </td>

                <!-- Name & ID -->
                <td>
                  <div class="font-bold text-slate-900 flex items-center gap-1.5">
                    <span>{{ formatContainerName(c.Names) }}</span>
                    <span v-if="c.State === 'running'" class="px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800 text-[9px] font-semibold">Running</span>
                    <span v-else-if="c.State === 'paused'" class="px-1.5 py-0.2 rounded bg-amber-100 text-amber-800 text-[9px] font-semibold">Paused</span>
                    <span v-else class="px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 text-[9px] font-medium">Exited</span>
                  </div>
                  <div class="flex items-center gap-1 font-mono text-[10px] text-slate-400 mt-0.5">
                    <span>{{ (c.ID || '').slice(0, 12) }}</span>
                    <button @click="copyText(c.ID)" class="hover:text-slate-600" title="Copy container ID">
                      <Copy class="w-2.5 h-2.5" />
                    </button>
                  </div>
                </td>

                <!-- Image -->
                <td>
                  <span class="font-mono text-[11px] text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200/50">
                    {{ c.Image }}
                  </span>
                </td>

                <!-- Ports -->
                <td>
                  <div v-if="c.parsed_ports && c.parsed_ports.length" class="flex flex-wrap gap-1">
                    <div
                      v-for="(p, idx) in c.parsed_ports"
                      :key="idx"
                      class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[10px] border border-slate-200"
                    >
                      <span v-if="p.host_port" class="font-semibold text-slate-900">{{ p.host_port }}</span>
                      <span v-if="p.host_port">→</span>
                      <span>{{ p.container_port }}/{{ p.protocol }}</span>
                      <a
                        v-if="p.host_port && isWebPort(p.host_port)"
                        :href="`http://${hostIp}:${p.host_port}`"
                        target="_blank"
                        class="text-blue-600 hover:text-blue-800 ml-0.5"
                        title="Open in browser"
                      >
                        <ExternalLink class="w-2.5 h-2.5" />
                      </a>
                    </div>
                  </div>
                  <span v-else-if="c.Ports" class="font-mono text-[10px] text-slate-600">{{ c.Ports }}</span>
                  <span v-else class="text-slate-400 italic text-[10px]">None exposed</span>
                </td>

                <!-- Resource Usage -->
                <td>
                  <div v-if="c.State === 'running'" class="space-y-1">
                    <div class="flex justify-between text-[10px] text-slate-600">
                      <span>CPU: <strong class="text-slate-800">{{ c.cpu_perc || '0%' }}</strong></span>
                      <span>Mem: <strong class="text-slate-800">{{ c.mem_perc || '0%' }}</strong></span>
                    </div>
                    <div class="w-full h-1 bg-slate-100 rounded-full overflow-hidden flex">
                      <div class="bg-blue-500 h-full" :style="{ width: c.mem_perc || '2%' }"></div>
                    </div>
                    <div class="text-[9px] text-slate-400 truncate">{{ c.mem_usage || '0MB' }}</div>
                  </div>
                  <span v-else class="text-slate-400 text-[10px] italic">Stopped</span>
                </td>

                <!-- Created / Uptime -->
                <td class="text-slate-600 text-[11px]">
                  <div>{{ c.Status }}</div>
                  <div v-if="c.Created" class="text-[10px] text-slate-400 mt-0.5">{{ c.Created }}</div>
                </td>

                <!-- Actions -->
                <td class="text-right">
                  <div class="flex items-center justify-end gap-1">
                    <!-- Lifecycle buttons -->
                    <button
                      v-if="c.State !== 'running'"
                      @click="controlContainer(c.ID, 'start')"
                      :disabled="busy === c.ID"
                      class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 font-semibold text-[11px] transition-colors flex items-center gap-1"
                      title="Start Container"
                    >
                      <Play class="w-3 h-3" />
                      <span>Start</span>
                    </button>
                    <button
                      v-else
                      @click="controlContainer(c.ID, 'stop')"
                      :disabled="busy === c.ID"
                      class="px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 border border-amber-200 font-semibold text-[11px] transition-colors flex items-center gap-1"
                      title="Stop Container"
                    >
                      <Square class="w-3 h-3" />
                      <span>Stop</span>
                    </button>

                    <button
                      @click="controlContainer(c.ID, 'restart')"
                      :disabled="busy === c.ID"
                      class="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                      title="Restart Container"
                    >
                      <RotateCw class="w-3.5 h-3.5" />
                    </button>

                    <button
                      @click="openLogs(c)"
                      class="p-1 rounded text-slate-600 hover:text-blue-600 hover:bg-blue-50"
                      title="View Container Logs"
                    >
                      <Terminal class="w-3.5 h-3.5" />
                    </button>

                    <button
                      v-if="c.State === 'running'"
                      @click="openExec(c)"
                      class="p-1 rounded text-slate-600 hover:text-purple-600 hover:bg-purple-50"
                      title="Execute Command inside Container"
                    >
                      <Cpu class="w-3.5 h-3.5" />
                    </button>

                    <button
                      @click="openInspect(c)"
                      class="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                      title="Inspect Container Config"
                    >
                      <Eye class="w-3.5 h-3.5" />
                    </button>

                    <button
                      @click="confirmRemoveContainer(c)"
                      :disabled="busy === c.ID"
                      class="p-1 rounded text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                      title="Delete Container"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>

              <tr v-if="!filteredContainers.length">
                <td colspan="7" class="text-center text-slate-400 py-8">
                  <Box class="w-8 h-8 mx-auto text-slate-300 mb-2" />
                  <p class="font-medium">No containers found.</p>
                  <p class="text-[10px] text-slate-400 mt-1">Deploy your first container or run a 1-click app stack!</p>
                  <button @click="showDeployModal = true" class="np-btn-primary mt-3 text-xs">+ Deploy Container</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SECTION: IMAGES -->
      <div v-else-if="activeSection === 'images'" class="space-y-4">
        <!-- Quick Pull Banner -->
        <div class="rounded border border-blue-200 bg-blue-50/50 p-3.5 space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-bold text-blue-900 text-xs flex items-center gap-1.5">
              <Download class="w-4 h-4 text-blue-600" />
              Quick Pull Official Docker Hub Images
            </span>
            <button @click="showPullModal = true" class="np-btn-primary py-1">+ Custom Pull</button>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="chip in popularPullChips"
              :key="chip"
              @click="quickPull(chip)"
              :disabled="busy === 'pull'"
              class="px-2 py-1 rounded bg-white hover:bg-blue-100 border border-blue-200 text-blue-800 text-[11px] font-mono transition-colors flex items-center gap-1"
            >
              <span>{{ chip }}</span>
              <Download class="w-2.5 h-2.5 text-blue-500" />
            </button>
          </div>
        </div>

        <!-- Images Table -->
        <div class="rounded border border-slate-200 overflow-hidden">
          <div class="px-4 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <span class="font-semibold text-slate-900">Local Images ({{ images.length }})</span>
            <div class="relative w-48">
              <Search class="w-3.5 h-3.5 absolute left-2 top-2 text-slate-400" />
              <input v-model="imageSearch" type="text" placeholder="Filter images..." class="np-input pl-7 py-1 text-xs w-full" />
            </div>
          </div>
          <table class="np-table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Tag</th>
                <th>Image ID</th>
                <th>Virtual Size</th>
                <th>Created</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="img in filteredImages" :key="img.ID">
                <td class="font-bold text-slate-900 flex items-center gap-1.5">
                  <Layers class="w-3.5 h-3.5 text-blue-500 shrink-0" />
                  <span>{{ img.Repository || '<none>' }}</span>
                </td>
                <td>
                  <span class="font-mono text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded border border-slate-200">
                    {{ img.Tag || '<none>' }}
                  </span>
                </td>
                <td class="font-mono text-[10px] text-slate-500">
                  {{ formatShortId(img.ID) }}
                </td>
                <td class="font-semibold text-slate-800">{{ img.Size }}</td>
                <td class="text-slate-500 text-[11px]">{{ img.CreatedAt || 'N/A' }}</td>
                <td class="text-right space-x-1">
                  <button
                    @click="runFromImage(img)"
                    class="px-2 py-0.8 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 text-[11px] font-medium"
                    title="Run Container from Image"
                  >
                    Run Container
                  </button>
                  <button
                    @click="deleteImage(img)"
                    :disabled="busy === img.ID"
                    class="p-1 rounded text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                    title="Delete Image"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredImages.length">
                <td colspan="6" class="text-center text-slate-400 py-6">No images downloaded yet.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SECTION: VOLUMES & STORAGE -->
      <div v-else-if="activeSection === 'volumes'" class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-xs font-bold text-slate-900">Persistent Storage Volumes</h2>
            <p class="text-[10px] text-slate-500">Manage persistent data volumes mapped into containers.</p>
          </div>
          <button @click="showCreateVolumeModal = true" class="np-btn-primary">+ Create Volume</button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Volume Name</th>
                <th>Driver</th>
                <th>Scope</th>
                <th>Mountpoint Path</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="v in volumes" :key="v.Name">
                <td class="font-bold text-slate-900 font-mono flex items-center gap-1.5">
                  <HardDrive class="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <span>{{ v.Name }}</span>
                </td>
                <td><span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[10px]">{{ v.Driver || 'local' }}</span></td>
                <td><span class="text-slate-600 text-[11px]">{{ v.Scope || 'local' }}</span></td>
                <td class="font-mono text-[10px] text-slate-500 truncate max-w-xs">{{ v.Mountpoint || 'Default' }}</td>
                <td class="text-right">
                  <button
                    @click="deleteVolume(v.Name)"
                    :disabled="busy === v.Name"
                    class="p-1 rounded text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                    title="Delete Volume"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
              <tr v-if="!volumes.length">
                <td colspan="5" class="text-center text-slate-400 py-6">No Docker volumes found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SECTION: NETWORKS -->
      <div v-else-if="activeSection === 'networks'" class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-xs font-bold text-slate-900">Virtual Networks</h2>
            <p class="text-[10px] text-slate-500">Manage isolated container networks and bridges.</p>
          </div>
          <button @click="showCreateNetworkModal = true" class="np-btn-primary">+ Create Network</button>
        </div>

        <div class="rounded border border-slate-200 overflow-hidden">
          <table class="np-table">
            <thead>
              <tr>
                <th>Network Name</th>
                <th>Network ID</th>
                <th>Driver</th>
                <th>Scope</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="net in networks" :key="net.ID || net.Name">
                <td class="font-bold text-slate-900 flex items-center gap-1.5">
                  <Network class="w-3.5 h-3.5 text-purple-600 shrink-0" />
                  <span>{{ net.Name }}</span>
                </td>
                <td class="font-mono text-[10px] text-slate-500">{{ formatShortId(net.ID) }}</td>
                <td>
                  <span class="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 font-mono text-[10px] border border-purple-200/50">
                    {{ net.Driver }}
                  </span>
                </td>
                <td class="text-slate-600 text-[11px]">{{ net.Scope }}</td>
                <td class="text-right">
                  <button
                    v-if="!['bridge', 'host', 'none'].includes(net.Name)"
                    @click="deleteNetwork(net.Name)"
                    :disabled="busy === net.Name"
                    class="p-1 rounded text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                    title="Delete Network"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                  <span v-else class="text-slate-400 text-[10px] italic">System</span>
                </td>
              </tr>
              <tr v-if="!networks.length">
                <td colspan="5" class="text-center text-slate-400 py-6">No networks found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- SECTION: 1-CLICK APP TEMPLATES -->
      <div v-else-if="activeSection === 'templates'" class="space-y-4">
        <!-- Category Filter -->
        <div class="flex flex-wrap items-center gap-1.5 pb-1 border-b border-slate-200">
          <button
            v-for="cat in templateCategories"
            :key="cat"
            @click="templateCategory = cat"
            :class="templateCategory === cat ? 'bg-blue-600 text-white font-semibold' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'"
            class="px-2.5 py-1 rounded-full text-[11px] transition-colors"
          >
            {{ cat }}
          </button>
        </div>

        <!-- Templates Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          <div
            v-for="tmpl in filteredTemplates"
            :key="tmpl.id"
            class="rounded-lg border border-slate-200 hover:border-blue-400 bg-white p-4 shadow-2xs hover:shadow-xs transition-all flex flex-col justify-between"
          >
            <div>
              <div class="flex items-start justify-between gap-2 mb-2">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 border border-blue-200 flex items-center justify-center font-bold">
                    <component :is="getTemplateIcon(tmpl.icon)" class="w-4 h-4" />
                  </div>
                  <div>
                    <h3 class="font-bold text-xs text-slate-900 leading-tight">{{ tmpl.name }}</h3>
                    <span class="text-[10px] text-slate-500">{{ tmpl.category }}</span>
                  </div>
                </div>
                <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[9px] font-mono font-medium">
                  {{ (tmpl.default_ports && tmpl.default_ports[0]) || 'internal' }}
                </span>
              </div>
              <p class="text-[11px] text-slate-600 mb-3 leading-relaxed">{{ tmpl.description }}</p>
              <div class="font-mono text-[10px] text-slate-500 bg-slate-50 p-1.5 rounded border border-slate-100 mb-3 truncate">
                Image: <strong class="text-slate-800">{{ tmpl.image }}</strong>
              </div>
            </div>

            <button
              @click="openDeployTemplate(tmpl)"
              class="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs transition-colors shadow-2xs"
            >
              <Sparkles class="w-3.5 h-3.5" />
              <span>1-Click Deploy</span>
            </button>
          </div>
        </div>
      </div>

      <!-- SECTION: DOCKER COMPOSE -->
      <div v-else-if="activeSection === 'compose'" class="space-y-4">
        <div class="rounded border border-slate-200 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-xs font-bold text-slate-900">Docker Compose / Multi-Container Stacks</h2>
              <p class="text-[10px] text-slate-500">Deploy declarative multi-container environments using docker-compose.yml specifications.</p>
            </div>
            <div class="flex items-center gap-2">
              <button @click="loadComposeSample('nginx_redis')" class="np-btn-secondary text-[10px] py-1">Load Nginx + Redis</button>
              <button @click="loadComposeSample('wordpress')" class="np-btn-secondary text-[10px] py-1">Load WordPress + MySQL</button>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block text-[10px] font-semibold text-slate-700 mb-1">Stack / Project Name</label>
              <input v-model="composeProject" type="text" placeholder="e.g. my-app-stack" class="np-input w-full text-xs" />
            </div>
          </div>

          <div>
            <label class="block text-[10px] font-semibold text-slate-700 mb-1">docker-compose.yml Configuration</label>
            <textarea
              v-model="composeYaml"
              rows="12"
              class="font-mono text-xs w-full p-3 rounded border border-slate-300 bg-slate-950 text-emerald-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="version: '3.8'&#10;services:&#10;  ..."
            ></textarea>
          </div>

          <div class="flex items-center justify-between pt-2">
            <label class="flex items-center gap-2 text-[11px] text-slate-700 cursor-pointer">
              <input v-model="composeRemoveVolumes" type="checkbox" class="rounded border-slate-300 text-blue-600" />
              <span>Remove named volumes on teardown</span>
            </label>
            <div class="space-x-2">
              <button
                @click="teardownCompose"
                :disabled="busy === 'compose_down' || !composeProject"
                class="np-btn-secondary text-rose-700 hover:bg-rose-50"
              >
                <span>Tear Down Stack</span>
              </button>
              <button
                @click="deployCompose"
                :disabled="busy === 'compose_deploy' || !composeProject || !composeYaml"
                class="np-btn-primary"
              >
                <RotateCw :class="{ 'animate-spin': busy === 'compose_deploy' }" class="w-3.5 h-3.5" />
                <span>Deploy Stack</span>
              </button>
            </div>
          </div>

          <div v-if="composeOutput" class="mt-3 p-3 rounded bg-slate-900 text-slate-100 font-mono text-[10px] whitespace-pre-wrap max-h-48 overflow-y-auto">
            {{ composeOutput }}
          </div>
        </div>
      </div>

      <!-- SECTION: SYSTEM PRUNE & CLEANUP -->
      <div v-else-if="activeSection === 'prune'" class="space-y-4">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div>
            <h2 class="text-xs font-bold text-slate-900 flex items-center gap-1.5">
              <Trash2 class="w-4 h-4 text-rose-600" />
              Docker System Cleanup & Prune
            </h2>
            <p class="text-[10px] text-slate-500 mt-0.5">Reclaim host storage disk space by pruning unused and stopped Docker resources.</p>
          </div>

          <!-- Disk usage breakdown -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="p-3 rounded border border-slate-200 bg-slate-50">
              <div class="text-[10px] text-slate-500 font-medium">Images</div>
              <div class="text-sm font-bold text-slate-900 mt-1">{{ images.length }} local images</div>
            </div>
            <div class="p-3 rounded border border-slate-200 bg-slate-50">
              <div class="text-[10px] text-slate-500 font-medium">Stopped Containers</div>
              <div class="text-sm font-bold text-slate-900 mt-1">{{ containers.length - runningCount }} stopped</div>
            </div>
            <div class="p-3 rounded border border-slate-200 bg-slate-50">
              <div class="text-[10px] text-slate-500 font-medium">Volumes</div>
              <div class="text-sm font-bold text-slate-900 mt-1">{{ volumes.length }} persistent</div>
            </div>
            <div class="p-3 rounded border border-slate-200 bg-slate-50">
              <div class="text-[10px] text-slate-500 font-medium">Networks</div>
              <div class="text-sm font-bold text-slate-900 mt-1">{{ networks.length }} networks</div>
            </div>
          </div>

          <div class="space-y-2 border-t border-slate-200 pt-3">
            <div class="font-semibold text-slate-800 text-xs">Cleanup Options</div>
            <label class="flex items-center gap-2 text-slate-700 cursor-pointer">
              <input v-model="pruneAllImages" type="checkbox" class="rounded border-slate-300 text-blue-600" />
              <span>Prune all unused images (not just dangling ones) <code>--all</code></span>
            </label>
            <label class="flex items-center gap-2 text-slate-700 cursor-pointer">
              <input v-model="pruneVolumes" type="checkbox" class="rounded border-slate-300 text-blue-600" />
              <span>Prune all unused storage volumes <code>--volumes</code></span>
            </label>
          </div>

          <div class="bg-amber-50 border border-amber-200 text-amber-900 p-3 rounded text-[11px] flex items-center gap-2">
            <AlertTriangle class="w-4 h-4 text-amber-600 shrink-0" />
            <span>Pruning will permanently delete stopped containers, unused networks, and unreferenced cache layers.</span>
          </div>

          <div class="flex items-center justify-end">
            <button
              @click="runSystemPrune"
              :disabled="busy === 'prune'"
              class="np-btn-danger px-4 py-2"
            >
              <RotateCw :class="{ 'animate-spin': busy === 'prune' }" class="w-3.5 h-3.5" />
              <span>{{ busy === 'prune' ? 'Pruning System...' : 'Run Docker System Prune' }}</span>
            </button>
          </div>

          <div v-if="pruneOutput" class="p-3 rounded bg-slate-950 text-emerald-400 font-mono text-[10px] whitespace-pre-wrap max-h-48 overflow-y-auto">
            {{ pruneOutput }}
          </div>
        </div>
      </div>
    </div>

    <!-- MODAL: DEPLOY CONTAINER -->
    <div v-if="showDeployModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-xl max-h-[90vh] overflow-y-auto flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Box class="w-4 h-4 text-blue-600" />
            <span>Deploy Docker Container</span>
          </div>
          <button @click="showDeployModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3.5 text-xs">
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Docker Image <span class="text-rose-500">*</span></label>
            <input v-model="deployForm.image" type="text" placeholder="e.g. nginx:alpine or redis:7-alpine" class="np-input w-full" />
            <div class="flex flex-wrap gap-1 mt-1.5">
              <button
                v-for="sug in ['nginx:alpine', 'redis:7-alpine', 'postgres:16-alpine', 'node:20-alpine']"
                :key="sug"
                @click="deployForm.image = sug"
                class="px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 font-mono text-[9px]"
              >
                {{ sug }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Container Name (optional)</label>
              <input v-model="deployForm.name" type="text" placeholder="e.g. my-web-app" class="np-input w-full" />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Restart Policy</label>
              <select v-model="deployForm.restart_policy" class="np-input w-full">
                <option value="unless-stopped">unless-stopped (Recommended)</option>
                <option value="always">always</option>
                <option value="on-failure">on-failure</option>
                <option value="no">no</option>
              </select>
            </div>
          </div>

          <!-- Port Mappings -->
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="font-semibold text-slate-700">Port Mappings (Host : Container)</label>
              <button @click="addPortMapping" class="text-blue-600 hover:underline text-[10px]">+ Add Port</button>
            </div>
            <div class="space-y-1.5">
              <div v-for="(p, idx) in deployForm.ports" :key="idx" class="flex items-center gap-2">
                <input v-model="p.host" type="text" placeholder="Host Port (e.g. 8080)" class="np-input flex-1" />
                <span>:</span>
                <input v-model="p.container" type="text" placeholder="Container Port (e.g. 80)" class="np-input flex-1" />
                <button @click="deployForm.ports.splice(idx, 1)" class="text-rose-500 hover:text-rose-700 p-1"><X class="w-3.5 h-3.5" /></button>
              </div>
              <div v-if="!deployForm.ports.length" class="text-[10px] text-slate-400 italic">No custom port mappings configured.</div>
            </div>
          </div>

          <!-- Environment Variables -->
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="font-semibold text-slate-700">Environment Variables</label>
              <button @click="addEnvVar" class="text-blue-600 hover:underline text-[10px]">+ Add Env</button>
            </div>
            <div class="space-y-1.5">
              <div v-for="(e, idx) in deployForm.envs" :key="idx" class="flex items-center gap-2">
                <input v-model="e.key" type="text" placeholder="KEY (e.g. MYSQL_ROOT_PASSWORD)" class="np-input flex-1 font-mono text-[11px]" />
                <span>=</span>
                <input v-model="e.value" type="text" placeholder="VALUE" class="np-input flex-1" />
                <button @click="deployForm.envs.splice(idx, 1)" class="text-rose-500 hover:text-rose-700 p-1"><X class="w-3.5 h-3.5" /></button>
              </div>
              <div v-if="!deployForm.envs.length" class="text-[10px] text-slate-400 italic">No environment variables.</div>
            </div>
          </div>

          <!-- Volume Mounts -->
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="font-semibold text-slate-700">Volume Mounts (Host Path / Volume Name : Container Path)</label>
              <button @click="addVolumeMount" class="text-blue-600 hover:underline text-[10px]">+ Add Volume</button>
            </div>
            <div class="space-y-1.5">
              <div v-for="(v, idx) in deployForm.volumes" :key="idx" class="flex items-center gap-2">
                <input v-model="v.host" type="text" placeholder="Host Path or Volume Name (e.g. app_data)" class="np-input flex-1 font-mono text-[11px]" />
                <span>:</span>
                <input v-model="v.container" type="text" placeholder="Container Path (e.g. /data)" class="np-input flex-1 font-mono text-[11px]" />
                <button @click="deployForm.volumes.splice(idx, 1)" class="text-rose-500 hover:text-rose-700 p-1"><X class="w-3.5 h-3.5" /></button>
              </div>
              <div v-if="!deployForm.volumes.length" class="text-[10px] text-slate-400 italic">No persistent volume mounts.</div>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Memory Limit (optional)</label>
              <input v-model="deployForm.memory_limit" type="text" placeholder="e.g. 512m or 1g" class="np-input w-full" />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Command / Entrypoint Override</label>
              <input v-model="deployForm.command" type="text" placeholder="optional custom command" class="np-input w-full" />
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showDeployModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitDeployContainer" :disabled="busy === 'deploy' || !deployForm.image" class="np-btn-primary">
            <RotateCw :class="{ 'animate-spin': busy === 'deploy' }" class="w-3.5 h-3.5" />
            <span>Deploy & Start</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: PULL IMAGE -->
    <div v-if="showPullModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-md flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Download class="w-4 h-4 text-blue-600" />
            <span>Pull Docker Image</span>
          </div>
          <button @click="showPullModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3 text-xs">
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Image Reference (with tag)</label>
            <input v-model="pullImageRef" type="text" placeholder="e.g. redis:7-alpine or nginx:alpine" class="np-input w-full font-mono" />
          </div>

          <div>
            <span class="text-[10px] text-slate-500 font-semibold block mb-1">Suggested Images:</span>
            <div class="flex flex-wrap gap-1">
              <button
                v-for="s in popularPullChips"
                :key="s"
                @click="pullImageRef = s"
                class="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 font-mono text-[10px] text-slate-700"
              >
                {{ s }}
              </button>
            </div>
          </div>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showPullModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitPullImage" :disabled="busy === 'pull' || !pullImageRef" class="np-btn-primary">
            <RotateCw :class="{ 'animate-spin': busy === 'pull' }" class="w-3.5 h-3.5" />
            <span>{{ busy === 'pull' ? 'Pulling Image...' : 'Pull Image' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: LIVE CONTAINER LOGS -->
    <div v-if="showLogsModal" class="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-slate-950 text-slate-100 rounded-lg border border-slate-800 shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col">
        <div class="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Terminal class="w-4 h-4 text-emerald-400" />
            <span class="font-bold text-xs">Container Logs: <strong class="text-emerald-400 font-mono">{{ selectedContainer?.Names }}</strong></span>
            <span class="font-mono text-[10px] text-slate-400">({{ (selectedContainer?.ID || '').slice(0, 12) }})</span>
          </div>

          <div class="flex items-center gap-2 text-xs">
            <!-- Line Selector -->
            <select v-model="logTailCount" @change="refreshLogs" class="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:outline-none">
              <option :value="50">50 lines</option>
              <option :value="100">100 lines</option>
              <option :value="250">250 lines</option>
              <option :value="500">500 lines</option>
              <option :value="1000">1000 lines</option>
            </select>

            <button
              @click="toggleLogsAutoRefresh"
              :class="logsAutoRefresh ? 'bg-emerald-600/30 text-emerald-300 border-emerald-500' : 'bg-slate-900 text-slate-400 border-slate-700'"
              class="px-2 py-1 rounded border text-[11px] font-medium flex items-center gap-1"
            >
              <span class="w-1.5 h-1.5 rounded-full" :class="logsAutoRefresh ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'"></span>
              <span>Auto (3s)</span>
            </button>

            <button @click="refreshLogs" :disabled="logsLoading" class="p-1 rounded bg-slate-900 text-slate-300 hover:text-white" title="Refresh Now">
              <RefreshCw :class="{ 'animate-spin': logsLoading }" class="w-3.5 h-3.5" />
            </button>

            <button @click="copyText(activeLogsContent)" class="p-1 rounded bg-slate-900 text-slate-300 hover:text-white" title="Copy to Clipboard">
              <Copy class="w-3.5 h-3.5" />
            </button>

            <button @click="showLogsModal = false" class="text-slate-400 hover:text-white ml-2"><X class="w-4 h-4" /></button>
          </div>
        </div>

        <!-- Logs output area -->
        <div class="p-4 flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed whitespace-pre-wrap select-text bg-slate-950 text-slate-200">
          <div v-if="activeLogsContent">{{ activeLogsContent }}</div>
          <div v-else-if="logsLoading" class="text-slate-500 italic">Streaming logs from Docker daemon...</div>
          <div v-else class="text-slate-500 italic">No log entries found for this container.</div>
        </div>
      </div>
    </div>

    <!-- MODAL: EXEC COMMAND IN CONTAINER -->
    <div v-if="showExecModal" class="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-slate-950 text-slate-100 rounded-lg border border-slate-800 shadow-2xl w-full max-w-2xl flex flex-col">
        <div class="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Cpu class="w-4 h-4 text-purple-400" />
            <span class="font-bold text-xs">Execute inside: <strong class="text-purple-400 font-mono">{{ selectedContainer?.Names }}</strong></span>
          </div>
          <button @click="showExecModal = false" class="text-slate-400 hover:text-white"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-4 space-y-3">
          <div class="flex gap-2">
            <input
              v-model="execCommand"
              @keydown.enter="runExec"
              type="text"
              placeholder="e.g. uptime, ls -la /app, env, df -h"
              class="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-1.5 font-mono text-xs text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
            />
            <button @click="runExec" :disabled="execLoading || !execCommand" class="px-3 py-1.5 rounded bg-purple-600 hover:bg-purple-700 text-white font-medium text-xs">
              {{ execLoading ? 'Running...' : 'Execute' }}
            </button>
          </div>

          <div class="flex flex-wrap gap-1">
            <button
              v-for="cmd in ['uptime', 'uname -a', 'env', 'df -h', 'ps aux', 'cat /etc/os-release']"
              :key="cmd"
              @click="execCommand = cmd; runExec()"
              class="px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 font-mono text-[10px] border border-slate-800"
            >
              {{ cmd }}
            </button>
          </div>

          <div class="p-3 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] min-h-[160px] max-h-72 overflow-y-auto whitespace-pre-wrap text-emerald-400">
            <div v-if="execOutput">{{ execOutput }}</div>
            <div v-else-if="execLoading" class="text-slate-500 italic">Executing command inside container...</div>
            <div v-else class="text-slate-600 italic">Enter a command above and click Execute.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- MODAL: INSPECT CONTAINER -->
    <div v-if="showInspectModal" class="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Eye class="w-4 h-4 text-blue-600" />
            <span>Inspect: <strong class="font-mono text-blue-600">{{ selectedContainer?.Names }}</strong></span>
          </div>
          <div class="flex items-center gap-2">
            <button @click="copyText(JSON.stringify(inspectData, null, 2))" class="np-btn-secondary text-xs py-1">
              <Copy class="w-3 h-3" />
              <span>Copy JSON</span>
            </button>
            <button @click="showInspectModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
          </div>
        </div>

        <div class="p-4 flex-1 overflow-y-auto font-mono text-[10px] bg-slate-950 text-emerald-400 rounded-b">
          <pre>{{ JSON.stringify(inspectData, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- MODAL: 1-CLICK DEPLOY TEMPLATE -->
    <div v-if="showDeployTemplateModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-lg flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Sparkles class="w-4 h-4 text-blue-600" />
            <span>Deploy {{ selectedTemplate?.name }}</span>
          </div>
          <button @click="showDeployTemplateModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3.5 text-xs">
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Container Name</label>
            <input v-model="templateForm.name" type="text" class="np-input w-full font-mono text-xs" />
          </div>

          <div>
            <label class="block font-semibold text-slate-700 mb-1">Port Mapping (Host : Container)</label>
            <input v-model="templateForm.port" type="text" class="np-input w-full font-mono text-xs" />
          </div>

          <!-- Customizable Environment Variables -->
          <div v-if="Object.keys(templateForm.env).length" class="space-y-2">
            <label class="block font-semibold text-slate-700">Environment Configuration</label>
            <div v-for="(val, k) in templateForm.env" :key="k">
              <label class="block text-[10px] font-mono text-slate-500">{{ k }}</label>
              <input v-model="templateForm.env[k]" type="text" class="np-input w-full text-xs" />
            </div>
          </div>

          <div v-if="templateForm.volume">
            <label class="block font-semibold text-slate-700 mb-1">Persistent Storage Volume</label>
            <input v-model="templateForm.volume" type="text" class="np-input w-full font-mono text-xs" />
          </div>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showDeployTemplateModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitDeployTemplate" :disabled="busy === 'deploy_tmpl'" class="np-btn-primary">
            <Sparkles class="w-3.5 h-3.5" />
            <span>Launch Container Stack</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: CREATE VOLUME -->
    <div v-if="showCreateVolumeModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-sm flex flex-col">
        <div class="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <span class="font-bold text-slate-900 text-xs">Create Storage Volume</span>
          <button @click="showCreateVolumeModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>
        <div class="p-4 space-y-3 text-xs">
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Volume Name</label>
            <input v-model="newVolumeName" type="text" placeholder="e.g. my_app_data" class="np-input w-full font-mono" />
          </div>
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Driver</label>
            <input v-model="newVolumeDriver" type="text" placeholder="local" class="np-input w-full font-mono" />
          </div>
        </div>
        <div class="px-4 py-2.5 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showCreateVolumeModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitCreateVolume" :disabled="!newVolumeName || busy === 'vol'" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <!-- MODAL: CREATE NETWORK -->
    <div v-if="showCreateNetworkModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-sm flex flex-col">
        <div class="px-4 py-3 border-b border-slate-200 flex items-center justify-between">
          <span class="font-bold text-slate-900 text-xs">Create Virtual Network</span>
          <button @click="showCreateNetworkModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>
        <div class="p-4 space-y-3 text-xs">
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Network Name</label>
            <input v-model="newNetworkName" type="text" placeholder="e.g. backend-network" class="np-input w-full font-mono" />
          </div>
          <div>
            <label class="block font-semibold text-slate-700 mb-1">Driver</label>
            <select v-model="newNetworkDriver" class="np-input w-full">
              <option value="bridge">bridge (Default)</option>
              <option value="host">host</option>
              <option value="overlay">overlay</option>
            </select>
          </div>
        </div>
        <div class="px-4 py-2.5 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showCreateNetworkModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitCreateNetwork" :disabled="!newNetworkName || busy === 'net'" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Box,
  Boxes,
  CheckCircle2,
  Copy,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileCode,
  HardDrive,
  Layers,
  Network,
  Play,
  Power,
  RefreshCw,
  RotateCw,
  Search,
  Sparkles,
  Square,
  Terminal,
  Trash2,
  X,
} from 'lucide-vue-next'

type Section = 'containers' | 'images' | 'volumes' | 'networks' | 'templates' | 'compose' | 'prune'

const { apiFetch } = useApi()

const activeSection = ref<Section>('containers')
const loading = ref(false)
const busy = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

// State variables
const dockerStatus = ref<any>({ installed: false, active: false, version: {}, info: {}, disk_usage: {} })
const containers = ref<any[]>([])
const images = ref<any[]>([])
const volumes = ref<any[]>([])
const networks = ref<any[]>([])
const templates = ref<any[]>([])

// Container filter & search
const containerFilter = ref('all')
const containerSearch = ref('')

// Image search
const imageSearch = ref('')

// Navigation config
const navSections = [
  { key: 'containers', label: 'Containers', icon: Box },
  { key: 'images', label: 'Images', icon: Layers },
  { key: 'volumes', label: 'Volumes', icon: HardDrive },
  { key: 'networks', label: 'Networks', icon: Network },
  { key: 'templates', label: '1-Click Stacks', icon: Sparkles },
  { key: 'compose', label: 'Compose Stack', icon: FileCode },
  { key: 'prune', label: 'System Cleanup', icon: Trash2 },
]

// Popular image pull chips
const popularPullChips = [
  'redis:7-alpine',
  'nginx:alpine',
  'postgres:16-alpine',
  'mariadb:10.11',
  'node:20-alpine',
  'portainer/portainer-ce:latest',
  'python:3.11-slim',
  'louislam/uptime-kuma:1',
]

// Modal visibility
const showDeployModal = ref(false)
const showPullModal = ref(false)
const showLogsModal = ref(false)
const showExecModal = ref(false)
const showInspectModal = ref(false)
const showDeployTemplateModal = ref(false)
const showCreateVolumeModal = ref(false)
const showCreateNetworkModal = ref(false)

// Logs state
const selectedContainer = ref<any>(null)
const activeLogsContent = ref('')
const logTailCount = ref(100)
const logsLoading = ref(false)
const logsAutoRefresh = ref(false)
let logsInterval: any = null

// Exec state
const execCommand = ref('')
const execOutput = ref('')
const execLoading = ref(false)

// Inspect state
const inspectData = ref<any>(null)

// Pull state
const pullImageRef = ref('')

// Volume / Network forms
const newVolumeName = ref('')
const newVolumeDriver = ref('local')
const newNetworkName = ref('')
const newNetworkDriver = ref('bridge')

// Prune options
const pruneAllImages = ref(false)
const pruneVolumes = ref(false)
const pruneOutput = ref('')

// Compose state
const composeProject = ref('')
const composeYaml = ref('')
const composeRemoveVolumes = ref(false)
const composeOutput = ref('')

// Deploy Form
const deployForm = ref({
  name: '',
  image: '',
  ports: [{ host: '', container: '' }],
  envs: [{ key: '', value: '' }],
  volumes: [{ host: '', container: '' }],
  restart_policy: 'unless-stopped',
  memory_limit: '',
  network: '',
  command: '',
})

// Template Deploy Form
const selectedTemplate = ref<any>(null)
const templateCategory = ref('All')
const templateForm = ref<any>({
  name: '',
  port: '',
  env: {},
  volume: '',
})

// Computed properties
const sectionTitle = computed(() => {
  switch (activeSection.value) {
    case 'containers': return 'Docker Container Management'
    case 'images': return 'Local Image Registry'
    case 'volumes': return 'Persistent Storage Volumes'
    case 'networks': return 'Virtual Networks'
    case 'templates': return '1-Click App Stacks'
    case 'compose': return 'Docker Compose Stacks'
    case 'prune': return 'System Prune & Cleanup'
    default: return 'Docker Manager'
  }
})

const sectionSubtitle = computed(() => {
  switch (activeSection.value) {
    case 'containers': return 'Monitor container lifecycle, ports, live CPU/Memory utilization, and inspect logs.'
    case 'images': return 'Pull container images from registries, inspect disk footprint, and launch containers.'
    case 'volumes': return 'Persistent block storage and data volumes attached to containers.'
    case 'networks': return 'Manage isolated container bridge and overlay network interfaces.'
    case 'templates': return 'Deploy production-ready databases, caches, web servers, and developer runtimes with 1-click.'
    case 'compose': return 'Define and deploy multi-container application stacks via docker-compose.yml.'
    case 'prune': return 'Reclaim host disk storage by purging stopped containers, unreferenced images, and cache.'
    default: return ''
  }
})

const runningCount = computed(() => {
  return containers.value.filter(c => c.State === 'running').length
})

const containerFilters = computed(() => [
  { key: 'all', label: 'All', count: containers.value.length },
  { key: 'running', label: 'Running', count: runningCount.value },
  { key: 'stopped', label: 'Stopped', count: containers.value.length - runningCount.value },
])

const filteredContainers = computed(() => {
  let list = containers.value
  if (containerFilter.value === 'running') {
    list = list.filter(c => c.State === 'running')
  } else if (containerFilter.value === 'stopped') {
    list = list.filter(c => c.State !== 'running')
  }
  if (containerSearch.value.trim()) {
    const q = containerSearch.value.toLowerCase().trim()
    list = list.filter(c =>
      (c.Names || '').toLowerCase().includes(q) ||
      (c.Image || '').toLowerCase().includes(q) ||
      (c.ID || '').toLowerCase().includes(q)
    )
  }
  return list
})

const filteredImages = computed(() => {
  if (!imageSearch.value.trim()) return images.value
  const q = imageSearch.value.toLowerCase().trim()
  return images.value.filter(i =>
    (i.Repository || '').toLowerCase().includes(q) ||
    (i.Tag || '').toLowerCase().includes(q) ||
    (i.ID || '').toLowerCase().includes(q)
  )
})

const serverVersion = computed(() => {
  const v = dockerStatus.value.version
  return v?.Server?.Version || v?.Client?.Version || ''
})

const totalImageSizeFormatted = computed(() => {
  if (!images.value.length) return '0 MB'
  return `${images.value.length} images`
})

const hostInfoText = computed(() => {
  const inf = dockerStatus.value.info
  if (!inf) return 'Local Docker'
  const cpus = inf.NCPU ? `${inf.NCPU} CPUs` : ''
  const mem = inf.MemTotal ? `${(inf.MemTotal / (1024 * 1024 * 1024)).toFixed(1)} GB RAM` : ''
  return [cpus, mem].filter(Boolean).join(' · ') || 'Docker Engine'
})

const hostIp = computed(() => {
  if (typeof window !== 'undefined') {
    return window.location.hostname
  }
  return '129.121.128.122'
})

const templateCategories = computed(() => {
  const cats = new Set(templates.value.map(t => t.category))
  return ['All', ...Array.from(cats)]
})

const filteredTemplates = computed(() => {
  if (templateCategory.value === 'All') return templates.value
  return templates.value.filter(t => t.category === templateCategory.value)
})

// Helper methods
function formatContainerName(name: string): string {
  if (!name) return 'unnamed'
  return name.startsWith('/') ? name.slice(1) : name
}

function formatShortId(id: string): string {
  if (!id) return ''
  const clean = id.startsWith('sha256:') ? id.replace('sha256:', '') : id
  return clean.slice(0, 12)
}

function isWebPort(portStr: string): boolean {
  const p = parseInt(portStr, 10)
  return [80, 443, 8080, 8081, 8085, 8088, 3000, 3001, 8000, 9000, 9443, 5000].includes(p)
}

function getTemplateIcon(icon: string) {
  switch (icon) {
    case 'database': return Database
    case 'globe': return Box
    case 'chart': return Activity
    case 'shield': return Sparkles
    default: return Box
  }
}

async function copyText(text: string) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    noticeMessage.value = 'Copied to clipboard.'
    setTimeout(() => { noticeMessage.value = '' }, 2500)
  } catch (err) {
    console.error(err)
  }
}

// Data loaders
async function loadStatus() {
  try {
    const res = await apiFetch<any>('/docker/status')
    dockerStatus.value = res
  } catch (err: any) {
    console.error(err)
  }
}

async function loadContainers() {
  try {
    const res = await apiFetch<any>('/docker/containers')
    containers.value = res.containers || []
  } catch (err: any) {
    console.error(err)
  }
}

async function loadImages() {
  try {
    const res = await apiFetch<any>('/docker/images')
    images.value = res.images || []
  } catch (err: any) {
    console.error(err)
  }
}

async function loadVolumes() {
  try {
    const res = await apiFetch<any>('/docker/volumes')
    volumes.value = res.volumes || []
  } catch (err: any) {
    console.error(err)
  }
}

async function loadNetworks() {
  try {
    const res = await apiFetch<any>('/docker/networks')
    networks.value = res.networks || []
  } catch (err: any) {
    console.error(err)
  }
}

async function loadTemplates() {
  try {
    const res = await apiFetch<any>('/docker/templates')
    templates.value = res || []
  } catch (err: any) {
    console.error(err)
  }
}

async function refreshAll() {
  loading.value = true
  errorMessage.value = ''
  try {
    await Promise.all([
      loadStatus(),
      loadContainers(),
      loadImages(),
      loadVolumes(),
      loadNetworks(),
      loadTemplates(),
    ])
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to refresh Docker data.'
  } finally {
    loading.value = false
  }
}

// Service Actions
async function installDocker() {
  busy.value = 'install_docker'
  errorMessage.value = ''
  noticeMessage.value = 'Installing Docker Engine & Docker Compose via package manager. This may take 1-2 minutes...'
  try {
    const res = await apiFetch<any>('/docker/install', { method: 'POST' })
    if (res.ok) {
      noticeMessage.value = res.message || 'Docker installed successfully!'
      await refreshAll()
    } else {
      errorMessage.value = res.stderr || 'Docker install encountered issues.'
    }
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to install Docker.'
  } finally {
    busy.value = ''
  }
}

async function controlService(action: string) {
  busy.value = 'service'
  errorMessage.value = ''
  try {
    const res = await apiFetch<any>(`/docker/service/${action}`, { method: 'POST' })
    noticeMessage.value = `Docker service ${action} completed (Status: ${res.status}).`
    await refreshAll()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || `Failed to ${action} Docker service.`
  } finally {
    busy.value = ''
  }
}

// Container Actions
async function controlContainer(id: string, action: string) {
  busy.value = id
  errorMessage.value = ''
  try {
    await apiFetch(`/docker/containers/${id}/${action}`, { method: 'POST' })
    noticeMessage.value = `Container ${action} succeeded.`
    await loadContainers()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || `Failed to ${action} container.`
  } finally {
    busy.value = ''
  }
}

async function confirmRemoveContainer(c: any) {
  const name = formatContainerName(c.Names)
  if (!confirm(`Are you sure you want to permanently delete container "${name}" (${c.ID.slice(0, 12)})?`)) {
    return
  }
  busy.value = c.ID
  try {
    await apiFetch(`/docker/containers/${c.ID}/rm?force=true`, { method: 'POST' })
    noticeMessage.value = `Container "${name}" deleted.`
    await loadContainers()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to delete container.'
  } finally {
    busy.value = ''
  }
}

// Deploy Container
function addPortMapping() {
  deployForm.value.ports.push({ host: '', container: '' })
}

function addEnvVar() {
  deployForm.value.envs.push({ key: '', value: '' })
}

function addVolumeMount() {
  deployForm.value.volumes.push({ host: '', container: '' })
}

function runFromImage(img: any) {
  const refStr = img.Tag ? `${img.Repository}:${img.Tag}` : img.Repository
  deployForm.value.image = refStr
  deployForm.value.name = (img.Repository || '').replace(/[^a-zA-Z0-9_-]/g, '-') + '-app'
  showDeployModal.value = true
}

async function submitDeployContainer() {
  busy.value = 'deploy'
  errorMessage.value = ''
  try {
    const ports = deployForm.value.ports
      .filter(p => p.host && p.container)
      .map(p => `${p.host}:${p.container}`)

    const envMap: Record<string, string> = {}
    for (const e of deployForm.value.envs) {
      if (e.key.trim()) {
        envMap[e.key.trim()] = e.value
      }
    }

    const vols = deployForm.value.volumes
      .filter(v => v.host && v.container)
      .map(v => `${v.host}:${v.container}`)

    const body = {
      image: deployForm.value.image.trim(),
      name: deployForm.value.name.trim() || undefined,
      ports,
      env: envMap,
      volumes: vols,
      restart_policy: deployForm.value.restart_policy,
      memory_limit: deployForm.value.memory_limit.trim() || undefined,
      command: deployForm.value.command.trim() || undefined,
    }

    await apiFetch('/docker/containers/run', { method: 'POST', body })
    noticeMessage.value = `Container deployed successfully!`
    showDeployModal.value = false
    await loadContainers()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to deploy container.'
  } finally {
    busy.value = ''
  }
}

// Logs Modal
async function openLogs(c: any) {
  selectedContainer.value = c
  showLogsModal.value = true
  activeLogsContent.value = ''
  await refreshLogs()
}

async function refreshLogs() {
  if (!selectedContainer.value) return
  logsLoading.value = true
  try {
    const res = await apiFetch<any>(`/docker/containers/${selectedContainer.value.ID}/logs?tail=${logTailCount.value}`)
    activeLogsContent.value = res.logs || 'No logs available.'
  } catch (err: any) {
    activeLogsContent.value = 'Failed to load logs: ' + (err?.data?.detail || err?.message)
  } finally {
    logsLoading.value = false
  }
}

function toggleLogsAutoRefresh() {
  logsAutoRefresh.value = !logsAutoRefresh.value
  if (logsAutoRefresh.value) {
    logsInterval = setInterval(refreshLogs, 3000)
  } else if (logsInterval) {
    clearInterval(logsInterval)
    logsInterval = null
  }
}

// Exec Modal
function openExec(c: any) {
  selectedContainer.value = c
  execCommand.value = 'uptime'
  execOutput.value = ''
  showExecModal.value = true
}

async function runExec() {
  if (!selectedContainer.value || !execCommand.value.trim()) return
  execLoading.value = true
  execOutput.value = ''
  try {
    const res = await apiFetch<any>(`/docker/containers/${selectedContainer.value.ID}/exec`, {
      method: 'POST',
      body: { command: execCommand.value.trim() },
    })
    execOutput.value = res.stdout + (res.stderr ? '\n' + res.stderr : '')
  } catch (err: any) {
    execOutput.value = 'Error: ' + (err?.data?.detail || err?.message)
  } finally {
    execLoading.value = false
  }
}

// Inspect Modal
async function openInspect(c: any) {
  selectedContainer.value = c
  showInspectModal.value = true
  inspectData.value = { loading: true }
  try {
    const res = await apiFetch<any>(`/docker/containers/${c.ID}/inspect`)
    inspectData.value = res
  } catch (err: any) {
    inspectData.value = { error: err?.data?.detail || err?.message }
  }
}

// Images Actions
async function quickPull(imgRef: string) {
  pullImageRef.value = imgRef
  await submitPullImage()
}

async function submitPullImage() {
  if (!pullImageRef.value.trim()) return
  busy.value = 'pull'
  errorMessage.value = ''
  noticeMessage.value = `Pulling ${pullImageRef.value}...`
  try {
    await apiFetch('/docker/images/pull', { method: 'POST', body: { image: pullImageRef.value.trim() } })
    noticeMessage.value = `Image ${pullImageRef.value} pulled successfully!`
    showPullModal.value = false
    pullImageRef.value = ''
    await loadImages()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to pull image.'
  } finally {
    busy.value = ''
  }
}

async function deleteImage(img: any) {
  const ref = img.Tag && img.Tag !== '<none>' ? `${img.Repository}:${img.Tag}` : img.ID
  if (!confirm(`Delete image ${ref}?`)) return
  busy.value = img.ID
  try {
    await apiFetch(`/docker/images/${encodeURIComponent(ref)}?force=true`, { method: 'DELETE' })
    noticeMessage.value = `Image ${ref} deleted.`
    await loadImages()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to delete image.'
  } finally {
    busy.value = ''
  }
}

// Volumes Actions
async function submitCreateVolume() {
  if (!newVolumeName.value.trim()) return
  busy.value = 'vol'
  try {
    await apiFetch('/docker/volumes', {
      method: 'POST',
      body: { name: newVolumeName.value.trim(), driver: newVolumeDriver.value },
    })
    noticeMessage.value = `Volume "${newVolumeName.value}" created.`
    showCreateVolumeModal.value = false
    newVolumeName.value = ''
    await loadVolumes()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to create volume.'
  } finally {
    busy.value = ''
  }
}

async function deleteVolume(name: string) {
  if (!confirm(`Delete persistent volume "${name}"? Data stored inside will be removed.`)) return
  busy.value = name
  try {
    await apiFetch(`/docker/volumes/${encodeURIComponent(name)}`, { method: 'DELETE' })
    noticeMessage.value = `Volume "${name}" removed.`
    await loadVolumes()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to remove volume.'
  } finally {
    busy.value = ''
  }
}

// Networks Actions
async function submitCreateNetwork() {
  if (!newNetworkName.value.trim()) return
  busy.value = 'net'
  try {
    await apiFetch('/docker/networks', {
      method: 'POST',
      body: { name: newNetworkName.value.trim(), driver: newNetworkDriver.value },
    })
    noticeMessage.value = `Network "${newNetworkName.value}" created.`
    showCreateNetworkModal.value = false
    newNetworkName.value = ''
    await loadNetworks()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to create network.'
  } finally {
    busy.value = ''
  }
}

async function deleteNetwork(name: string) {
  if (!confirm(`Delete network "${name}"?`)) return
  busy.value = name
  try {
    await apiFetch(`/docker/networks/${encodeURIComponent(name)}`, { method: 'DELETE' })
    noticeMessage.value = `Network "${name}" removed.`
    await loadNetworks()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to remove network.'
  } finally {
    busy.value = ''
  }
}

// 1-Click Templates
function openDeployTemplate(tmpl: any) {
  selectedTemplate.value = tmpl
  templateForm.value = {
    name: tmpl.default_name || tmpl.id,
    port: tmpl.default_ports?.[0] || '',
    env: { ...(tmpl.default_env || {}) },
    volume: tmpl.default_volumes?.[0] || '',
  }
  showDeployTemplateModal.value = true
}

async function submitDeployTemplate() {
  if (!selectedTemplate.value) return
  busy.value = 'deploy_tmpl'
  errorMessage.value = ''
  try {
    const ports = templateForm.value.port ? [templateForm.value.port] : []
    const volumes = templateForm.value.volume ? [templateForm.value.volume] : []

    await apiFetch('/docker/templates/deploy', {
      method: 'POST',
      body: {
        template_id: selectedTemplate.value.id,
        name: templateForm.value.name,
        ports,
        env: templateForm.value.env,
        volumes,
      },
    })
    noticeMessage.value = `Deployed "${selectedTemplate.value.name}" successfully!`
    showDeployTemplateModal.value = false
    activeSection.value = 'containers'
    await loadContainers()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to deploy template.'
  } finally {
    busy.value = ''
  }
}

// Compose Stacks
function loadComposeSample(type: string) {
  if (type === 'nginx_redis') {
    composeProject.value = 'web-cache-stack'
    composeYaml.value = `version: '3.8'

services:
  web:
    image: nginx:alpine
    ports:
      - "8080:80"
    restart: unless-stopped

  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    volumes:
      - redis_data:/data

volumes:
  redis_data:
`
  } else if (type === 'wordpress') {
    composeProject.value = 'wp-stack'
    composeYaml.value = `version: '3.8'

services:
  db:
    image: mariadb:10.11
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: SecureWpRootPassword123!
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wp_user
      MYSQL_PASSWORD: SecureWpUserPassword123!
    volumes:
      - db_data:/var/lib/mysql

  wordpress:
    depends_on:
      - db
    image: wordpress:latest
    restart: unless-stopped
    ports:
      - "8090:80"
    environment:
      WORDPRESS_DB_HOST: db:3306
      WORDPRESS_DB_USER: wp_user
      WORDPRESS_DB_PASSWORD: SecureWpUserPassword123!
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - wp_data:/var/www/html

volumes:
  db_data:
  wp_data:
`
  }
}

async function deployCompose() {
  if (!composeProject.value || !composeYaml.value) return
  busy.value = 'compose_deploy'
  errorMessage.value = ''
  composeOutput.value = 'Deploying stack...'
  try {
    const res = await apiFetch<any>('/docker/compose/deploy', {
      method: 'POST',
      body: { project_name: composeProject.value.trim(), compose_yaml: composeYaml.value },
    })
    composeOutput.value = res.output || 'Stack deployed successfully!'
    noticeMessage.value = `Compose stack "${composeProject.value}" deployed!`
    await loadContainers()
  } catch (err: any) {
    composeOutput.value = 'Error: ' + (err?.data?.detail || err?.message)
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to deploy compose stack.'
  } finally {
    busy.value = ''
  }
}

async function teardownCompose() {
  if (!composeProject.value) return
  if (!confirm(`Are you sure you want to stop and tear down stack "${composeProject.value}"?`)) return
  busy.value = 'compose_down'
  composeOutput.value = 'Stopping stack...'
  try {
    const res = await apiFetch<any>(`/docker/compose/down?remove_volumes=${composeRemoveVolumes.value}`, {
      method: 'POST',
      body: { project_name: composeProject.value.trim(), compose_yaml: '' },
    })
    composeOutput.value = res.output || 'Stack torn down successfully.'
    noticeMessage.value = `Compose stack "${composeProject.value}" stopped.`
    await loadContainers()
  } catch (err: any) {
    composeOutput.value = 'Error: ' + (err?.data?.detail || err?.message)
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to teardown compose stack.'
  } finally {
    busy.value = ''
  }
}

// Prune System
async function runSystemPrune() {
  if (!confirm('Run Docker System Prune? Unused resources will be permanently deleted.')) return
  busy.value = 'prune'
  pruneOutput.value = 'Pruning system...'
  try {
    const res = await apiFetch<any>('/docker/prune', {
      method: 'POST',
      body: { all: pruneAllImages.value, volumes: pruneVolumes.value },
    })
    pruneOutput.value = res.output || 'System pruned successfully.'
    noticeMessage.value = 'Docker system prune completed.'
    await refreshAll()
  } catch (err: any) {
    pruneOutput.value = 'Error: ' + (err?.data?.detail || err?.message)
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to prune system.'
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  refreshAll()
})

onUnmounted(() => {
  if (logsInterval) {
    clearInterval(logsInterval)
  }
})
</script>