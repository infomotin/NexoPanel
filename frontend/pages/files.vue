<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col min-h-[calc(100vh-7.5rem)] text-xs overflow-hidden">
    <!-- Top Folder Tabs Bar -->
    <div class="flex items-center gap-1 px-3 pt-2 bg-slate-100/80 border-b border-slate-200 overflow-x-auto">
      <div
        v-for="(tab, idx) in tabs"
        :key="tab.id"
        @click="switchTab(idx)"
        :class="activeTabIndex === idx ? 'bg-white text-emerald-700 font-semibold border-t border-l border-r border-slate-200 -mb-px' : 'bg-slate-200/60 text-slate-600 hover:bg-slate-200'"
        class="flex items-center gap-2 px-3 py-1.5 rounded-t cursor-pointer select-none shrink-0"
      >
        <Folder class="w-3.5 h-3.5 text-amber-500" />
        <span class="max-w-[140px] truncate">{{ tab.label }}</span>
        <button
          v-if="tabs.length > 1"
          @click.stop="closeTab(idx)"
          class="text-slate-400 hover:text-rose-600 ml-1"
          title="Close Tab"
        >
          ×
        </button>
      </div>
      <button
        @click="addTab"
        class="px-2 py-1 text-slate-600 hover:text-emerald-600 hover:bg-white rounded font-bold text-sm ml-1"
        title="New Directory Tab"
      >
        +
      </button>
    </div>

    <!-- Breadcrumb Path & Search Row -->
    <div class="px-3 py-2.5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 bg-white">
      <div class="flex items-center gap-1.5 flex-1 min-w-[260px]">
        <button
          @click="goUp"
          class="p-1.5 border border-slate-300 rounded bg-white hover:bg-slate-50 text-slate-600"
          title="Parent Directory"
        >
          <ArrowLeft class="w-3.5 h-3.5" />
        </button>

        <!-- Breadcrumb / Editable Path Box -->
        <div
          v-if="!editingPathBar"
          @click="startEditPath"
          class="flex-1 flex items-center gap-1 border border-slate-300 rounded px-2.5 py-1 bg-white cursor-text overflow-x-auto"
        >
          <button
            @click.stop="loadDir(rootDir)"
            class="text-slate-600 hover:text-emerald-600 font-medium whitespace-nowrap"
          >
            Root dir
          </button>
          <template v-for="(seg, i) in pathSegments" :key="i">
            <span class="text-slate-400">&gt;</span>
            <button
              @click.stop="loadDir(seg.fullPath)"
              class="text-slate-700 hover:text-emerald-600 whitespace-nowrap"
            >
              {{ seg.name }}
            </button>
          </template>
        </div>
        <input
          v-else
          ref="pathInputRef"
          v-model="pathDraft"
          @keyup.enter="commitPathEdit"
          @blur="editingPathBar = false"
          class="flex-1 np-input font-mono"
        />

        <button
          @click="loadDir(currentPath)"
          class="p-1.5 border border-slate-300 rounded bg-white hover:bg-slate-50 text-slate-600"
          title="Refresh"
        >
          <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
        </button>
      </div>

      <!-- Search Files Box -->
      <div class="flex items-center gap-2">
        <div class="flex items-center border border-slate-300 rounded overflow-hidden bg-white">
          <input
            v-model="fileSearch"
            @keyup.enter="runFileSearch"
            placeholder="Search Files"
            class="px-2.5 py-1 text-xs focus:outline-none w-44"
          />
          <label class="flex items-center gap-1 px-2 text-[11px] text-slate-500 border-l border-slate-200 cursor-pointer select-none">
            <input type="checkbox" v-model="includeSubdir" />
            <span>Include subdir</span>
          </label>
          <button
            @click="runFileSearch"
            class="px-2.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
            title="Search"
          >
            <Search class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Action Toolbar Row -->
    <div class="px-3 py-2 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 bg-slate-50/40">
      <div class="flex flex-wrap items-center gap-1.5">
        <input type="file" ref="fileInput" multiple @change="uploadFiles" class="hidden" />
        <button @click="($refs.fileInput as HTMLInputElement).click()" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
          <Upload class="w-3.5 h-3.5 text-slate-500" />
          <span>Upload</span>
        </button>

        <button @click="showRemoteModal = true" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
          <Download class="w-3.5 h-3.5 text-slate-500" />
          <span>Remote Download</span>
        </button>

        <!-- New Dropdown -->
        <div class="relative">
          <button @click="showNewMenu = !showNewMenu" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
            <FolderPlus class="w-3.5 h-3.5 text-amber-500" />
            <span>New</span>
            <span class="text-[10px] text-slate-400">▾</span>
          </button>
          <div v-if="showNewMenu" @mouseleave="showNewMenu = false" class="absolute left-0 mt-1 w-36 bg-white border border-slate-200 rounded shadow-lg z-30 py-1">
            <button @click="showNewMenu = false; openNewModal('file')" class="w-full text-left px-3 py-1.5 hover:bg-slate-50">New Blank File</button>
            <button @click="showNewMenu = false; openNewModal('dir')" class="w-full text-left px-3 py-1.5 hover:bg-slate-50">New Directory</button>
          </div>
        </div>

        <button @click="openContentSearch" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
          <FileSearch class="w-3.5 h-3.5 text-slate-500" />
          <span>Search File Content</span>
        </button>

        <!-- Favorite Dropdown -->
        <div class="relative">
          <button @click="showFavMenu = !showFavMenu" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
            <Star class="w-3.5 h-3.5 text-amber-500" />
            <span>Favorite</span>
            <span class="text-[10px] text-slate-400">▾</span>
          </button>
          <div v-if="showFavMenu" @mouseleave="showFavMenu = false" class="absolute left-0 mt-1 w-56 bg-white border border-slate-200 rounded shadow-lg z-30 py-1">
            <button @click="toggleFavoriteCurrent(); showFavMenu = false" class="w-full text-left px-3 py-1.5 hover:bg-emerald-50 text-emerald-700 font-medium border-b border-slate-100">
              {{ favorites.includes(currentPath) ? '★ Remove Current from Favorites' : '☆ Add Current to Favorites' }}
            </button>
            <button
              v-for="fav in favorites"
              :key="fav"
              @click="loadDir(fav); showFavMenu = false"
              class="w-full text-left px-3 py-1.5 hover:bg-slate-50 font-mono text-[11px] truncate"
            >
              📁 {{ fav }}
            </button>
            <div v-if="favorites.length === 0" class="px-3 py-2 text-slate-400 text-[11px]">No favorites saved</div>
          </div>
        </div>

        <NuxtLink to="/terminal" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
          <Terminal class="w-3.5 h-3.5 text-slate-500" />
          <span>Terminal</span>
        </NuxtLink>

        <button @click="loadDir(rootDir)" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
          Root dir
        </button>

        <button @click="openOperationLogs" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium">
          Operation Logs
        </button>

        <!-- Batch Operations when rows selected -->
        <div v-if="selectedPaths.length > 0" class="flex items-center gap-1 ml-2 pl-2 border-l border-slate-300">
          <button @click="compressSelected" class="px-2 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 font-medium">
            Compress ({{ selectedPaths.length }})
          </button>
          <button @click="batchTrash" class="px-2 py-1 rounded bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 font-medium">
            Delete ({{ selectedPaths.length }})
          </button>
        </div>
      </div>

      <!-- Right Controls: Recycle Bin + View Toggle -->
      <div class="flex items-center gap-1.5">
        <button @click="openRecycleBin" class="px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium flex items-center gap-1">
          <Trash2 class="w-3.5 h-3.5 text-slate-500" />
          <span>Recycle Bin</span>
        </button>
        <div class="flex border border-slate-300 rounded overflow-hidden">
          <button
            @click="viewMode = 'grid'"
            :class="viewMode === 'grid' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'"
            class="p-1.5"
            title="Grid View"
          >
            <LayoutGrid class="w-3.5 h-3.5" />
          </button>
          <button
            @click="viewMode = 'list'"
            :class="viewMode === 'list' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'"
            class="p-1.5 border-l border-slate-300"
            title="List View"
          >
            <List class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>

    <!-- Subdir Search Banner if active -->
    <div v-if="searchResults !== null" class="px-3 py-1.5 bg-emerald-50 border-b border-emerald-200 flex items-center justify-between text-[11px] text-emerald-800">
      <span>Showing recursive search results for "<strong>{{ fileSearch }}</strong>" ({{ searchResults.length }} matches)</span>
      <button @click="searchResults = null; fileSearch = ''" class="underline font-semibold">Clear Search</button>
    </div>

    <!-- Main Files Table (List View) -->
    <div v-if="viewMode === 'list'" class="flex-1 overflow-x-auto">
      <table class="np-table">
        <thead>
          <tr class="bg-slate-50">
            <th class="w-8"><input type="checkbox" @change="toggleAll($event)" /></th>
            <th>File Name</th>
            <th class="w-28">Protected</th>
            <th class="w-32">PMSN/Owner</th>
            <th class="w-28">Size</th>
            <th class="w-40">Modified Time</th>
            <th class="w-24">Ps</th>
            <th class="text-right">Operation</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in paginatedEntries" :key="entry.path" class="hover:bg-slate-50/80">
            <td><input type="checkbox" :value="entry.path" v-model="selectedPaths" /></td>
            <td>
              <button
                v-if="entry.is_dir"
                @click="loadDir(entry.path)"
                class="flex items-center gap-2 font-medium text-slate-800 hover:text-emerald-600 text-left"
              >
                <Folder class="w-4 h-4 text-amber-400 fill-amber-400 shrink-0" />
                <span>{{ entry.name }}</span>
              </button>
              <button
                v-else
                @click="editFile(entry.path)"
                class="flex items-center gap-2 font-mono text-slate-700 hover:text-emerald-600 text-left"
              >
                <FileText class="w-4 h-4 text-slate-400 shrink-0" />
                <span>{{ entry.name }}</span>
              </button>
            </td>
            <td class="text-slate-500 text-[11px]">Unprotected 🔓</td>
            <td>
              <button
                @click="openChmodModal(entry)"
                class="font-mono text-[11px] text-slate-700 hover:text-emerald-600 hover:underline"
              >
                {{ entry.mode_short || entry.mode }} / {{ entry.owner || 'root' }}
              </button>
            </td>
            <td>
              <template v-if="entry.is_dir">
                <span v-if="dirSizes[entry.path] !== undefined" class="font-mono text-[11px] text-slate-700">
                  {{ formatBytes(dirSizes[entry.path]) }}
                </span>
                <button v-else @click="calculateDirSize(entry.path)" class="text-emerald-600 hover:underline font-medium">
                  Calculate
                </button>
              </template>
              <span v-else class="font-mono text-[11px] text-slate-700">{{ formatBytes(entry.size) }}</span>
            </td>
            <td class="font-mono text-[11px] text-slate-500">{{ formatTimestamp(entry.modified_at) }}</td>
            <td class="text-[11px] text-slate-400">{{ entry.is_dir ? 'Directory' : getFileExt(entry.name) }}</td>
            <td class="text-right space-x-2 whitespace-nowrap">
              <button v-if="!entry.is_dir" @click="editFile(entry.path)" class="text-emerald-600 hover:underline font-medium">Edit</button>
              <button v-if="!entry.is_dir" @click="downloadFile(entry.path)" class="text-emerald-600 hover:underline">Download</button>
              <button v-if="!entry.is_dir && isArchive(entry.name)" @click="extractArchive(entry.path)" class="text-blue-600 hover:underline">Extract</button>
              <button @click="openRenameModal(entry)" class="text-slate-600 hover:underline">Rename</button>
              <button @click="openChmodModal(entry)" class="text-slate-600 hover:underline">PMSN</button>
              <button @click="trashEntry(entry.path)" class="text-rose-600 hover:underline">Delete</button>
            </td>
          </tr>
          <tr v-if="displayedEntries.length === 0">
            <td colspan="8" class="p-10 text-center text-slate-400">
              Directory is empty or no files match your search.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Grid View -->
    <div v-else class="flex-1 p-4 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3 content-start">
      <div
        v-for="entry in paginatedEntries"
        :key="entry.path"
        @dblclick="entry.is_dir ? loadDir(entry.path) : editFile(entry.path)"
        class="p-3 rounded border border-slate-200 hover:border-emerald-400 hover:bg-emerald-50/30 flex flex-col items-center text-center gap-1.5 cursor-pointer select-none"
      >
        <Folder v-if="entry.is_dir" class="w-10 h-10 text-amber-400 fill-amber-400" />
        <FileText v-else class="w-10 h-10 text-slate-400" />
        <span class="text-[11px] font-medium text-slate-800 break-all line-clamp-2">{{ entry.name }}</span>
        <span class="text-[10px] text-slate-400 font-mono">{{ entry.is_dir ? 'Folder' : formatBytes(entry.size) }}</span>
      </div>
    </div>

    <!-- Footer Bar -->
    <div class="px-3 py-2 border-t border-slate-200 bg-slate-50/70 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600">
      <div>
        Total {{ dirCount }} directories, {{ fileCount }} files, File size:
        <span v-if="totalFolderSize !== null" class="font-mono font-semibold text-slate-800 ml-1">{{ formatBytes(totalFolderSize) }}</span>
        <button v-else @click="calculateTotalSize" class="text-emerald-600 hover:underline font-medium ml-1">Calculate</button>
      </div>

      <div class="flex items-center gap-2">
        <button @click="page = Math.max(1, page - 1)" :disabled="page === 1" class="px-2 py-0.5 border border-slate-300 rounded bg-white disabled:opacity-40">&lt;</button>
        <span class="px-2 py-0.5 border border-emerald-600 text-emerald-600 font-semibold rounded bg-emerald-50">{{ page }}</span>
        <button @click="page = Math.min(totalPages, page + 1)" :disabled="page >= totalPages" class="px-2 py-0.5 border border-slate-300 rounded bg-white disabled:opacity-40">&gt;</button>
        <select v-model.number="pageSize" class="border border-slate-300 rounded px-1.5 py-0.5 bg-white">
          <option :value="50">50 / page</option>
          <option :value="100">100 / page</option>
          <option :value="200">200 / page</option>
        </select>
        <span>Total {{ displayedEntries.length }}</span>
      </div>
    </div>

    <!-- Modal: Inline Code/Text Editor -->
    <div v-if="editingPath" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-2xl w-full max-w-4xl h-[82vh] flex flex-col overflow-hidden">
        <div class="px-4 py-2.5 bg-slate-900 text-slate-100 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold font-mono text-emerald-400">{{ editingPath }}</span>
            <span class="text-[10px] text-slate-400">({{ editingContent.split('\n').length }} lines)</span>
          </div>
          <button @click="editingPath = ''" class="px-2 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 rounded">Close</button>
        </div>
        <textarea
          v-model="editingContent"
          spellcheck="false"
          class="flex-1 p-4 font-mono text-xs bg-slate-950 text-slate-200 focus:outline-none resize-none leading-relaxed"
        ></textarea>
        <div class="px-4 py-2.5 bg-slate-100 border-t border-slate-200 flex justify-end gap-2">
          <button @click="editingPath = ''" class="np-btn-secondary">Cancel</button>
          <button @click="saveFile" class="np-btn-primary">Save Changes</button>
        </div>
      </div>
    </div>

    <!-- Modal: Chmod Permissions -->
    <div v-if="chmodTarget" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-4">
        <h3 class="text-sm font-bold text-slate-900">Permissions — {{ chmodTarget.name }}</h3>
        <div class="grid grid-cols-3 gap-3 text-xs border border-slate-200 rounded p-3 bg-slate-50">
          <div v-for="(label, role) in { owner: 'Owner', group: 'Group', pub: 'Public' }" :key="role" class="space-y-1.5">
            <p class="font-bold text-slate-700 border-b border-slate-200 pb-1">{{ label }}</p>
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" v-model="permBits[role].r" @change="syncOctalFromBits" /> Read (4)
            </label>
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" v-model="permBits[role].w" @change="syncOctalFromBits" /> Write (2)
            </label>
            <label class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" v-model="permBits[role].x" @change="syncOctalFromBits" /> Execute (1)
            </label>
          </div>
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Octal Permission</label>
          <input v-model="chmodOctal" @input="syncBitsFromOctal" maxlength="4" class="np-input font-mono w-32" />
        </div>
        <div class="flex justify-end gap-2">
          <button @click="chmodTarget = null" class="np-btn-secondary">Cancel</button>
          <button @click="applyChmod" class="np-btn-primary">Apply</button>
        </div>
      </div>
    </div>

    <!-- Modal: New File / Directory -->
    <div v-if="newModalType" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-sm space-y-3">
        <h3 class="text-sm font-bold">{{ newModalType === 'dir' ? 'Create New Directory' : 'Create Blank File' }}</h3>
        <input v-model="newItemName" @keyup.enter="createNewItem" :placeholder="newModalType === 'dir' ? 'folder_name' : 'index.php'" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="newModalType = null" class="np-btn-secondary">Cancel</button>
          <button @click="createNewItem" class="np-btn-primary">Create</button>
        </div>
      </div>
    </div>

    <!-- Modal: Rename -->
    <div v-if="renameTarget" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-sm space-y-3">
        <h3 class="text-sm font-bold">Rename — {{ renameTarget.name }}</h3>
        <input v-model="renameNewName" @keyup.enter="applyRename" class="np-input" />
        <div class="flex justify-end gap-2">
          <button @click="renameTarget = null" class="np-btn-secondary">Cancel</button>
          <button @click="applyRename" class="np-btn-primary">Rename</button>
        </div>
      </div>
    </div>

    <!-- Modal: Remote Download -->
    <div v-if="showRemoteModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-md space-y-3">
        <h3 class="text-sm font-bold">Remote Download (Fetch URL)</h3>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Download URL</label>
          <input v-model="remoteForm.url" placeholder="https://wordpress.org/latest.zip" class="np-input" />
        </div>
        <div>
          <label class="block text-[11px] font-medium text-slate-600 mb-1">Save As Filename (optional)</label>
          <input v-model="remoteForm.filename" placeholder="latest.zip" class="np-input" />
        </div>
        <div class="flex justify-end gap-2">
          <button @click="showRemoteModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="runRemoteDownload" :disabled="remoteDownloading" class="np-btn-primary">
            {{ remoteDownloading ? 'Downloading...' : 'Download to Current Dir' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Modal: Search File Content -->
    <div v-if="showContentSearchModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-2xl h-[65vh] flex flex-col space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-bold">Search File Content in {{ currentPath }}</h3>
          <button @click="showContentSearchModal = false" class="np-btn-secondary">Close</button>
        </div>
        <div class="flex gap-2">
          <input v-model="contentQuery" @keyup.enter="runContentSearch" placeholder="Enter text or symbol to search inside files..." class="np-input flex-1" />
          <button @click="runContentSearch" class="np-btn-primary">Search</button>
        </div>
        <div class="flex-1 overflow-y-auto border border-slate-200 rounded">
          <table class="np-table">
            <thead><tr class="bg-slate-50"><th>File</th><th>Line</th><th>Matched Snippet</th></tr></thead>
            <tbody>
              <tr v-for="(m, i) in contentMatches" :key="i" @click="showContentSearchModal = false; editFile(m.path)" class="hover:bg-emerald-50 cursor-pointer">
                <td class="font-mono text-[11px] text-emerald-700 font-medium">{{ m.name }}</td>
                <td class="font-mono text-[11px]">{{ m.line }}</td>
                <td class="font-mono text-[11px] text-slate-600 truncate max-w-xs">{{ m.snippet }}</td>
              </tr>
              <tr v-if="contentMatches.length === 0">
                <td colspan="3" class="p-6 text-center text-slate-400">No matches found.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal: Operation Logs -->
    <div v-if="showLogsModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-2xl h-[65vh] flex flex-col">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2.5 mb-3">
          <h3 class="text-sm font-bold">File Operation Logs</h3>
          <button @click="showLogsModal = false" class="np-btn-secondary">Close</button>
        </div>
        <div class="flex-1 overflow-y-auto border border-slate-200 rounded">
          <table class="np-table">
            <thead><tr class="bg-slate-50"><th>Time</th><th>User</th><th>Action</th><th>Target</th></tr></thead>
            <tbody>
              <tr v-for="l in fileLogs" :key="l.id">
                <td class="text-[11px] text-slate-500">{{ l.created_at.replace('T', ' ').slice(0, 19) }}</td>
                <td class="font-medium">{{ l.actor }}</td>
                <td class="font-mono text-[11px]">{{ l.action }}</td>
                <td class="font-mono text-[11px] truncate max-w-xs">{{ l.target }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal: Recycle Bin -->
    <div v-if="showTrashModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div class="bg-white rounded-lg shadow-xl p-5 w-full max-w-2xl h-[65vh] flex flex-col">
        <div class="flex items-center justify-between border-b border-slate-200 pb-2.5 mb-3">
          <h3 class="text-sm font-bold">Recycle Bin</h3>
          <div class="flex gap-2">
            <button @click="emptyTrashBin" class="px-2.5 py-1 rounded bg-rose-600 text-white text-xs hover:bg-rose-700">Empty Recycle Bin</button>
            <button @click="showTrashModal = false" class="np-btn-secondary">Close</button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto border border-slate-200 rounded">
          <table class="np-table">
            <thead><tr class="bg-slate-50"><th>Original Path</th><th>Size</th><th>Deleted At</th><th class="text-right">Operate</th></tr></thead>
            <tbody>
              <tr v-for="t in trashItems" :key="t.id">
                <td class="font-mono text-[11px]">{{ t.original_path }}</td>
                <td class="font-mono text-[11px]">{{ t.is_dir ? 'Directory' : formatBytes(t.size_bytes) }}</td>
                <td class="text-[11px] text-slate-500">{{ t.deleted_at.replace('T', ' ').slice(0, 19) }}</td>
                <td class="text-right space-x-2">
                  <button @click="restoreTrash(t.id)" class="text-emerald-600 hover:underline font-medium">Restore</button>
                  <button @click="deleteTrashPermanent(t.id)" class="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
              <tr v-if="trashItems.length === 0">
                <td colspan="4" class="p-8 text-center text-slate-400">Recycle Bin is empty.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeft,
  Download,
  FileSearch,
  FileText,
  Folder,
  FolderPlus,
  LayoutGrid,
  List,
  RefreshCw,
  Search,
  Star,
  Terminal,
  Trash2,
  Upload,
} from 'lucide-vue-next'
import { useAuthStore } from '~/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const { apiFetch, apiBase } = useApi()

const rootDir = ref('/var/www')
const tabs = ref([{ id: 1, label: 'www', path: '/var/www' }])
const activeTabIndex = ref(0)

const currentPath = ref('/var/www')
const entries = ref<any[]>([])
const searchResults = ref<any[] | null>(null)
const dirSizes = ref<Record<string, number>>({})
const totalFolderSize = ref<number | null>(null)
const loading = ref(false)

const editingPathBar = ref(false)
const pathDraft = ref('')
const pathInputRef = ref<HTMLInputElement | null>(null)

const fileSearch = ref('')
const includeSubdir = ref(false)
const selectedPaths = ref<string[]>([])
const viewMode = ref<'list' | 'grid'>('list')
const page = ref(1)
const pageSize = ref(100)

const showNewMenu = ref(false)
const showFavMenu = ref(false)
const favorites = ref<string[]>([])

const editingPath = ref('')
const editingContent = ref('')

const chmodTarget = ref<any>(null)
const chmodOctal = ref('755')
const permBits = reactive<Record<string, { r: boolean; w: boolean; x: boolean }>>({
  owner: { r: true, w: true, x: true },
  group: { r: true, w: false, x: true },
  pub: { r: true, w: false, x: true },
})

const newModalType = ref<'file' | 'dir' | null>(null)
const newItemName = ref('')

const renameTarget = ref<any>(null)
const renameNewName = ref('')

const showRemoteModal = ref(false)
const remoteDownloading = ref(false)
const remoteForm = reactive({ url: '', filename: '' })

const showContentSearchModal = ref(false)
const contentQuery = ref('')
const contentMatches = ref<any[]>([])

const showLogsModal = ref(false)
const fileLogs = ref<any[]>([])

const showTrashModal = ref(false)
const trashItems = ref<any[]>([])

const pathSegments = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  return parts.map((name, idx) => ({
    name,
    fullPath: '/' + parts.slice(0, idx + 1).join('/'),
  }))
})

