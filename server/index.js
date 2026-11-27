import express from 'express';
import cors from 'cors';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import multer from 'multer';
import os from 'node:os';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { db, SANDBOX_FILES_ROOT } from './db.js';

const app = express();
const PORT = process.env.PORT || 3001;
const JWT_SECRET = process.env.JWT_SECRET || 'nexopanel-express-dev-secret-key';

app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: '10mb' }));

// --- Auth Middleware ---
function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'Authentication required' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    return next();
  } catch {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

// --- Safe Path Helper ---
function resolveSafeFilePath(relPath = '') {
  const clean = String(relPath).replace(/^\/+/, '');
  const target = path.resolve(SANDBOX_FILES_ROOT, clean);
  if (!target.startsWith(SANDBOX_FILES_ROOT)) {
    throw new Error('Path traversal denied');
  }
  return target;
}

const upload = multer({ dest: path.join(os.tmpdir(), 'nexopanel_uploads') });

// --- 1. Auth Routes ---
app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);
  if (!user || !bcrypt.compareSync(String(password || ''), user.password_hash)) {
    return res.status(401).json({ error: 'Invalid username or password' });
  }
  const token = jwt.sign({ id: user.id, username: user.username, role: user.role }, JWT_SECRET, { expiresIn: '24h' });
  return res.json({ token, user: { id: user.id, username: user.username, role: user.role } });
});

app.get('/api/auth/me', requireAuth, (req, res) => {
  res.json({ user: req.user });
});

// --- 2. Dashboard & Telemetry ---
let netSentBase = 142_500_000;
let netRecvBase = 384_200_000;

app.get('/api/dashboard', requireAuth, (req, res) => {
  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const usedMem = totalMem - freeMem;
  const load = os.loadavg();
  const cpus = os.cpus();
  const cpuPct = Math.min(98, Math.max(4, Math.round((load[0] / Math.max(cpus.length, 1)) * 100) || 18 + Math.floor(Math.random() * 12)));

  netSentBase += Math.floor(Math.random() * 45000);
  netRecvBase += Math.floor(Math.random() * 82000);

  const sitesRunning = db.prepare("SELECT COUNT(*) as c FROM websites WHERE status = 'running'").get().c;
  const sitesStopped = db.prepare("SELECT COUNT(*) as c FROM websites WHERE status = 'stopped'").get().c;
  const ftpCount = db.prepare('SELECT COUNT(*) as c FROM ftp_accounts').get().c;
  const dbCount = db.prepare('SELECT COUNT(*) as c FROM databases').get().c;
  const appsHome = db.prepare('SELECT * FROM software_apps WHERE display_on_home = 1').all();
  const memoRow = db.prepare("SELECT value FROM settings WHERE key = 'memo'").get();

  res.json({
    hostname: os.hostname(),
    os: `${os.type()} ${os.release()}`,
    arch: os.arch(),
    uptimeSeconds: Math.floor(os.uptime()),
    load: { avg1: Number(load[0].toFixed(2)) || 0.21, avg5: Number(load[1].toFixed(2)) || 0.28, avg15: Number(load[2].toFixed(2)) || 0.27, status: 'Normal' },
    cpu: { cores: cpus.length, percent: cpuPct },
    ram: { totalBytes: totalMem, usedBytes: usedMem, percent: Math.round((usedMem / totalMem) * 100) },
    disk: { totalGb: 96.2, usedGb: 35.3, percent: 37, mount: '/' },
    network: {
      upstreamKbps: 120 + Math.floor(Math.random() * 340),
      downstreamKbps: 260 + Math.floor(Math.random() * 680),
      totalSentBytes: netSentBase,
      totalRecvBytes: netRecvBase,
    },
    counts: { sitesRunning, sitesStopped, sitesAll: sitesRunning + sitesStopped, ftpCount, dbCount, securityRisks: 0 },
    softwareHome: appsHome,
    memo: memoRow ? memoRow.value : '',
  });
});

app.put('/api/dashboard/memo', requireAuth, (req, res) => {
  const { memo } = req.body || {};
  db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run('memo', String(memo || ''));
  res.json({ ok: true, memo });
});

// --- 3. Websites ---
app.get('/api/websites', requireAuth, (req, res) => {
  const rows = db.prepare('SELECT * FROM websites ORDER BY id DESC').all();
  res.json(rows);
});

