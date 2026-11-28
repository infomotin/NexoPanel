<template>
  <div class="bg-white rounded-lg border border-slate-200 shadow-sm flex min-h-[calc(100vh-7.5rem)] overflow-hidden text-xs">
    <!-- Left Navigation Sidebar -->
    <aside class="w-52 shrink-0 border-r border-slate-200 bg-slate-50/70 py-3 flex flex-col justify-between">
      <div>
        <div class="px-4 pb-3 mb-2 border-b border-slate-200">
          <div class="flex items-center gap-2 font-bold text-slate-900 text-sm">
            <Settings class="w-4 h-4 text-blue-600" />
            <span>Panel Settings</span>
          </div>
          <p class="text-[10px] text-slate-500 mt-0.5 font-medium">Branding · Security · Port · SMTP · Storage</p>
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
          </button>
        </nav>
      </div>

      <!-- Quick Panel Meta & Actions Widget -->
      <div class="mx-3 mt-4 space-y-2">
        <div class="rounded border border-slate-200 bg-white p-2.5 space-y-1.5 shadow-2xs">
          <div class="flex items-center justify-between">
            <span class="text-[10px] font-medium text-slate-500">Control Plane</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-600">
              <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
              Operational
            </span>
          </div>
          <div class="text-[10px] text-slate-600 flex justify-between">
            <span>Storage:</span>
            <span class="font-mono text-slate-800 font-semibold">SQLite WAL</span>
          </div>
          <div class="text-[10px] text-slate-600 flex justify-between">
            <span>Version:</span>
            <span class="font-mono text-slate-800 font-semibold">v1.0 (online)</span>
          </div>
        </div>

        <button
          @click="saveAllSettings"
          :disabled="saving"
          class="w-full flex items-center justify-center gap-1.5 rounded border border-blue-600 bg-blue-600 hover:bg-blue-700 text-white py-1.5 px-2 text-[11px] font-semibold transition-colors shadow-2xs disabled:opacity-50"
        >
          <RotateCw :class="{ 'animate-spin': saving }" class="w-3.5 h-3.5" />
          <span>{{ saving ? 'Saving Changes...' : 'Save All Changes' }}</span>
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
            <span v-if="hasUnsavedChanges" class="px-2 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px] font-semibold flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span> Unsaved Changes
            </span>
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">{{ sectionSubtitle }}</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button @click="refreshSettings" :disabled="loading" class="np-btn-secondary" title="Reload settings from database">
            <RefreshCw :class="{ 'animate-spin': loading }" class="w-3.5 h-3.5" />
            <span>Reload</span>
          </button>
          <button @click="saveAllSettings" :disabled="saving" class="np-btn-primary">
            <Check class="w-3.5 h-3.5" />
            <span>{{ saving ? 'Saving...' : 'Save Changes' }}</span>
          </button>
        </div>
      </div>

      <!-- Feedback Alerts -->
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

      <!-- SECTION: GENERAL & BRANDING -->
      <div v-if="activeSection === 'general'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="font-bold text-slate-900 text-xs border-b border-slate-200 pb-2 flex items-center gap-1.5">
            <Sliders class="w-4 h-4 text-blue-600" />
            <span>Branding & Identification</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Panel Brand Title</label>
              <input v-model="form.panel_title" type="text" placeholder="e.g. NexoPanel or My Hosting Panel" class="np-input w-full" />
              <p class="text-[10px] text-slate-400 mt-1">Displayed in browser tab titles, navigation headers, and emails.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Panel Base Public URL</label>
              <input v-model="form.panel_url" type="text" placeholder="http://129.121.128.122:8443" class="np-input w-full font-mono" />
              <p class="text-[10px] text-slate-400 mt-1">Used for webhook callbacks, automated links, and email notifications.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Admin Notification Email</label>
              <input v-model="form.admin_email" type="email" placeholder="admin@example.com" class="np-input w-full" />
              <p class="text-[10px] text-slate-400 mt-1">Recipient for critical system alerts, SSL expiration, and backup failures.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Server Timezone</label>
              <select v-model="form.timezone" class="np-input w-full">
                <option value="UTC">UTC (Coordinated Universal Time)</option>
                <option value="America/New_York">America/New_York (EST / EDT)</option>
                <option value="America/Chicago">America/Chicago (CST / CDT)</option>
                <option value="America/Los_Angeles">America/Los_Angeles (PST / PDT)</option>
                <option value="Europe/London">Europe/London (GMT / BST)</option>
                <option value="Europe/Paris">Europe/Paris (CET / CEST)</option>
                <option value="Europe/Berlin">Europe/Berlin (CET / CEST)</option>
                <option value="Asia/Dhaka">Asia/Dhaka (BST)</option>
                <option value="Asia/Dubai">Asia/Dubai (GST)</option>
                <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
                <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
                <option value="Australia/Sydney">Australia/Sydney (AEST)</option>
              </select>
              <p class="text-[10px] text-slate-400 mt-1">Determines timestamp formatting for logs, cron jobs, and backups.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Date & Time Format</label>
              <select v-model="form.date_format" class="np-input w-full font-mono text-[11px]">
                <option value="YYYY-MM-DD HH:mm:ss">2026-11-28 14:30:00 (ISO 8601 24h)</option>
                <option value="MM/DD/YYYY hh:mm A">11/28/2026 02:30 PM (US 12h)</option>
                <option value="DD/MM/YYYY HH:mm">28/11/2026 14:30 (EU 24h)</option>
              </select>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Interface Language</label>
              <select v-model="form.language" class="np-input w-full">
                <option value="en">English (US)</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION: SECURITY & ACCESS -->
      <div v-else-if="activeSection === 'security'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="font-bold text-slate-900 text-xs border-b border-slate-200 pb-2 flex items-center gap-1.5">
            <ShieldCheck class="w-4 h-4 text-emerald-600" />
            <span>Authentication & Session Hardening</span>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Administrative Session Timeout</label>
              <div class="flex items-center gap-2">
                <input v-model="form.session_timeout_minutes" type="number" class="np-input w-36 font-mono text-xs" />
                <span class="text-slate-500 text-xs">minutes ({{ sessionTimeoutText }})</span>
              </div>
              <div class="flex gap-1.5 mt-2">
                <button @click="form.session_timeout_minutes = '60'" class="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px]">1 Hour</button>
                <button @click="form.session_timeout_minutes = '720'" class="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px]">12 Hours</button>
                <button @click="form.session_timeout_minutes = '1440'" class="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px]">24 Hours</button>
                <button @click="form.session_timeout_minutes = '10080'" class="px-2 py-0.5 rounded bg-blue-100 hover:bg-blue-200 text-blue-800 text-[10px] font-semibold">7 Days (Default)</button>
              </div>
            </div>

            <div class="pt-2 border-t border-slate-200">
              <label class="flex items-start gap-2.5 cursor-pointer">
                <input v-model="form.force_https" type="checkbox" true-value="true" false-value="false" class="mt-0.5 rounded border-slate-300 text-blue-600" />
                <div>
                  <span class="font-semibold text-slate-800 block">Enforce HTTPS Redirect for Web UI</span>
                  <span class="text-[10px] text-slate-500">Automatically redirect all unencrypted HTTP traffic to SSL/TLS port 8443.</span>
                </div>
              </label>
            </div>

            <div class="pt-2 border-t border-slate-200">
              <label class="flex items-start gap-2.5 cursor-pointer">
                <input v-model="form.rate_limit_login" type="checkbox" true-value="true" false-value="false" class="mt-0.5 rounded border-slate-300 text-blue-600" />
                <div>
                  <span class="font-semibold text-slate-800 block">Brute-Force Rate Limiting & Fail2Ban Protection</span>
                  <span class="text-[10px] text-slate-500">Temporarily lock out IP addresses exceeding maximum failed authentication attempts.</span>
                </div>
              </label>
            </div>

            <div class="grid grid-cols-2 gap-3 pl-6">
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Max Failed Attempts</label>
                <input v-model="form.max_login_attempts" type="number" class="np-input w-28 font-mono text-xs" />
              </div>
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Lockout Duration (mins)</label>
                <input v-model="form.lockout_duration_minutes" type="number" class="np-input w-28 font-mono text-xs" />
              </div>
            </div>

            <div class="pt-2 border-t border-slate-200">
              <label class="block font-semibold text-slate-700 mb-1">Panel Access IP Allowlist</label>
              <textarea
                v-model="form.ip_allowlist"
                rows="2"
                placeholder="Leave blank to allow access from any IP. Or enter comma-separated IPs: 192.168.1.100, 10.0.0.0/24"
                class="np-input w-full font-mono text-xs"
              ></textarea>
              <p class="text-[10px] text-slate-400 mt-1">When configured, logins from unlisted IP addresses will be blocked at the HTTP layer.</p>
            </div>

            <div class="pt-2 border-t border-slate-200">
              <label class="flex items-start gap-2.5 cursor-pointer">
                <input v-model="form.security_headers" type="checkbox" true-value="true" false-value="false" class="mt-0.5 rounded border-slate-300 text-blue-600" />
                <div>
                  <span class="font-semibold text-slate-800 block">Strict HTTP Security Headers (HSTS, CSP, X-Frame-Options)</span>
                  <span class="text-[10px] text-slate-500">Inject security headers to guard against clickjacking, cross-site framing, and MIME confusion.</span>
                </div>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION: PANEL PORT & SSL -->
      <div v-else-if="activeSection === 'port_ssl'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="font-bold text-slate-900 text-xs border-b border-slate-200 pb-2 flex items-center gap-1.5">
            <Globe class="w-4 h-4 text-blue-600" />
            <span>Panel Listen Port & Domain Binding</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Panel Listen Port</label>
              <input v-model="form.panel_port" type="number" class="np-input w-full font-mono text-xs" placeholder="8443" />
              <p class="text-[10px] text-slate-400 mt-1">Default is 8443. Ensure firewall rules permit traffic on this port.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Panel Domain Name (optional)</label>
              <input v-model="form.panel_domain" type="text" placeholder="panel.yourdomain.com" class="np-input w-full font-mono text-xs" />
              <p class="text-[10px] text-slate-400 mt-1">Point this domain's A DNS record to 129.121.128.122 before enabling SSL.</p>
            </div>
          </div>

          <div class="border-t border-slate-200 pt-3 space-y-2">
            <label class="block font-semibold text-slate-700 mb-1">SSL Certificate Provider</label>
            <div class="space-y-1.5">
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.panel_ssl_type" type="radio" value="self_signed" class="text-blue-600" />
                <span>Self-Signed SSL Certificate (Default fallback)</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.panel_ssl_type" type="radio" value="letsencrypt" class="text-blue-600" />
                <span>Let's Encrypt Automated SSL (Requires domain bound above)</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.panel_ssl_type" type="radio" value="custom" class="text-blue-600" />
                <span>Custom SSL Certificate & Key</span>
              </label>
            </div>
          </div>

          <div v-if="form.panel_ssl_type === 'custom'" class="space-y-3 pt-2">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">SSL Certificate (PEM format)</label>
              <textarea v-model="form.custom_ssl_cert" rows="4" placeholder="-----BEGIN CERTIFICATE-----..." class="np-input w-full font-mono text-[10px]"></textarea>
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">SSL Private Key (PEM format)</label>
              <textarea v-model="form.custom_ssl_key" rows="4" placeholder="-----BEGIN PRIVATE KEY-----..." class="np-input w-full font-mono text-[10px]"></textarea>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION: EMAIL & SMTP NOTIFICATIONS -->
      <div v-else-if="activeSection === 'email'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-200 pb-2">
            <div class="font-bold text-slate-900 text-xs flex items-center gap-1.5">
              <Mail class="w-4 h-4 text-blue-600" />
              <span>Outgoing SMTP Mail Server</span>
            </div>
            <button @click="showTestSmtpModal = true" class="np-btn-secondary text-xs py-1">
              <Send class="w-3.5 h-3.5" />
              <span>Test SMTP Connection</span>
            </button>
          </div>

          <label class="flex items-start gap-2.5 cursor-pointer">
            <input v-model="form.smtp_enabled" type="checkbox" true-value="true" false-value="false" class="mt-0.5 rounded border-slate-300 text-blue-600" />
            <div>
              <span class="font-semibold text-slate-800 block">Enable Outgoing Email Notifications</span>
              <span class="text-[10px] text-slate-500">Send server alerts, backup digests, and administrative notices via SMTP.</span>
            </div>
          </label>

          <!-- Popular Provider Presets -->
          <div>
            <span class="text-[10px] font-semibold text-slate-500 block mb-1">Popular SMTP Presets:</span>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="p in smtpPresets"
                :key="p.name"
                @click="applySmtpPreset(p)"
                class="px-2 py-0.8 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] font-medium border border-slate-200 transition-colors"
              >
                {{ p.name }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div class="md:col-span-2">
              <label class="block font-semibold text-slate-700 mb-1">SMTP Server Host</label>
              <input v-model="form.smtp_host" type="text" placeholder="e.g. smtp.mailgun.org or smtp.gmail.com" class="np-input w-full font-mono text-xs" />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">SMTP Port</label>
              <input v-model="form.smtp_port" type="number" placeholder="587" class="np-input w-full font-mono text-xs" />
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Encryption Protocol</label>
              <select v-model="form.smtp_encryption" class="np-input w-full">
                <option value="tls">STARTTLS (Port 587)</option>
                <option value="ssl">SSL / TLS (Port 465)</option>
                <option value="none">None (Port 25)</option>
              </select>
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">SMTP Username</label>
              <input v-model="form.smtp_user" type="text" placeholder="username or api key" class="np-input w-full" />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">SMTP Password</label>
              <input v-model="form.smtp_password" type="password" placeholder="••••••••" class="np-input w-full" />
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-slate-200 pt-3">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Default From Email</label>
              <input v-model="form.smtp_from_email" type="email" placeholder="noreply@yourdomain.com" class="np-input w-full" />
            </div>
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Default From Name</label>
              <input v-model="form.smtp_from_name" type="text" placeholder="NexoPanel Notifications" class="np-input w-full" />
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION: WEB & RUNTIME DEFAULTS -->
      <div v-else-if="activeSection === 'web_defaults'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="font-bold text-slate-900 text-xs border-b border-slate-200 pb-2 flex items-center gap-1.5">
            <Server class="w-4 h-4 text-purple-600" />
            <span>Web Server & Runtime Provisioning Defaults</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Default PHP Version</label>
              <select v-model="form.default_php_version" class="np-input w-full font-mono text-xs">
                <option value="8.4">PHP 8.4</option>
                <option value="8.3">PHP 8.3 (Recommended)</option>
                <option value="8.2">PHP 8.2</option>
                <option value="8.1">PHP 8.1</option>
                <option value="8.0">PHP 8.0</option>
                <option value="7.4">PHP 7.4 (Legacy)</option>
              </select>
              <p class="text-[10px] text-slate-400 mt-1">Pre-selected runtime version when creating new websites.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Default Web Document Root</label>
              <input v-model="form.default_web_root" type="text" placeholder="/var/www/{domain}/public" class="np-input w-full font-mono text-xs" />
              <p class="text-[10px] text-slate-400 mt-1">Placeholder <code>{domain}</code> will be substituted automatically.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Nginx Max Upload Body Size</label>
              <select v-model="form.nginx_client_max_body_size" class="np-input w-full font-mono text-xs">
                <option value="64M">64 MB</option>
                <option value="128M">128 MB (Default)</option>
                <option value="256M">256 MB</option>
                <option value="512M">512 MB</option>
                <option value="1024M">1 GB</option>
              </select>
              <p class="text-[10px] text-slate-400 mt-1">Configures <code>client_max_body_size</code> for file uploads.</p>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Database Prefix Format</label>
              <input v-model="form.default_database_prefix" type="text" placeholder="db_" class="np-input w-full font-mono text-xs" />
              <p class="text-[10px] text-slate-400 mt-1">Prefix automatically assigned to managed databases.</p>
            </div>
          </div>

          <div class="border-t border-slate-200 pt-3">
            <label class="flex items-start gap-2.5 cursor-pointer">
              <input v-model="form.auto_ssl_enabled" type="checkbox" true-value="true" false-value="false" class="mt-0.5 rounded border-slate-300 text-blue-600" />
              <div>
                <span class="font-semibold text-slate-800 block">Automatic SSL Certificate Issuance</span>
                <span class="text-[10px] text-slate-500">Automatically attempt to issue Let's Encrypt SSL when new domains are added.</span>
              </div>
            </label>
          </div>
        </div>
      </div>

      <!-- SECTION: BACKUPS & CLOUD STORAGE -->
      <div v-else-if="activeSection === 'storage'" class="space-y-4 max-w-3xl">
        <div class="rounded-lg border border-slate-200 p-4 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-200 pb-2">
            <div class="font-bold text-slate-900 text-xs flex items-center gap-1.5">
              <Cloud class="w-4 h-4 text-blue-600" />
              <span>Backup Destinations & Cloud Storage (S3 / R2 / B2)</span>
            </div>
            <button
              v-if="form.backup_storage_provider !== 'local'"
              @click="showTestS3Modal = true"
              class="np-btn-secondary text-xs py-1"
            >
              <Check class="w-3.5 h-3.5" />
              <span>Test S3 Connection</span>
            </button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block font-semibold text-slate-700 mb-1">Default Storage Provider</label>
              <select v-model="form.backup_storage_provider" class="np-input w-full">
                <option value="local">Local Server (/var/backups/nexopanel)</option>
                <option value="s3">Amazon S3 / AWS Compatible</option>
                <option value="r2">Cloudflare R2 Storage</option>
                <option value="b2">Backblaze B2 Storage</option>
                <option value="wasabi">Wasabi Hot Cloud Storage</option>
              </select>
            </div>

            <div>
              <label class="block font-semibold text-slate-700 mb-1">Backup Retention Period</label>
              <select v-model="form.backup_retention_days" class="np-input w-full">
                <option value="7">7 Days</option>
                <option value="14">14 Days (Recommended)</option>
                <option value="30">30 Days</option>
                <option value="60">60 Days</option>
                <option value="90">90 Days</option>
              </select>
            </div>
          </div>

          <div v-if="form.backup_storage_provider !== 'local'" class="space-y-3 border-t border-slate-200 pt-3">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label class="block font-semibold text-slate-700 mb-1">S3 Custom Endpoint URL</label>
                <input v-model="form.s3_endpoint" type="text" placeholder="https://s3.amazonaws.com or R2 URL" class="np-input w-full font-mono text-xs" />
              </div>
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Bucket Name</label>
                <input v-model="form.s3_bucket" type="text" placeholder="my-backups-bucket" class="np-input w-full font-mono text-xs" />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label class="block font-semibold text-slate-700 mb-1">S3 Region</label>
                <input v-model="form.s3_region" type="text" placeholder="us-east-1" class="np-input w-full font-mono text-xs" />
              </div>
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Access Key ID</label>
                <input v-model="form.s3_access_key" type="text" placeholder="AKIA..." class="np-input w-full font-mono text-xs" />
              </div>
              <div>
                <label class="block font-semibold text-slate-700 mb-1">Secret Access Key</label>
                <input v-model="form.s3_secret_key" type="password" placeholder="••••••••" class="np-input w-full font-mono text-xs" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION: MAINTENANCE & DIAGNOSTICS -->
      <div v-else-if="activeSection === 'maintenance'" class="space-y-4 max-w-3xl">
        <!-- Cache & Buffer Cleaner -->
        <div class="rounded-lg border border-slate-200 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-bold text-slate-900 text-xs">System Storage & Cache Cleaner</h3>
              <p class="text-[10px] text-slate-500">Purge temporary files in /run/nexopanel/tmp, clean APT package cache, and flush transient buffers.</p>
            </div>
            <button
              @click="cleanCache"
              :disabled="busy === 'clean_cache'"
              class="np-btn-secondary text-xs"
            >
              <Trash2 class="w-3.5 h-3.5 text-slate-500" />
              <span>{{ busy === 'clean_cache' ? 'Cleaning...' : 'Clean Cache Now' }}</span>
            </button>
          </div>
        </div>

        <!-- Service Restarter -->
        <div class="rounded-lg border border-slate-200 p-4 space-y-3">
          <div>
            <h3 class="font-bold text-slate-900 text-xs">Core Services Management</h3>
            <p class="text-[10px] text-slate-500">Restart or reload core background services if configuration updates require daemon restart.</p>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
            <button
              @click="restartService('nexopanel')"
              :disabled="busy === 'svc_nexopanel'"
              class="p-2.5 rounded border border-slate-200 hover:border-blue-400 bg-white hover:bg-slate-50 text-left transition-colors flex items-center justify-between"
            >
              <div>
                <div class="font-bold text-slate-900 text-[11px]">NexoPanel</div>
                <div class="text-[9px] text-slate-400">Restart Backend</div>
              </div>
              <RotateCw :class="{ 'animate-spin': busy === 'svc_nexopanel' }" class="w-3 h-3 text-slate-400" />
            </button>

            <button
              @click="restartService('nginx', 'reload')"
              :disabled="busy === 'svc_nginx'"
              class="p-2.5 rounded border border-slate-200 hover:border-blue-400 bg-white hover:bg-slate-50 text-left transition-colors flex items-center justify-between"
            >
              <div>
                <div class="font-bold text-slate-900 text-[11px]">Nginx</div>
                <div class="text-[9px] text-slate-400">Reload Config</div>
              </div>
              <RotateCw :class="{ 'animate-spin': busy === 'svc_nginx' }" class="w-3 h-3 text-slate-400" />
            </button>

            <button
              @click="restartService('mariadb')"
              :disabled="busy === 'svc_mariadb'"
              class="p-2.5 rounded border border-slate-200 hover:border-blue-400 bg-white hover:bg-slate-50 text-left transition-colors flex items-center justify-between"
            >
              <div>
                <div class="font-bold text-slate-900 text-[11px]">MariaDB</div>
                <div class="text-[9px] text-slate-400">Restart Database</div>
              </div>
              <RotateCw :class="{ 'animate-spin': busy === 'svc_mariadb' }" class="w-3 h-3 text-slate-400" />
            </button>

            <button
              @click="restartService('redis-server')"
              :disabled="busy === 'svc_redis-server'"
              class="p-2.5 rounded border border-slate-200 hover:border-blue-400 bg-white hover:bg-slate-50 text-left transition-colors flex items-center justify-between"
            >
              <div>
                <div class="font-bold text-slate-900 text-[11px]">Redis</div>
                <div class="text-[9px] text-slate-400">Restart Cache</div>
              </div>
              <RotateCw :class="{ 'animate-spin': busy === 'svc_redis-server' }" class="w-3 h-3 text-slate-400" />
            </button>
          </div>
        </div>

        <!-- Export & Import Settings -->
        <div class="rounded-lg border border-slate-200 p-4 space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="font-bold text-slate-900 text-xs">Configuration Portability (Backup & Restore)</h3>
              <p class="text-[10px] text-slate-500">Download current panel settings as a JSON file or migrate configuration to another host.</p>
            </div>
            <div class="space-x-2">
              <button @click="showImportModal = true" class="np-btn-secondary text-xs">
                <Upload class="w-3.5 h-3.5" />
                <span>Import JSON</span>
              </button>
              <button @click="exportSettings" class="np-btn-secondary text-xs">
                <Download class="w-3.5 h-3.5" />
                <span>Export JSON</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Reset to Factory Defaults -->
        <div class="rounded-lg border border-rose-200 bg-rose-50/50 p-4 flex items-center justify-between">
          <div>
            <h3 class="font-bold text-rose-900 text-xs">Reset to Factory Defaults</h3>
            <p class="text-[10px] text-rose-700">Restore all panel configuration settings to default values. Websites and databases will not be touched.</p>
          </div>
          <button
            @click="resetDefaults"
            :disabled="busy === 'reset'"
            class="np-btn-danger text-xs px-3"
          >
            <RotateCw :class="{ 'animate-spin': busy === 'reset' }" class="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: TEST SMTP -->
    <div v-if="showTestSmtpModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-md flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Send class="w-4 h-4 text-blue-600" />
            <span>Test SMTP Mail Connectivity</span>
          </div>
          <button @click="showTestSmtpModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3 text-xs">
          <p class="text-slate-600 text-[11px]">
            Verify outbound connection and TLS handshake with <strong>{{ form.smtp_host || 'Configured Host' }}</strong> on port <strong>{{ form.smtp_port }}</strong>.
          </p>

          <div>
            <label class="block font-semibold text-slate-700 mb-1">Test Recipient Email (optional)</label>
            <input v-model="testRecipientEmail" type="email" placeholder="e.g. your-email@example.com" class="np-input w-full" />
          </div>

          <div v-if="smtpTestResult" class="p-3 rounded text-[11px]" :class="smtpTestResult.ok ? 'bg-emerald-50 border border-emerald-200 text-emerald-800' : 'bg-rose-50 border border-rose-200 text-rose-800'">
            {{ smtpTestResult.message || smtpTestResult.error }}
          </div>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showTestSmtpModal = false" class="np-btn-secondary">Close</button>
          <button @click="runSmtpTest" :disabled="testingSmtp || !form.smtp_host" class="np-btn-primary">
            <RotateCw :class="{ 'animate-spin': testingSmtp }" class="w-3.5 h-3.5" />
            <span>{{ testingSmtp ? 'Testing Connection...' : 'Run Test' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: TEST S3 -->
    <div v-if="showTestS3Modal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-md flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Check class="w-4 h-4 text-emerald-600" />
            <span>Test S3 Storage Connectivity</span>
          </div>
          <button @click="showTestS3Modal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3 text-xs">
          <p class="text-slate-600 text-[11px]">
            Verify endpoint resolution and bucket access for <strong>{{ form.s3_bucket || 'Configured Bucket' }}</strong> in region <strong>{{ form.s3_region }}</strong>.
          </p>

          <div v-if="s3TestResult" class="p-3 rounded text-[11px]" :class="s3TestResult.ok ? 'bg-emerald-50 border border-emerald-200 text-emerald-800' : 'bg-rose-50 border border-rose-200 text-rose-800'">
            {{ s3TestResult.message || s3TestResult.error }}
          </div>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showTestS3Modal = false" class="np-btn-secondary">Close</button>
          <button @click="runS3Test" :disabled="testingS3 || !form.s3_bucket" class="np-btn-primary">
            <RotateCw :class="{ 'animate-spin': testingS3 }" class="w-3.5 h-3.5" />
            <span>{{ testingS3 ? 'Testing Bucket...' : 'Test Connection' }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- MODAL: IMPORT SETTINGS -->
    <div v-if="showImportModal" class="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div class="bg-white rounded-lg border border-slate-200 shadow-xl w-full max-w-lg flex flex-col">
        <div class="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <div class="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Upload class="w-4 h-4 text-blue-600" />
            <span>Import Settings JSON</span>
          </div>
          <button @click="showImportModal = false" class="text-slate-400 hover:text-slate-600"><X class="w-4 h-4" /></button>
        </div>

        <div class="p-5 space-y-3 text-xs">
          <p class="text-slate-600 text-[11px]">Paste a valid settings JSON payload exported from another NexoPanel installation:</p>
          <textarea
            v-model="importJsonText"
            rows="8"
            placeholder='{"settings": {"panel_title": "NexoPanel", ...}}'
            class="np-input w-full font-mono text-[10px]"
          ></textarea>
        </div>

        <div class="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end gap-2">
          <button @click="showImportModal = false" class="np-btn-secondary">Cancel</button>
          <button @click="submitImportSettings" :disabled="!importJsonText.trim() || busy === 'import'" class="np-btn-primary">
            <Upload class="w-3.5 h-3.5" />
            <span>Apply Settings</span>
          </button>
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
  Check,
  CheckCircle2,
  Cloud,
  Download,
  Globe,
  HardDrive,
  Key,
  Lock,
  Mail,
  Power,
  RefreshCw,
  RotateCw,
  Send,
  Server,
  Settings,
  ShieldCheck,
  Sliders,
  Trash2,
  Upload,
  X,
} from 'lucide-vue-next'

type Section = 'general' | 'security' | 'port_ssl' | 'email' | 'web_defaults' | 'storage' | 'maintenance'

const { apiFetch } = useApi()

const activeSection = ref<Section>('general')
const loading = ref(false)
const saving = ref(false)
const busy = ref('')
const noticeMessage = ref('')
const errorMessage = ref('')
const hasUnsavedChanges = ref(false)

// Modals
const showTestSmtpModal = ref(false)
const showTestS3Modal = ref(false)
const showImportModal = ref(false)

// Test states
const testRecipientEmail = ref('')
const testingSmtp = ref(false)
const smtpTestResult = ref<any>(null)
const testingS3 = ref(false)
const s3TestResult = ref<any>(null)
const importJsonText = ref('')

// Form State with initial defaults
const form = reactive<Record<string, any>>({
  // General
  panel_title: 'NexoPanel',
  panel_url: 'http://129.121.128.122:8443',
  admin_email: 'admin@localhost.localdomain',
  timezone: 'UTC',
  language: 'en',
  date_format: 'YYYY-MM-DD HH:mm:ss',

  // Security
  session_timeout_minutes: '10080',
  force_https: 'false',
  rate_limit_login: 'true',
  max_login_attempts: '5',
  lockout_duration_minutes: '15',
  ip_allowlist: '',
  security_headers: 'true',

  // Port & SSL
  panel_port: '8443',
  panel_domain: '',
  panel_ssl_type: 'self_signed',
  custom_ssl_cert: '',
  custom_ssl_key: '',

  // Email
  smtp_enabled: 'false',
  smtp_host: '',
  smtp_port: '587',
  smtp_encryption: 'tls',
  smtp_user: '',
  smtp_password: '',
  smtp_from_email: 'noreply@localhost',
  smtp_from_name: 'NexoPanel Alerts',

  // Web Defaults
  default_php_version: '8.3',
  default_web_root: '/var/www/{domain}/public',
  auto_ssl_enabled: 'true',
  nginx_client_max_body_size: '128M',
  default_database_prefix: 'db_',

  // Storage
  backup_retention_days: '14',
  backup_storage_provider: 'local',
  s3_endpoint: '',
  s3_bucket: '',
  s3_region: 'us-east-1',
  s3_access_key: '',
  s3_secret_key: '',
})

// Navigation Items
const navSections = [
  { key: 'general', label: 'General & Branding', icon: Sliders },
  { key: 'security', label: 'Security & Access', icon: ShieldCheck },
  { key: 'port_ssl', label: 'Port & SSL Binding', icon: Globe },
  { key: 'email', label: 'Email & SMTP', icon: Mail },
  { key: 'web_defaults', label: 'Web & PHP Defaults', icon: Server },
  { key: 'storage', label: 'Backups & S3 Cloud', icon: Cloud },
  { key: 'maintenance', label: 'Maintenance & Tools', icon: Activity },
]

// SMTP Presets
const smtpPresets = [
  { name: 'Gmail', host: 'smtp.gmail.com', port: '587', encryption: 'tls' },
  { name: 'Mailgun', host: 'smtp.mailgun.org', port: '587', encryption: 'tls' },
  { name: 'SendGrid', host: 'smtp.sendgrid.net', port: '587', encryption: 'tls' },
  { name: 'Amazon SES', host: 'email-smtp.us-east-1.amazonaws.com', port: '587', encryption: 'tls' },
  { name: 'Postmark', host: 'smtp.postmarkapp.com', port: '587', encryption: 'tls' },
  { name: 'Brevo (Sendinblue)', host: 'smtp-relay.brevo.com', port: '587', encryption: 'tls' },
]

// Computed Titles
const sectionTitle = computed(() => {
  switch (activeSection.value) {
    case 'general': return 'General Branding & Localization'
    case 'security': return 'Security, Sessions & Access Restrictions'
    case 'port_ssl': return 'Panel Port & Domain SSL Binding'
    case 'email': return 'Email & Outgoing SMTP Notifications'
    case 'web_defaults': return 'Web Server & Runtime Provisioning Defaults'
    case 'storage': return 'Backup Retention & Cloud Storage (S3 / R2)'
    case 'maintenance': return 'Maintenance, Cache Cleaner & Portability'
    default: return 'Panel Settings'
  }
})

const sectionSubtitle = computed(() => {
  switch (activeSection.value) {
    case 'general': return 'Configure global panel identity, public address, administrator email, and time settings.'
    case 'security': return 'Harden administrative sessions, configure brute force rate limiting, and restrict access.'
    case 'port_ssl': return 'Manage the panel listening port and assign an SSL certificate to your administration interface.'
    case 'email': return 'Configure outgoing mail delivery for server alerts, backup digests, and user notifications.'
    case 'web_defaults': return 'Default configuration applied to newly provisioned websites, PHP engines, and databases.'
    case 'storage': return 'Configure remote S3-compatible cloud storage targets for off-site disaster recovery backups.'
    case 'maintenance': return 'Perform cache purging, service restarts, settings export/import, or factory resets.'
    default: return ''
  }
})

const sessionTimeoutText = computed(() => {
  const m = parseInt(form.session_timeout_minutes, 10) || 60
  if (m >= 1440) return `${(m / 1440).toFixed(1)} days`
  if (m >= 60) return `${(m / 60).toFixed(1)} hours`
  return `${m} minutes`
})

function applySmtpPreset(p: any) {
  form.smtp_host = p.host
  form.smtp_port = p.port
  form.smtp_encryption = p.encryption
  noticeMessage.value = `Applied ${p.name} SMTP settings.`
}

// Data Fetching
async function refreshSettings() {
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await apiFetch<Record<string, string>>('/system/settings/map')
    for (const [k, v] of Object.entries(res)) {
      form[k] = v
    }
    hasUnsavedChanges.value = false
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to load panel settings.'
  } finally {
    loading.value = false
  }
}

async function saveAllSettings() {
  saving.value = true
  errorMessage.value = ''
  try {
    const payload: Record<string, string> = {}
    for (const [k, v] of Object.entries(form)) {
      payload[k] = String(v ?? '')
    }
    await apiFetch('/system/settings/batch', {
      method: 'POST',
      body: { settings: payload },
    })
    noticeMessage.value = 'Panel settings successfully saved.'
    hasUnsavedChanges.value = false
    setTimeout(() => { noticeMessage.value = '' }, 3500)
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to save settings.'
  } finally {
    saving.value = false
  }
}

// Actions
async function runSmtpTest() {
  testingSmtp.value = true
  smtpTestResult.value = null
  try {
    const res = await apiFetch<any>('/system/settings/test-smtp', {
      method: 'POST',
      body: {
        smtp_host: form.smtp_host,
        smtp_port: parseInt(form.smtp_port, 10) || 587,
        smtp_encryption: form.smtp_encryption,
        smtp_user: form.smtp_user,
        smtp_password: form.smtp_password,
        smtp_from_email: form.smtp_from_email,
        test_recipient: testRecipientEmail.value,
      },
    })
    smtpTestResult.value = res
  } catch (err: any) {
    smtpTestResult.value = { ok: false, error: err?.data?.detail || err?.message }
  } finally {
    testingSmtp.value = false
  }
}

async function runS3Test() {
  testingS3.value = true
  s3TestResult.value = null
  try {
    const res = await apiFetch<any>('/system/settings/test-s3', {
      method: 'POST',
      body: {
        s3_endpoint: form.s3_endpoint,
        s3_bucket: form.s3_bucket,
        s3_region: form.s3_region,
        s3_access_key: form.s3_access_key,
        s3_secret_key: form.s3_secret_key,
      },
    })
    s3TestResult.value = res
  } catch (err: any) {
    s3TestResult.value = { ok: false, error: err?.data?.detail || err?.message }
  } finally {
    testingS3.value = false
  }
}

async function cleanCache() {
  busy.value = 'clean_cache'
  try {
    const res = await apiFetch<any>('/system/settings/clean-cache', { method: 'POST' })
    noticeMessage.value = res.message || 'System cache cleaned successfully.'
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to clean system cache.'
  } finally {
    busy.value = ''
  }
}

async function restartService(serviceName: string, action: string = 'restart') {
  busy.value = `svc_${serviceName}`
  try {
    const res = await apiFetch<any>('/system/maintenance/restart-service', {
      method: 'POST',
      body: { service: serviceName, action },
    })
    noticeMessage.value = `Service ${serviceName} ${action} completed successfully.`
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || `Failed to ${action} ${serviceName}.`
  } finally {
    busy.value = ''
  }
}

async function exportSettings() {
  try {
    const data = await apiFetch<any>('/system/settings/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nexopanel-settings-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    noticeMessage.value = 'Settings exported as JSON.'
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to export settings.'
  }
}

async function submitImportSettings() {
  busy.value = 'import'
  errorMessage.value = ''
  try {
    const parsed = JSON.parse(importJsonText.value)
    const res = await apiFetch<any>('/system/settings/import', {
      method: 'POST',
      body: parsed,
    })
    noticeMessage.value = `Imported ${res.imported_count} settings successfully!`
    showImportModal.value = false
    importJsonText.value = ''
    await refreshSettings()
  } catch (err: any) {
    errorMessage.value = 'Invalid JSON: ' + (err?.data?.detail || err?.message)
  } finally {
    busy.value = ''
  }
}

async function resetDefaults() {
  if (!confirm('Are you sure you want to reset all panel settings to factory defaults?')) {
    return
  }
  busy.value = 'reset'
  try {
    await apiFetch('/system/settings/reset-defaults', { method: 'POST' })
    noticeMessage.value = 'All panel settings reset to factory defaults.'
    await refreshSettings()
  } catch (err: any) {
    errorMessage.value = err?.data?.detail || err?.message || 'Failed to reset settings.'
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  refreshSettings()
})
</script>