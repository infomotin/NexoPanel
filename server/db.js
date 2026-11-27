import { DatabaseSync } from 'node:sqlite';
import bcrypt from 'bcryptjs';
import path from 'node:path';
import fs from 'node:fs';

const DATA_DIR = path.resolve(process.cwd(), 'data');
fs.mkdirSync(DATA_DIR, { recursive: true });

export const SANDBOX_FILES_ROOT = path.resolve(DATA_DIR, 'wwwroot');
fs.mkdirSync(SANDBOX_FILES_ROOT, { recursive: true });

const dbPath = path.join(DATA_DIR, 'panel.db');
export const db = new DatabaseSync(dbPath);

db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Administrator'
  );

  CREATE TABLE IF NOT EXISTS websites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    project_type TEXT NOT NULL DEFAULT 'php',
    php_version TEXT NOT NULL DEFAULT '8.2',
    document_root TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    ssl_enabled INTEGER NOT NULL DEFAULT 0,
    force_https INTEGER NOT NULL DEFAULT 0,
    remarks TEXT NOT NULL DEFAULT '',
    backups_count INTEGER NOT NULL DEFAULT 0,
    nginx_config TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS ftp_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    document_root TEXT NOT NULL,
    quota_mb INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    note TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS ftp_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    log_kind TEXT NOT NULL DEFAULT 'login',
    action_type TEXT NOT NULL DEFAULT 'login_success',
    ip TEXT NOT NULL DEFAULT '127.0.0.1',
    country TEXT NOT NULL DEFAULT 'Local',
    file_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Success',
    in_time TEXT NOT NULL DEFAULT (datetime('now')),
    out_time TEXT NOT NULL DEFAULT '--',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS ftp_whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS databases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    engine TEXT NOT NULL DEFAULT 'mysql',
    db_name TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT 'localhost',
    quota_mb INTEGER NOT NULL DEFAULT 0,
    backup_count INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'shell',
    schedule TEXT NOT NULL,
    execute_user TEXT NOT NULL DEFAULT 'root',
    script_content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    retention_count INTEGER NOT NULL DEFAULT 3,
    last_run_at TEXT,
    last_output TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS firewall_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol TEXT NOT NULL DEFAULT 'tcp',
    port TEXT NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'allow',
    direction TEXT NOT NULL DEFAULT 'inbound',
    source_ip TEXT NOT NULL DEFAULT '0.0.0.0/0',
    remarks TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS software_apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    category TEXT NOT NULL,
    developer TEXT NOT NULL DEFAULT 'Official',
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_installed',
    display_on_home INTEGER NOT NULL DEFAULT 0
  );

  CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`);

function seedDefaults() {
  const admin = db.prepare('SELECT id FROM users WHERE username = ?').get('aapanel');
  if (!admin) {
    const hash = bcrypt.hashSync('aapanel', 10);
    db.prepare('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)').run('aapanel', hash, 'Administrator');
    const admin2 = db.prepare('SELECT id FROM users WHERE username = ?').get('admin');
    if (!admin2) {
      db.prepare('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)').run('admin', hash, 'Administrator');
    }
  }

  const siteCount = db.prepare('SELECT COUNT(*) as c FROM websites').get().c;
  if (siteCount === 0) {
    const insertSite = db.prepare(
      'INSERT INTO websites (domain, project_type, php_version, document_root, status, ssl_enabled, remarks, backups_count, nginx_config) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
    );
    insertSite.run('app.nexopanel.local', 'php', '8.2', '/www/wwwroot/app.nexopanel.local', 'running', 1, 'Production Portal', 2, 'server {\n  listen 80;\n  server_name app.nexopanel.local;\n  root /www/wwwroot/app.nexopanel.local;\n}');
    insertSite.run('api.nexopanel.local', 'nodejs', 'static', '/www/wwwroot/api.nexopanel.local', 'running', 1, 'Node API Gateway', 1, 'server {\n  listen 80;\n  server_name api.nexopanel.local;\n  location / { proxy_pass http://127.0.0.1:4000; }\n}');
    insertSite.run('docs.nexopanel.local', 'php', '8.3', '/www/wwwroot/docs.nexopanel.local', 'stopped', 0, 'Documentation Site', 0, 'server {\n  listen 80;\n  server_name docs.nexopanel.local;\n}');
  }

  const dbCount = db.prepare('SELECT COUNT(*) as c FROM databases').get().c;
  if (dbCount === 0) {
    db.prepare('INSERT INTO databases (engine, db_name, username, password, location, backup_count, note) VALUES (?, ?, ?, ?, ?, ?, ?)').run(
      'mysql', 'nexopanel_prod', 'np_user', 'S3cureDbPass!', 'localhost', 1, 'Main app database'
    );
  }

  const ftpCount = db.prepare('SELECT COUNT(*) as c FROM ftp_accounts').get().c;
  if (ftpCount === 0) {
    db.prepare('INSERT INTO ftp_accounts (username, password, document_root, quota_mb, status, note) VALUES (?, ?, ?, ?, ?, ?)').run(
      'ftp_app', 'FtpPass123!', '/www/wwwroot/app.nexopanel.local', 2048, 'active', 'Site deployment'
    );
  }

  try {
    db.exec("ALTER TABLE ftp_accounts ADD COLUMN expires_at TEXT");
  } catch { /* column already exists */ }

  const ftpLogCount = db.prepare('SELECT COUNT(*) as c FROM ftp_logs').get().c;
  if (ftpLogCount === 0) {
    const insLog = db.prepare(
      'INSERT INTO ftp_logs (username, log_kind, action_type, ip, country, file_path, status, in_time, out_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
    );
    const nowIso = new Date().toISOString().replace('T', ' ').slice(0, 19);
    insLog.run('ftp_app', 'login', 'login_success', '192.168.1.45', 'Local', '', 'Success', nowIso, nowIso);
    insLog.run('ftp_app', 'action', 'upload', '192.168.1.45', 'Local', '/www/wwwroot/app.nexopanel.local/index.html', 'Success', nowIso, '--');
    insLog.run('ftp_app', 'action', 'download', '192.168.1.45', 'Local', '/www/wwwroot/app.nexopanel.local/config.json', 'Success', nowIso, '--');
    insLog.run('ftp_app', 'action', 'upload', '203.0.113.77', 'Unknown', '/www/wwwroot/app.nexopanel.local/shell.php', 'Success', nowIso, '--');
    for (let i = 0; i < 6; i++) {
      insLog.run('ftp_app', 'login', 'login_fail', '198.51.100.24', 'Unknown', '', 'Failure', nowIso, nowIso);
    }
  }

  const fwCount = db.prepare('SELECT COUNT(*) as c FROM firewall_rules').get().c;
  if (fwCount === 0) {
    const insFw = db.prepare('INSERT INTO firewall_rules (protocol, port, strategy, direction, source_ip, remarks) VALUES (?, ?, ?, ?, ?, ?)');
    insFw.run('tcp', '22', 'allow', 'inbound', '0.0.0.0/0', 'SSH Access');
    insFw.run('tcp', '80', 'allow', 'inbound', '0.0.0.0/0', 'HTTP Traffic');
    insFw.run('tcp', '443', 'allow', 'inbound', '0.0.0.0/0', 'HTTPS Traffic');
    insFw.run('tcp', '8888', 'allow', 'inbound', '0.0.0.0/0', 'Panel Port');
  }

  const cronCount = db.prepare('SELECT COUNT(*) as c FROM cron_jobs').get().c;
  if (cronCount === 0) {
    db.prepare('INSERT INTO cron_jobs (name, task_type, schedule, execute_user, script_content, status, last_run_at, last_output) VALUES (?, ?, ?, ?, ?, ?, ?, ?)').run(
      'Nightly Site Backup', 'backup_site', '0 2 * * *', 'root', 'tar -czf /www/backup/sites.tar.gz /www/wwwroot', 'active', new Date().toISOString(), 'Backup completed (42 MB)'
    );
  }

  const appCount = db.prepare('SELECT COUNT(*) as c FROM software_apps').get().c;
  if (appCount === 0) {
    const insApp = db.prepare('INSERT INTO software_apps (slug, name, version, category, developer, description, status, display_on_home) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    insApp.run('nginx', 'Nginx', '1.24.0', 'Deployment', 'Official', 'High-performance HTTP and reverse proxy server', 'installed', 1);
    insApp.run('mysql', 'MySQL', '5.7.43', 'Deployment', 'Official', 'Popular open-source relational database', 'installed', 1);
    insApp.run('php82', 'PHP 8.2', '8.2.17', 'Deployment', 'Official', 'Fast, flexible server-side scripting runtime', 'installed', 1);
    insApp.run('pureftpd', 'Pure-Ftpd', '1.0.49', 'Deployment', 'Official', 'Secure, production-quality FTP server', 'installed', 1);
    insApp.run('redis', 'Redis', '7.2.7', 'Deployment', 'Official', 'In-memory key-value data store', 'installed', 1);
    insApp.run('phpmyadmin', 'phpMyAdmin', '5.2.1', 'Tools', 'Official', 'Web-based MySQL administration tool', 'installed', 1);
    insApp.run('docker', 'Docker Engine', '26.1.0', 'Tools', 'Official', 'Container runtime and orchestration', 'not_installed', 0);
    insApp.run('waf', 'Website Firewall', '4.2.0', 'Plug-ins', 'Security', 'L7 WAF protecting against SQLi and XSS', 'not_installed', 0);
  }

  const defaultSettings = {
    panel_port: '8888',
    security_entrance: '/fdgi87jbn',
    panel_domain: '',
    panel_ssl: 'false',
    firewall_enabled: 'true',
    block_icmp: 'false',
    monitoring_enabled: 'true',
    monitoring_days: '30',
    memo: 'Reset every 3 hours. Demo workspace ready.',
    api_enabled: 'true',
    ftp_port: '21',
    ftp_log_service: 'start',
    ftp_no_anonymous: 'true',
    ftp_forbid_root: 'true',
    ftp_scan_config: JSON.stringify({
      login_error: 5,
      area: { country: ['Local', 'US', 'DE', 'SG'] },
      time: { start_time: 6, end_time: 23 },
      upload_shell: ['.php', '.sh', '.py', '.jsp', '.asp'],
      auto_scan: false,
      cron_task_status: 0,
    }),
  };
  const insSet = db.prepare('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)');
  for (const [k, v] of Object.entries(defaultSettings)) {
    insSet.run(k, v);
  }

  // Seed sample files inside SANDBOX_FILES_ROOT
  const sampleSiteDir = path.join(SANDBOX_FILES_ROOT, 'app.nexopanel.local');
  fs.mkdirSync(sampleSiteDir, { recursive: true });
  const indexHtml = path.join(sampleSiteDir, 'index.html');
  if (!fs.existsSync(indexHtml)) {
    fs.writeFileSync(indexHtml, '<!doctype html>\n<html>\n<head><title>NexoPanel App</title></head>\n<body><h1>Welcome to app.nexopanel.local</h1></body>\n</html>\n');
    fs.writeFileSync(path.join(sampleSiteDir, 'config.json'), JSON.stringify({ env: 'production', debug: false }, null, 2));
  }
}

seedDefaults();