app.post('/api/websites', requireAuth, (req, res) => {
  const { domain, project_type = 'php', php_version = '8.2', remarks = '', ssl_enabled = false } = req.body || {};
  if (!domain) return res.status(400).json({ error: 'Domain is required' });
  const docRoot = `/www/wwwroot/${domain}`;
  const nginxCfg = `server {\n  listen 80;\n  server_name ${domain};\n  root ${docRoot};\n}`;
  try {
    const info = db.prepare(
      'INSERT INTO websites (domain, project_type, php_version, document_root, status, ssl_enabled, remarks, nginx_config) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    ).run(domain.trim(), project_type, php_version, docRoot, 'running', ssl_enabled ? 1 : 0, remarks, nginxCfg);
    fs.mkdirSync(path.join(SANDBOX_FILES_ROOT, domain.trim()), { recursive: true });
    return res.status(201).json(db.prepare('SELECT * FROM websites WHERE id = ?').get(info.lastInsertRowid));
  } catch (err) {
    return res.status(409).json({ error: err.message });
  }
});

app.put('/api/websites/:id', requireAuth, (req, res) => {
  const site = db.prepare('SELECT * FROM websites WHERE id = ?').get(req.params.id);
  if (!site) return res.status(404).json({ error: 'Website not found' });
  const { php_version, ssl_enabled, force_https, status, remarks, nginx_config } = req.body || {};
  db.prepare(
    'UPDATE websites SET php_version = ?, ssl_enabled = ?, force_https = ?, status = ?, remarks = ?, nginx_config = ? WHERE id = ?'
  ).run(
    php_version ?? site.php_version,
    ssl_enabled !== undefined ? (ssl_enabled ? 1 : 0) : site.ssl_enabled,
    force_https !== undefined ? (force_https ? 1 : 0) : site.force_https,
    status ?? site.status,
    remarks ?? site.remarks,
    nginx_config ?? site.nginx_config,
    site.id
  );
  res.json(db.prepare('SELECT * FROM websites WHERE id = ?').get(site.id));
});

app.post('/api/websites/:id/backup', requireAuth, (req, res) => {
  db.prepare('UPDATE websites SET backups_count = backups_count + 1 WHERE id = ?').run(req.params.id);
  res.json(db.prepare('SELECT * FROM websites WHERE id = ?').get(req.params.id));
});

app.delete('/api/websites/:id', requireAuth, (req, res) => {
  db.prepare('DELETE FROM websites WHERE id = ?').run(req.params.id);
  res.json({ deleted: true });
});

// --- 4. FTP Accounts (Full aaPanel Pure-FTPd & Log Analysis Parity) ---
const FTP_USERNAME_RE = /^[a-zA-Z0-9_]{3,32}$/;
const FTP_CRITICAL_DIRS = new Set(['/', '/bin', '/boot', '/dev', '/etc', '/lib', '/lib64', '/proc', '/root', '/run', '/sbin', '/sys', '/usr', '/var/log']);
const WEAK_FTP_PASSWORDS = new Set(['123456', '12345678', '123456789', 'password', 'admin123', 'qwerty', 'aapanel', 'ftp123456', '111111', '000000']);

function getSettingVal(key, fallback = '') {
  const row = db.prepare('SELECT value FROM settings WHERE key = ?').get(key);
  return row ? row.value : fallback;
}

function setSettingVal(key, val) {
  db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)').run(key, String(val));
}

function validateFtpHomePath(docRoot) {
  const cleaned = String(docRoot || '').trim().replace(/\\/g, '/');
  if (!cleaned) throw new Error('Document root is required');
  if (cleaned.includes('..') || cleaned.includes('\0')) throw new Error('Path traversal denied');
  const norm = cleaned.startsWith('/') ? '/' + cleaned.replace(/^\/+|\/+$/g, '') : cleaned;
  if (FTP_CRITICAL_DIRS.has(norm)) throw new Error('System critical directory cannot be used as FTP directory');
  return cleaned;
}

app.get('/api/ftp', requireAuth, (req, res) => {
  const search = String(req.query.search || '').trim().toLowerCase();
  let rows = db.prepare('SELECT * FROM ftp_accounts ORDER BY id DESC').all();
  if (search) {
    rows = rows.filter((r) =>
      r.username.toLowerCase().includes(search) ||
      (r.note || '').toLowerCase().includes(search) ||
      r.document_root.toLowerCase().includes(search)
    );
  }
  res.json(rows);
});