const displayedEntries = computed(() => {
  if (searchResults.value !== null) {
    return searchResults.value.map((m) => ({
      name: m.name,
      path: m.path,
      is_dir: m.is_dir,
      size: 0,
      mode_short: '---',
      owner: '-',
      modified_at: 0,
    }))
  }
  const q = fileSearch.value.trim().toLowerCase()
  if (!q) return entries.value
  return entries.value.filter((e) => e.name.toLowerCase().includes(q))
})

const totalPages = computed(() => Math.max(1, Math.ceil(displayedEntries.value.length / pageSize.value)))
const paginatedEntries = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return displayedEntries.value.slice(start, start + pageSize.value)
})

const dirCount = computed(() => displayedEntries.value.filter((e) => e.is_dir).length)
const fileCount = computed(() => displayedEntries.value.filter((e) => !e.is_dir).length)

function formatBytes(bytes: number) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const idx = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`
}

function formatTimestamp(ts: number) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return d.toISOString().replace('T', ' ').slice(0, 19)
}

function getFileExt(name: string) {
  const idx = name.lastIndexOf('.')
  return idx > 0 ? name.slice(idx + 1).toUpperCase() : 'File'
}

function isArchive(name: string) {
  return /\.(zip|tar\.gz|tgz|tar)$/i.test(name)
}

async function loadDir(path: string) {
  loading.value = true
  searchResults.value = null
  totalFolderSize.value = null
  selectedPaths.value = []
  page.value = 1
  try {
    const res = await apiFetch<any>(`/files/list?path=${encodeURIComponent(path)}`)
    currentPath.value = res.path
    entries.value = res.entries || []
    const tab = tabs.value[activeTabIndex.value]
    if (tab) {
      tab.path = res.path
      tab.label = res.path.split('/').filter(Boolean).pop() || 'Root'
    }
  } finally {
    loading.value = false
  }
}

function switchTab(idx: number) {
  activeTabIndex.value = idx
  loadDir(tabs.value[idx].path)
}

function addTab() {
  const id = Date.now()
  tabs.value.push({ id, label: 'www', path: rootDir.value })
  activeTabIndex.value = tabs.value.length - 1
  loadDir(rootDir.value)
}

function closeTab(idx: number) {
  tabs.value.splice(idx, 1)
  if (activeTabIndex.value >= tabs.value.length) {
    activeTabIndex.value = tabs.value.length - 1
  }
  loadDir(tabs.value[activeTabIndex.value].path)
}

function goUp() {
  const parts = currentPath.value.split('/').filter(Boolean)
  if (parts.length <= 1) return
  const parent = '/' + parts.slice(0, -1).join('/')
  loadDir(parent)
}

function startEditPath() {
  pathDraft.value = currentPath.value
  editingPathBar.value = true
  nextTick(() => pathInputRef.value?.focus())
}

function commitPathEdit() {
  editingPathBar.value = false
  if (pathDraft.value.trim()) loadDir(pathDraft.value.trim())
}

async function runFileSearch() {
  if (!fileSearch.value.trim()) {
    searchResults.value = null
    return
  }
  if (includeSubdir.value) {
    const res = await apiFetch<any>(`/files/search?path=${encodeURIComponent(currentPath.value)}&query=${encodeURIComponent(fileSearch.value.trim())}`)
    searchResults.value = res.matches || []
  } else {
    searchResults.value = null
  }
}

function toggleAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedPaths.value = checked ? paginatedEntries.value.map((en) => en.path) : []
}

async function calculateDirSize(path: string) {
  const res = await apiFetch<any>(`/files/size?path=${encodeURIComponent(path)}`)
  dirSizes.value[path] = res.size
}

async function calculateTotalSize() {
  const res = await apiFetch<any>(`/files/size?path=${encodeURIComponent(currentPath.value)}`)
  totalFolderSize.value = res.size
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

function downloadFile(path: string) {
  const url = `${apiBase}/files/download?path=${encodeURIComponent(path)}`
  fetch(url, { headers: { Authorization: `Bearer ${auth.token}` } })
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = path.split('/').pop() || 'file'
      a.click()
    })
}

async function uploadFiles(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  for (const file of Array.from(input.files)) {
    const fd = new FormData()
    fd.append('path', currentPath.value)
    fd.append('file', file)
    await apiFetch('/files/upload', { method: 'POST', body: fd })
  }
  input.value = ''
  await loadDir(currentPath.value)
}

function openNewModal(type: 'file' | 'dir') {
  newModalType.value = type
  newItemName.value = ''
}

async function createNewItem() {
  const name = newItemName.value.trim()
  if (!name) return
  const target = `${currentPath.value.replace(/\/$/, '')}/${name}`
  if (newModalType.value === 'dir') {
    await apiFetch('/files/mkdir', { method: 'POST', body: { source: target } })
  } else {
    await apiFetch('/files/write', { method: 'POST', body: { path: target, content: '' } })
  }
  newModalType.value = null
  await loadDir(currentPath.value)
}

function openRenameModal(entry: any) {
  renameTarget.value = entry
  renameNewName.value = entry.name
}

async function applyRename() {
  if (!renameTarget.value || !renameNewName.value.trim()) return
  const parent = renameTarget.value.path.split('/').slice(0, -1).join('/') || '/'
  const dst = `${parent}/${renameNewName.value.trim()}`
  await apiFetch('/files/rename', { method: 'POST', body: { source: renameTarget.value.path, destination: dst } })
  renameTarget.value = null
  await loadDir(currentPath.value)
}

function openChmodModal(entry: any) {
  chmodTarget.value = entry
  chmodOctal.value = (entry.mode_short || '755').slice(-3)
  syncBitsFromOctal()
}

function syncBitsFromOctal() {
  const oct = chmodOctal.value.padStart(3, '0').slice(-3)
  const roles = ['owner', 'group', 'pub']
  roles.forEach((role, i) => {
    const d = parseInt(oct[i] || '0', 10) || 0
    permBits[role].r = Boolean(d & 4)
    permBits[role].w = Boolean(d & 2)
    permBits[role].x = Boolean(d & 1)
  })
}

function syncOctalFromBits() {
  const roles = ['owner', 'group', 'pub']
  chmodOctal.value = roles
    .map((r) => (permBits[r].r ? 4 : 0) + (permBits[r].w ? 2 : 0) + (permBits[r].x ? 1 : 0))
    .join('')
}

async function applyChmod() {
  if (!chmodTarget.value) return
  await apiFetch('/files/chmod', { method: 'POST', body: { path: chmodTarget.value.path, mode: chmodOctal.value } })
  chmodTarget.value = null
  await loadDir(currentPath.value)
}

async function extractArchive(path: string) {
  await apiFetch('/files/extract', { method: 'POST', body: { archive_path: path, destination_dir: currentPath.value } })
  await loadDir(currentPath.value)
}

async function compressSelected() {
  const name = prompt('Archive filename:', `archive_${Date.now()}.zip`)
  if (!name) return
  const out = `${currentPath.value.replace(/\/$/, '')}/${name}`
  await apiFetch('/files/archive', {
    method: 'POST',
    body: { paths: selectedPaths.value, output_path: out, format: name.endsWith('.zip') ? 'zip' : 'tar.gz' },
  })
  selectedPaths.value = []
  await loadDir(currentPath.value)
}

async function trashEntry(path: string) {
  if (!confirm(`Move ${path.split('/').pop()} to Recycle Bin?`)) return
  await apiFetch(`/files/trash/move?path=${encodeURIComponent(path)}`, { method: 'POST' })
  await loadDir(currentPath.value)
}

async function batchTrash() {
  if (!confirm(`Move ${selectedPaths.value.length} selected items to Recycle Bin?`)) return
  for (const p of selectedPaths.value) {
    await apiFetch(`/files/trash/move?path=${encodeURIComponent(p)}`, { method: 'POST' })
  }
  selectedPaths.value = []
  await loadDir(currentPath.value)
}

async function runRemoteDownload() {
  if (!remoteForm.url.trim()) return
  remoteDownloading.value = true
  try {
    await apiFetch('/files/fetch-url', {
      method: 'POST',
      body: {
        url: remoteForm.url.trim(),
        destination_dir: currentPath.value,
        filename: remoteForm.filename.trim() || null,
      },
    })
    showRemoteModal.value = false
    remoteForm.url = ''
    remoteForm.filename = ''
    await loadDir(currentPath.value)
  } finally {
    remoteDownloading.value = false
  }
}

function openContentSearch() {
  contentQuery.value = ''
  contentMatches.value = []
  showContentSearchModal.value = true
}

async function runContentSearch() {
  if (!contentQuery.value.trim()) return
  const res = await apiFetch<any>(`/files/search-content?path=${encodeURIComponent(currentPath.value)}&query=${encodeURIComponent(contentQuery.value.trim())}`)
  contentMatches.value = res.matches || []
}

async function openOperationLogs() {
  fileLogs.value = await apiFetch<any[]>('/files/logs')
  showLogsModal.value = true
}

async function openRecycleBin() {
  trashItems.value = await apiFetch<any[]>('/files/trash')
  showTrashModal.value = true
}

async function restoreTrash(id: number) {
  await apiFetch(`/files/trash/${id}/restore`, { method: 'POST' })
  trashItems.value = await apiFetch<any[]>('/files/trash')
  await loadDir(currentPath.value)
}

async function deleteTrashPermanent(id: number) {
  await apiFetch(`/files/trash/${id}`, { method: 'DELETE' })
  trashItems.value = await apiFetch<any[]>('/files/trash')
}

async function emptyTrashBin() {
  if (!confirm('Permanently delete all items in Recycle Bin?')) return
  await apiFetch('/files/trash', { method: 'DELETE' })
  trashItems.value = []
}

function toggleFavoriteCurrent() {
  const idx = favorites.value.indexOf(currentPath.value)
  if (idx >= 0) favorites.value.splice(idx, 1)
  else favorites.value.push(currentPath.value)
  localStorage.setItem('np_file_favorites', JSON.stringify(favorites.value))
}

onMounted(async () => {
  try {
    favorites.value = JSON.parse(localStorage.getItem('np_file_favorites') || '[]')
  } catch {
    favorites.value = []
  }
  try {
    const rootsRes = await apiFetch<any>('/files/roots')
    if (rootsRes?.roots?.length) {
      rootDir.value = rootsRes.roots[0]
    }
  } catch {
    // Keep /var/www default
  }
  const initialPath = (route.query.path as string) || rootDir.value
  tabs.value[0].path = initialPath
  await loadDir(initialPath).catch(() => {})
})
</script>