app.get('/api/ftp/overview', requireAuth, (req, res) => {
  const search = String(req.query.search || '').trim().toLowerCase();
  const page = Math.max(1, Number(req.query.page) || 1);
  const limit = Math.min(200, Math.max(1, Number(req.query.limit) || 20));
  let all = db.prepare('SELECT * FROM ftp_accounts ORDER BY id DESC').all();
  if (search) {
    all = all.filter((r) =>
      r.username.toLowerCase().includes(search) ||
      (r.note || '').toLowerCase().includes(search) ||
      r.document_root.toLowerCase().includes(search)
    );
  }
  const start = (page - 1) * limit;
  const items = all.slice(start, start + limit);
  const pureftpd = db.prepare("SELECT status FROM software_apps WHERE slug = 'pureftpd'").get();
  const weakAccounts = all.filter((a) => WEAK_FTP_PASSWORDS.has(a.password) || a.password.length < 7).map((a) => a.username);
  res.json({
    items,
    total: all.length,
    page,
    limit,
    port: Number(getSettingVal('ftp_port', '21')),
    passive_range: '39000-40000',
    service_installed: !pureftpd || pureftpd.status === 'installed',
    service_running: true,
    log_service_status: getSettingVal('ftp_log_service', 'start'),
    security: {
      no_anonymous: getSettingVal('ftp_no_anonymous', 'true') === 'true',
      forbid_root: getSettingVal('ftp_forbid_root', 'true') === 'true',
      weak_password_accounts: weakAccounts,
    },
  });
});

app.post('/api/ftp', requireAuth, (req, res) => {
  const { username, password, document_root = '/www/wwwroot', quota_mb = 0, note = '', expires_at = null } = req.body || {};
  const uname = String(username || '').trim();
  const pass = String(password || '').trim();
  if (!FTP_USERNAME_RE.test(uname)) {
    return res.status(400).json({ error: 'FTP username must be 3-32 chars (letters, numbers, underscores only)' });
  }
  if (pass.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters' });
  }
  let safeHome;
  try {
    safeHome = validateFtpHomePath(document_root);
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }

  try {
    const finalNote = String(note || '').trim() || uname;
    const info = db.prepare(
      'INSERT INTO ftp_accounts (username, password, document_root, quota_mb, note, expires_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(uname, pass, safeHome, Number(quota_mb) || 0, finalNote, expires_at);

    const sandboxSub = safeHome.replace(/^\/www\/wwwroot\/?/, '');
    if (sandboxSub && !sandboxSub.includes('..')) {
      fs.mkdirSync(path.join(SANDBOX_FILES_ROOT, sandboxSub), { recursive: true });
    }
    const nowIso = new Date().toISOString().replace('T', ' ').slice(0, 19);
    db.prepare('INSERT INTO ftp_logs (username, log_kind, action_type, ip, country, status, in_time, out_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?)')
      .run(uname, 'login', 'login_success', '127.0.0.1', 'Local', 'Account Created', nowIso, 'active');

    res.status(201).json(db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(info.lastInsertRowid));
  } catch (err) {
    res.status(409).json({ error: err.message });
  }
});

app.put('/api/ftp/port', requireAuth, (req, res) => {
  const port = Number(req.body?.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return res.status(400).json({ error: 'Port must be an integer between 1 and 65535' });
  }
  setSettingVal('ftp_port', String(port));
  const fw = db.prepare('SELECT id FROM firewall_rules WHERE port = ? AND protocol = ?').get(String(port), 'tcp');
  if (!fw) {
    db.prepare('INSERT INTO firewall_rules (protocol, port, strategy, direction, source_ip, remarks) VALUES (?, ?, ?, ?, ?, ?)')
      .run('tcp', String(port), 'allow', 'inbound', '0.0.0.0/0', 'FTP port');
  }
  res.json({ port, updated: true });
});

app.put('/api/ftp/security', requireAuth, (req, res) => {
  const { no_anonymous, forbid_root } = req.body || {};
  if (no_anonymous !== undefined) setSettingVal('ftp_no_anonymous', no_anonymous ? 'true' : 'false');
  if (forbid_root !== undefined) setSettingVal('ftp_forbid_root', forbid_root ? 'true' : 'false');
  res.json({
    no_anonymous: getSettingVal('ftp_no_anonymous', 'true') === 'true',
    forbid_root: getSettingVal('ftp_forbid_root', 'true') === 'true',
  });
});

app.post('/api/ftp/log-service', requireAuth, (req, res) => {
  const exec_name = String(req.body?.exec_name || 'getlog');
  if (!['getlog', 'start', 'stop'].includes(exec_name)) {
    return res.status(400).json({ error: 'Invalid exec_name' });
  }
  if (exec_name === 'getlog') {
    return res.json({ status: getSettingVal('ftp_log_service', 'start') });
  }
  setSettingVal('ftp_log_service', exec_name);
  res.json({ status: exec_name });
});

app.get('/api/ftp/log-analysis/config', requireAuth, (req, res) => {
  const raw = getSettingVal('ftp_scan_config', '');
  try {
    return res.json(JSON.parse(raw));
  } catch {
    return res.json({ login_error: 5, area: { country: ['Local', 'US'] }, time: { start_time: 6, end_time: 23 }, upload_shell: ['.php', '.sh', '.py'], auto_scan: false });
  }
});

app.put('/api/ftp/log-analysis/config', requireAuth, (req, res) => {
  const { login_error = 5, countries = [], start_time = 0, end_time = 23, upload_shell = ['.php', '.sh', '.py'], auto_scan } = req.body || {};
  let current = {};
  try { current = JSON.parse(getSettingVal('ftp_scan_config', '{}')); } catch { current = {}; }
  const next = {
    ...current,
    login_error: Math.max(1, Number(login_error) || 5),
    area: { country: Array.isArray(countries) ? countries : [] },
    time: { start_time: Number(start_time) || 0, end_time: Number(end_time) || 23 },
    upload_shell: Array.isArray(upload_shell) ? upload_shell : [],
    auto_scan: auto_scan !== undefined ? Boolean(auto_scan) : Boolean(current.auto_scan),
    cron_task_status: (auto_scan !== undefined ? Boolean(auto_scan) : Boolean(current.auto_scan)) ? 1 : 0,
  };
  setSettingVal('ftp_scan_config', JSON.stringify(next));
  res.json(next);
});

app.post('/api/ftp/log-analysis/scan', requireAuth, (req, res) => {
  const { types = ['login_error', 'area', 'upload_shell', 'time', 'anonymous'], usernames = [] } = req.body || {};
  let cfg = { login_error: 5, area: { country: ['Local', 'US', 'DE', 'SG'] }, time: { start_time: 6, end_time: 23 }, upload_shell: ['.php', '.sh', '.py'] };
  try { cfg = { ...cfg, ...JSON.parse(getSettingVal('ftp_scan_config', '{}')) }; } catch { /* ignore */ }
  const whitelist = new Set(db.prepare('SELECT ip FROM ftp_whitelist').all().map((r) => r.ip));
  const accountsMap = Object.fromEntries(db.prepare('SELECT id, username FROM ftp_accounts').all().map((a) => [a.username, a.id]));
  const logs = db.prepare('SELECT * FROM ftp_logs ORDER BY id DESC').all();

  const risks = [];
  const failMap = {};
  for (const e of logs) {
    if (whitelist.has(e.ip)) continue;
    if (Array.isArray(usernames) && usernames.length > 0 && !usernames.includes(e.username)) continue;
    const uid = accountsMap[e.username] ?? 0;
    if (e.action_type === 'login_fail' && types.includes('login_error')) {
      const k = `${e.username}__${e.ip}`;
      failMap[k] = (failMap[k] || 0) + 1;
    }
    if (types.includes('anonymous') && e.username.toLowerCase() === 'anonymous') {
      risks.push({ id: 0, user: 'anonymous', ip: e.ip, type: 'Anonymous user login', exec_time: e.in_time });
    }
    if (types.includes('upload_shell') && e.action_type === 'upload') {
      const exts = cfg.upload_shell || ['.php', '.sh', '.py'];
      if (exts.some((ext) => e.file_path.toLowerCase().endsWith(ext.toLowerCase()))) {
        risks.push({ id: uid, user: e.username, ip: e.ip, type: `Upload script (${e.file_path})`, exec_time: e.in_time });
      }
    }
    if (types.includes('area') && e.log_kind === 'login') {
      const allowedCountries = cfg.area?.country || [];
      if (allowedCountries.length > 0 && !allowedCountries.includes(e.country)) {
        risks.push({ id: uid, user: e.username, ip: e.ip, type: `Abnormal login area (${e.country})`, exec_time: e.in_time });
      }
    }
  }
  const threshold = Number(cfg.login_error) || 5;
  for (const [k, count] of Object.entries(failMap)) {
    if (count >= threshold) {
      const [user, ip] = k.split('__');
      risks.push({ id: accountsMap[user] ?? 0, user, ip, type: `Multiple login failures (${count}x)`, exec_time: new Date().toISOString().replace('T', ' ').slice(0, 19) });
    }
  }
  res.json({ risks, total: risks.length });
});

app.get('/api/ftp/whitelist', requireAuth, (req, res) => {
  res.json({ ips: db.prepare('SELECT ip FROM ftp_whitelist ORDER BY id DESC').all().map((r) => r.ip) });
});

app.post('/api/ftp/whitelist', requireAuth, (req, res) => {
  const ip = String(req.body?.ip || '').trim();
  if (!net.isIP(ip)) return res.status(400).json({ error: 'Invalid IP address' });
  db.prepare('INSERT OR IGNORE INTO ftp_whitelist (ip) VALUES (?)').run(ip);
  res.json({ ips: db.prepare('SELECT ip FROM ftp_whitelist ORDER BY id DESC').all().map((r) => r.ip) });
});

app.delete('/api/ftp/whitelist/:ip', requireAuth, (req, res) => {
  db.prepare('DELETE FROM ftp_whitelist WHERE ip = ?').run(req.params.ip);
  res.json({ ips: db.prepare('SELECT ip FROM ftp_whitelist ORDER BY id DESC').all().map((r) => r.ip) });
});

app.post('/api/ftp/batch-delete', requireAuth, (req, res) => {
  const ids = Array.isArray(req.body?.ids) ? req.body.ids : [];
  const results = [];
  for (const id of ids) {
    const acct = db.prepare('SELECT id, username FROM ftp_accounts WHERE id = ?').get(id);
    if (!acct) {
      results.push({ id, username: `#${id}`, ok: false, msg: 'Not found' });
      continue;
    }
    db.prepare('DELETE FROM ftp_accounts WHERE id = ?').run(id);
    results.push({ id, username: acct.username, ok: true, msg: 'Deleted' });
  }
  res.json({ results });
});

app.put('/api/ftp/:id', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  const { password, status, note, quota_mb } = req.body || {};
  if (password !== undefined && String(password).length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters' });
  }
  db.prepare('UPDATE ftp_accounts SET password = ?, status = ?, note = ?, quota_mb = ? WHERE id = ?').run(
    password ?? acct.password,
    status ?? acct.status,
    note !== undefined ? String(note) : acct.note,
    quota_mb !== undefined ? Number(quota_mb) || 0 : acct.quota_mb,
    acct.id
  );
  res.json(db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(acct.id));
});

app.put('/api/ftp/:id/password', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  const password = String(req.body?.password || '').trim();
  if (password.length < 6) return res.status(400).json({ error: 'Password must be at least 6 characters' });
  db.prepare('UPDATE ftp_accounts SET password = ? WHERE id = ?').run(password, acct.id);
  res.json({ updated: true, weak_password: WEAK_FTP_PASSWORDS.has(password) });
});

app.put('/api/ftp/:id/home', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  let safeHome;
  try {
    safeHome = validateFtpHomePath(req.body?.document_root);
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
  const migrate = Boolean(req.body?.migrate);
  const oldSub = acct.document_root.replace(/^\/www\/wwwroot\/?/, '');
  const newSub = safeHome.replace(/^\/www\/wwwroot\/?/, '');
  if (newSub && !newSub.includes('..')) {
    const newFull = path.join(SANDBOX_FILES_ROOT, newSub);
    fs.mkdirSync(newFull, { recursive: true });
    if (migrate && oldSub && oldSub !== newSub) {
      const oldFull = path.join(SANDBOX_FILES_ROOT, oldSub);
      if (fs.existsSync(oldFull)) {
        fs.cpSync(oldFull, newFull, { recursive: true });
      }
    }
  }
  db.prepare('UPDATE ftp_accounts SET document_root = ? WHERE id = ?').run(safeHome, acct.id);
  res.json({ id: acct.id, document_root: safeHome, migrated: migrate });
});

app.put('/api/ftp/:id/note', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  db.prepare('UPDATE ftp_accounts SET note = ? WHERE id = ?').run(String(req.body?.note || ''), acct.id);
  res.json(db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(acct.id));
});

app.put('/api/ftp/:id/quota', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  const quota_mb = Math.max(0, Number(req.body?.quota_mb) || 0);
  db.prepare('UPDATE ftp_accounts SET quota_mb = ? WHERE id = ?').run(quota_mb, acct.id);
  res.json(db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(acct.id));
});

app.get('/api/ftp/:id/logs/login', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  const search = String(req.query.search || '').trim().toLowerCase();
  let rows = db.prepare("SELECT * FROM ftp_logs WHERE username = ? AND log_kind = 'login' ORDER BY id DESC").all(acct.username);
  if (search) rows = rows.filter((r) => r.ip.toLowerCase().includes(search) || r.status.toLowerCase().includes(search) || r.in_time.includes(search));
  res.json({ total: rows.length, data: rows.map((r) => ({ id: r.id, user: r.username, ip: r.ip, status: r.status, in_time: r.in_time, out_time: r.out_time })) });
});

app.get('/api/ftp/:id/logs/action', requireAuth, (req, res) => {
  const acct = db.prepare('SELECT * FROM ftp_accounts WHERE id = ?').get(req.params.id);
  if (!acct) return res.status(404).json({ error: 'FTP account not found' });
  const type = String(req.query.type || 'all');
  const search = String(req.query.search || '').trim().toLowerCase();
  let rows = db.prepare("SELECT * FROM ftp_logs WHERE username = ? AND log_kind = 'action' ORDER BY id DESC").all(acct.username);
  if (type !== 'all') rows = rows.filter((r) => r.action_type === type);
  if (search) rows = rows.filter((r) => r.ip.toLowerCase().includes(search) || r.file_path.toLowerCase().includes(search) || r.action_type.includes(search));
  res.json({ total: rows.length, data: rows.map((r) => ({ id: r.id, name: r.username, ip: r.ip, file: r.file_path, type: r.action_type, time: r.in_time })) });
});

app.delete('/api/ftp/:id', requireAuth, (req, res) => {
  db.prepare('DELETE FROM ftp_accounts WHERE id = ?').run(req.params.id);
  res.json({ deleted: true });
});

// --- 5. Databases ---
app.get('/api/databases', requireAuth, (req, res) => {
  res.json(db.prepare('SELECT * FROM databases ORDER BY id DESC').all());
});

app.post('/api/databases', requireAuth, (req, res) => {
  const { engine = 'mysql', db_name, username, password, location = 'localhost', note = '' } = req.body || {};
  if (!db_name || !username || !password) return res.status(400).json({ error: 'db_name, username, and password required' });
  try {
    const info = db.prepare(
      'INSERT INTO databases (engine, db_name, username, password, location, note) VALUES (?, ?, ?, ?, ?, ?)'
    ).run(engine, db_name.trim(), username.trim(), password, location, note);
    res.status(201).json(db.prepare('SELECT * FROM databases WHERE id = ?').get(info.lastInsertRowid));
  } catch (err) {
    res.status(409).json({ error: err.message });
  }
});

app.put('/api/databases/:id/password', requireAuth, (req, res) => {
  const { password } = req.body || {};
  if (!password) return res.status(400).json({ error: 'New password required' });
  db.prepare('UPDATE databases SET password = ? WHERE id = ?').run(password, req.params.id);
  res.json(db.prepare('SELECT * FROM databases WHERE id = ?').get(req.params.id));
});

app.post('/api/databases/:id/backup', requireAuth, (req, res) => {
  db.prepare('UPDATE databases SET backup_count = backup_count + 1 WHERE id = ?').run(req.params.id);
  res.json(db.prepare('SELECT * FROM databases WHERE id = ?').get(req.params.id));
});

app.post('/api/databases/:id/restore', requireAuth, (req, res) => {
  res.json({ restored: true, id: Number(req.params.id), timestamp: new Date().toISOString() });
});

app.delete('/api/databases/:id', requireAuth, (req, res) => {
  db.prepare('DELETE FROM databases WHERE id = ?').run(req.params.id);
  res.json({ deleted: true });
});

// --- 6. File Manager ---
app.get('/api/files/list', requireAuth, (req, res) => {
  try {
    const rel = String(req.query.path || '');
    const dir = resolveSafeFilePath(rel);
    if (!fs.existsSync(dir)) return res.status(404).json({ error: 'Directory not found' });
    const items = fs.readdirSync(dir, { withFileTypes: true }).map((entry) => {
      const full = path.join(dir, entry.name);
      const stat = fs.statSync(full);
      const relItem = path.relative(SANDBOX_FILES_ROOT, full).replace(/\\/g, '/');
      return {
        name: entry.name,
        path: relItem,
        isDir: entry.isDirectory(),
        size: stat.size,
        mode: (stat.mode & 0o777).toString(8).padStart(4, '0'),
        modifiedAt: stat.mtime.toISOString(),
      };
    });
    items.sort((a, b) => Number(b.isDir) - Number(a.isDir) || a.name.localeCompare(b.name));
    return res.json({ path: rel, entries: items });
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
});

app.get('/api/files/read', requireAuth, (req, res) => {
  try {
    const file = resolveSafeFilePath(String(req.query.path || ''));
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) return res.status(404).json({ error: 'File not found' });
    return res.json({ path: req.query.path, content: fs.readFileSync(file, 'utf8') });
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
});

app.post('/api/files/write', requireAuth, (req, res) => {
  try {
    const { path: relPath, content = '' } = req.body || {};
    const file = resolveSafeFilePath(relPath);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content, 'utf8');
    return res.json({ saved: true, path: relPath });
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
});

app.post('/api/files/mkdir', requireAuth, (req, res) => {
  try {
    const dir = resolveSafeFilePath(req.body?.path || '');
    fs.mkdirSync(dir, { recursive: true });
    return res.status(201).json({ created: true });
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
});

app.post('/api/files/rename', requireAuth, (req, res) => {
  try {
    const src = resolveSafeFilePath(req.body?.source || '');
    const dst = resolveSafeFilePath(req.body?.destination || '');
    fs.renameSync(src, dst);
    return res.json({ renamed: true });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
});

app.post('/api/files/chmod', requireAuth, (req, res) => {
  try {
    const target = resolveSafeFilePath(req.body?.path || '');
    const mode = parseInt(String(req.body?.mode || '0644'), 8);
    fs.chmodSync(target, mode);
    return res.json({ updated: true, mode: req.body?.mode });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
});

app.post('/api/files/upload', requireAuth, upload.single('file'), (req, res) => {
  try {
    const destDir = resolveSafeFilePath(req.body?.path || '');
    fs.mkdirSync(destDir, { recursive: true });
    const target = path.join(destDir, path.basename(req.file.originalname));
    fs.renameSync(req.file.path, target);
    return res.json({ uploaded: true, name: req.file.originalname });
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
});

app.delete('/api/files', requireAuth, (req, res) => {
  try {
    const target = resolveSafeFilePath(String(req.query.path || ''));
    if (target === SANDBOX_FILES_ROOT) return res.status(400).json({ error: 'Cannot delete root' });
    fs.rmSync(target, { recursive: true, force: true });
    return res.json({ deleted: true });
  } catch (err) {
    return res.status(403).json({ error: err.message });
  }
});

// --- 7. Cron Jobs ---
app.get('/api/cron', requireAuth, (req, res) => {
  res.json(db.prepare('SELECT * FROM cron_jobs ORDER BY id DESC').all());
});

app.post('/api/cron', requireAuth, (req, res) => {
  const { name, task_type = 'shell', schedule, execute_user = 'root', script_content } = req.body || {};
  if (!name || !schedule || !script_content) return res.status(400).json({ error: 'Missing required fields' });
  const info = db.prepare(
    'INSERT INTO cron_jobs (name, task_type, schedule, execute_user, script_content) VALUES (?, ?, ?, ?, ?)'
  ).run(name, task_type, schedule, execute_user, script_content);
  res.status(201).json(db.prepare('SELECT * FROM cron_jobs WHERE id = ?').get(info.lastInsertRowid));
});

app.post('/api/cron/:id/run', requireAuth, (req, res) => {
  const job = db.prepare('SELECT * FROM cron_jobs WHERE id = ?').get(req.params.id);
  if (!job) return res.status(404).json({ error: 'Cron job not found' });
  const now = new Date().toISOString();
  const out = `[${now}] Executed '${job.name}' (${job.task_type}) successfully.`;
  db.prepare('UPDATE cron_jobs SET last_run_at = ?, last_output = ? WHERE id = ?').run(now, out, job.id);
  res.json(db.prepare('SELECT * FROM cron_jobs WHERE id = ?').get(job.id));
});

app.post('/api/cron/:id/toggle', requireAuth, (req, res) => {
  const job = db.prepare('SELECT * FROM cron_jobs WHERE id = ?').get(req.params.id);
  if (!job) return res.status(404).json({ error: 'Cron job not found' });
  const nextStatus = job.status === 'active' ? 'paused' : 'active';
  db.prepare('UPDATE cron_jobs SET status = ? WHERE id = ?').run(nextStatus, job.id);
  res.json(db.prepare('SELECT * FROM cron_jobs WHERE id = ?').get(job.id));
});

app.delete('/api/cron/:id', requireAuth, (req, res) => {
  db.prepare('DELETE FROM cron_jobs WHERE id = ?').run(req.params.id);
  res.json({ deleted: true });
});

// --- 8. Security & Firewall ---
app.get('/api/security/firewall', requireAuth, (req, res) => {
  const rules = db.prepare('SELECT * FROM firewall_rules ORDER BY id DESC').all();
  const fw = db.prepare("SELECT value FROM settings WHERE key = 'firewall_enabled'").get()?.value === 'true';
  const icmp = db.prepare("SELECT value FROM settings WHERE key = 'block_icmp'").get()?.value === 'true';
  res.json({ firewall_enabled: fw, block_icmp: icmp, rules });
});

app.post('/api/security/firewall/rules', requireAuth, (req, res) => {
  const { protocol = 'tcp', port, strategy = 'allow', direction = 'inbound', source_ip = '0.0.0.0/0', remarks = '' } = req.body || {};
  if (!port) return res.status(400).json({ error: 'Port is required' });
  const info = db.prepare(
    'INSERT INTO firewall_rules (protocol, port, strategy, direction, source_ip, remarks) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(protocol, String(port), strategy, direction, source_ip, remarks);
  res.status(201).json(db.prepare('SELECT * FROM firewall_rules WHERE id = ?').get(info.lastInsertRowid));
});

app.delete('/api/security/firewall/rules/:id', requireAuth, (req, res) => {
  db.prepare('DELETE FROM firewall_rules WHERE id = ?').run(req.params.id);
  res.json({ deleted: true });
});

app.post('/api/security/scan', requireAuth, (req, res) => {
  res.json({ scannedAt: new Date().toISOString(), risksFound: 0, checks: ['SSH Root Key', 'UFW Active', 'PHP Expose Off', 'Open Ports Audit'] });
});

// --- 9. App Store ---
app.get('/api/apps', requireAuth, (req, res) => {
  res.json(db.prepare('SELECT * FROM software_apps ORDER BY id ASC').all());
});

app.post('/api/apps/:id/install', requireAuth, (req, res) => {
  db.prepare("UPDATE software_apps SET status = 'installed' WHERE id = ?").run(req.params.id);
  res.json(db.prepare('SELECT * FROM software_apps WHERE id = ?').get(req.params.id));
});

app.post('/api/apps/:id/uninstall', requireAuth, (req, res) => {
  db.prepare("UPDATE software_apps SET status = 'not_installed', display_on_home = 0 WHERE id = ?").run(req.params.id);
  res.json(db.prepare('SELECT * FROM software_apps WHERE id = ?').get(req.params.id));
});

app.post('/api/apps/:id/home-toggle', requireAuth, (req, res) => {
  const appRow = db.prepare('SELECT * FROM software_apps WHERE id = ?').get(req.params.id);
  if (!appRow) return res.status(404).json({ error: 'App not found' });
  db.prepare('UPDATE software_apps SET display_on_home = ? WHERE id = ?').run(appRow.display_on_home ? 0 : 1, appRow.id);
  res.json(db.prepare('SELECT * FROM software_apps WHERE id = ?').get(appRow.id));
});

// --- 10. System Monitor (Historical Data) ---
app.get('/api/monitor/history', requireAuth, (req, res) => {
  const range = String(req.query.range || 'today');
  const points = range === '7d' ? 28 : 24;
  const series = Array.from({ length: points }, (_, i) => {
    const label = range === '7d' ? `Day ${i + 1}` : `${String(i).padStart(2, '0')}:00`;
    return {
      time: label,
      load: Number((0.15 + Math.sin(i / 3) * 0.12 + Math.random() * 0.15).toFixed(2)),
      cpu: Math.round(14 + Math.cos(i / 2) * 8 + Math.random() * 12),
      memory: Math.round(28 + Math.sin(i / 4) * 5 + Math.random() * 4),
      diskIo: Math.round(5 + Math.random() * 25),
      netIn: Math.round(120 + Math.random() * 420),
      netOut: Math.round(80 + Math.random() * 280),
      swap: Math.round(2 + Math.random() * 3),
    };
  });
  res.json({ range, series });
});

// --- 11. Settings ---
app.get('/api/settings', requireAuth, (req, res) => {
  const rows = db.prepare('SELECT * FROM settings').all();
  const map = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  res.json(map);
});

app.put('/api/settings', requireAuth, (req, res) => {
  const updates = req.body || {};
  const stmt = db.prepare('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)');
  for (const [k, v] of Object.entries(updates)) {
    stmt.run(k, String(v));
  }
  const rows = db.prepare('SELECT * FROM settings').all();
  res.json(Object.fromEntries(rows.map((r) => [r.key, r.value])));
});

// --- 12. Terminal Command Runner (Safe Simulated/Host Info) ---
app.post('/api/terminal/exec', requireAuth, (req, res) => {
  const cmd = String(req.body?.command || '').trim();
  if (!cmd) return res.json({ output: '' });
  if (cmd === 'uname -a') return res.json({ output: `${os.type()} ${os.hostname()} ${os.release()} ${os.arch()}` });
  if (cmd === 'whoami') return res.json({ output: req.user.username });
  if (cmd === 'uptime') return res.json({ output: `up ${Math.floor(os.uptime() / 60)} minutes, load average: ${os.loadavg().map((n) => n.toFixed(2)).join(', ')}` });
  if (cmd === 'ls') return res.json({ output: fs.readdirSync(SANDBOX_FILES_ROOT).join('  ') });
  if (cmd === 'help') return res.json({ output: 'Available commands: uname -a, whoami, uptime, ls, help' });
  return res.json({ output: `nexopanel-sh: executed '${cmd}' (exit 0)` });
});

app.listen(PORT, () => {
  console.log(`NexoPanel Express API running at http://localhost:${PORT}`);
});
