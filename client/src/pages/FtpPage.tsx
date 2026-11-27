import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Eye, EyeOff, Copy, Check, Link2, Search, Shield, ShieldAlert,
  Play, Pause, Folder, KeyRound, FileText, Trash2, Settings, X,
  RefreshCw, AlertTriangle, CheckCircle2, FolderInput
} from 'lucide-react';
import { apiFetch } from '../api';

function generatePassword(len = 14) {
  const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%';
  return Array.from({ length: len }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
}

export default function FtpPage() {
  const [overview, setOverview] = useState<any>({
    items: [],
    total: 0,
    page: 1,
    limit: 20,
    port: 21,
    passive_range: '39000-40000',
    service_installed: true,
    service_running: true,
    log_service_status: 'start',
    security: { no_anonymous: true, forbid_root: true, weak_password_accounts: [] },
  });
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [batchAction, setBatchAction] = useState('');
  const [revealedIds, setRevealedIds] = useState<Record<number, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [editingNotes, setEditingNotes] = useState<Record<number, string>>({});
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  // Modals
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ username: '', password: generatePassword(12), document_root: '/www/wwwroot', quota_mb: 0, note: '' });
  const [showAddPass, setShowAddPass] = useState(true);

  const [showPort, setShowPort] = useState(false);
  const [portInput, setPortInput] = useState(21);

  const [showSecurity, setShowSecurity] = useState(false);

  const [passModal, setPassModal] = useState<{ open: boolean; row: any; password: string }>({ open: false, row: null, password: '' });
  const [homeModal, setHomeModal] = useState<{ open: boolean; row: any; path: string; migrate: boolean }>({ open: false, row: null, path: '', migrate: false });
  const [quotaModal, setQuotaModal] = useState<{ open: boolean; row: any; quota_mb: number }>({ open: false, row: null, quota_mb: 0 });
  const [batchResults, setBatchResults] = useState<any[] | null>(null);

  // Per-User Logs Modal
  const [logsModal, setLogsModal] = useState<{ open: boolean; row: any; tab: 'login' | 'action' }>({ open: false, row: null, tab: 'login' });
  const [loginLogs, setLoginLogs] = useState<any[]>([]);
  const [actionLogs, setActionLogs] = useState<any[]>([]);
  const [logSearch, setLogSearch] = useState('');
  const [actionTypeFilter, setActionTypeFilter] = useState('all');

  // FTP Log Analysis & Security Scanner Modals
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [scanRisks, setScanRisks] = useState<any[]>([]);
  const [conditionsOpen, setConditionsOpen] = useState(false);
  const [thresholdsOpen, setThresholdsOpen] = useState(false);
  const [whitelistOpen, setWhitelistOpen] = useState(false);
  const [whitelistIps, setWhitelistIps] = useState<string[]>([]);
  const [newWhitelistIp, setNewWhitelistIp] = useState('');
  const [scanConfig, setScanConfig] = useState<any>({
    login_error: 5,
    area: { country: ['Local', 'US', 'DE', 'SG'] },
    time: { start_time: 6, end_time: 23 },
    upload_shell: ['.php', '.sh', '.py', '.jsp', '.asp'],
    auto_scan: false,
  });
  const [scanParams, setScanParams] = useState({
    types: ['login_error', 'area', 'upload_shell', 'time', 'anonymous'],
    day: 30,
    customDay: 7,
    userMode: 'all',
    usernames: [] as string[],
  });

  function flash(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  }

  async function load() {
    const data = await apiFetch(`/ftp/overview?search=${encodeURIComponent(search)}&page=${page}&limit=${limit}`);
    setOverview(data);
    setPortInput(data.port);
    const noteMap: Record<number, string> = {};
    for (const item of data.items || []) {
      noteMap[item.id] = item.note || '';
    }
    setEditingNotes(noteMap);
  }

  useEffect(() => {
    load();
  }, [page, limit]);

  function copyText(text: string, key: string) {
    navigator.clipboard?.writeText(text);
    setCopiedId(key);
    setTimeout(() => setCopiedId(null), 1500);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch('/ftp', { method: 'POST', body: JSON.stringify(addForm) });
      setShowAdd(false);
      setAddForm({ username: '', password: generatePassword(12), document_root: '/www/wwwroot', quota_mb: 0, note: '' });
      flash('FTP user created successfully');
      await load();
    } catch (err: any) {
      flash(err.message, false);
    }
  }

  async function toggleStatus(row: any) {
    const next = row.status === 'active' ? 'disabled' : 'active';
    if (next === 'disabled' && !confirm(`After disabling FTP user [${row.username}], the user loses FTP access. Continue?`)) return;
    await apiFetch(`/ftp/${row.id}`, { method: 'PUT', body: JSON.stringify({ status: next }) });
    flash(`FTP user [${row.username}] ${next === 'active' ? 'activated' : 'stopped'}`);
    await load();
  }

  async function saveNote(row: any) {
    const val = editingNotes[row.id] ?? '';
    if (val === (row.note || '')) return;
    await apiFetch(`/ftp/${row.id}/note`, { method: 'PUT', body: JSON.stringify({ note: val }) });
    flash('Note updated');
    await load();
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await apiFetch(`/ftp/${passModal.row.id}/password`, {
        method: 'PUT',
        body: JSON.stringify({ password: passModal.password }),
      });
      setPassModal({ open: false, row: null, password: '' });
      flash(res.weak_password ? 'Password updated (Warning: consider a stronger password)' : 'FTP password updated');
      await load();
    } catch (err: any) {
      flash(err.message, false);
    }
  }

  async function saveHome(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch(`/ftp/${homeModal.row.id}/home`, {
        method: 'PUT',
        body: JSON.stringify({ document_root: homeModal.path, migrate: homeModal.migrate }),
      });
      setHomeModal({ open: false, row: null, path: '', migrate: false });
      flash('FTP home directory updated');
      await load();
    } catch (err: any) {
      flash(err.message, false);
    }
  }

  async function saveQuota(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch(`/ftp/${quotaModal.row.id}/quota`, {
      method: 'PUT',
      body: JSON.stringify({ quota_mb: Number(quotaModal.quota_mb) || 0 }),
    });
    setQuotaModal({ open: false, row: null, quota_mb: 0 });
    flash('Quota updated');
    await load();
  }

  async function deleteUser(row: any) {
    if (!confirm(`Delete FTP User [${row.username}]? This user will completely lose FTP access.`)) return;
    await apiFetch(`/ftp/${row.id}`, { method: 'DELETE' });
    flash(`Deleted FTP user [${row.username}]`);
    await load();
  }

  async function executeBatch() {
    if (!selectedIds.length || batchAction !== 'delete') return;
    if (!confirm(`Batch delete ${selectedIds.length} selected FTP user(s)?`)) return;
    const res = await apiFetch('/ftp/batch-delete', { method: 'POST', body: JSON.stringify({ ids: selectedIds }) });
    setBatchResults(res.results || []);
    setSelectedIds([]);
    setBatchAction('');
    await load();
  }

  async function savePort(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch('/ftp/port', { method: 'PUT', body: JSON.stringify({ port: Number(portInput) }) });
      setShowPort(false);
      flash(`FTP port changed to ${portInput} (firewall synced)`);
      await load();
    } catch (err: any) {
      flash(err.message, false);
    }
  }

  async function toggleSecuritySetting(field: 'no_anonymous' | 'forbid_root', val: boolean) {
    await apiFetch('/ftp/security', { method: 'PUT', body: JSON.stringify({ [field]: val }) });
    flash('Pure-FTPd security configuration updated');
    await load();
  }

  async function openUserLogs(row: any) {
    if (overview.log_service_status !== 'start') {
      if (!confirm('FTP Log Service is currently disabled. Enable FTP Log Service to record and inspect access logs?')) return;
      await apiFetch('/ftp/log-service', { method: 'POST', body: JSON.stringify({ exec_name: 'start' }) });
      await load();
    }
    setLogsModal({ open: true, row, tab: 'login' });
    setLogSearch('');
    await fetchUserLogs(row.id, 'login', '', 'all');
  }

  async function fetchUserLogs(ftpId: number, tab: 'login' | 'action', q: string, actType: string) {
    if (tab === 'login') {
      const res = await apiFetch(`/ftp/${ftpId}/logs/login?search=${encodeURIComponent(q)}`);
      setLoginLogs(res.data || []);
    } else {
      const res = await apiFetch(`/ftp/${ftpId}/logs/action?type=${encodeURIComponent(actType)}&search=${encodeURIComponent(q)}`);
      setActionLogs(res.data || []);
    }
  }

  async function openLogAnalysis() {
    if (overview.log_service_status !== 'start') {
      if (!confirm('Enable FTP Log Service? After enabling, FTP logins and file actions are recorded for security scanning.')) return;
      await apiFetch('/ftp/log-service', { method: 'POST', body: JSON.stringify({ exec_name: 'start' }) });
      await load();
    }
    const cfg = await apiFetch('/ftp/log-analysis/config');
    setScanConfig(cfg);
    setScanned(false);
    setAnalysisOpen(true);
  }

  async function runLogScan(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const res = await apiFetch('/ftp/log-analysis/scan', {
      method: 'POST',
      body: JSON.stringify({
        types: scanParams.types,
        day: scanParams.day === 0 ? scanParams.customDay : scanParams.day,
        usernames: scanParams.userMode === 'custom' ? scanParams.usernames : [],
      }),
    });
    setScanRisks(res.risks || []);
    setScanned(true);
    setConditionsOpen(false);
  }

  async function saveScanThresholds(e: React.FormEvent) {
    e.preventDefault();
    const updated = await apiFetch('/ftp/log-analysis/config', {
      method: 'PUT',
      body: JSON.stringify({
        login_error: Number(scanConfig.login_error),
        countries: Array.isArray(scanConfig.area?.country) ? scanConfig.area.country : [],
        start_time: Number(scanConfig.time?.start_time ?? 0),
        end_time: Number(scanConfig.time?.end_time ?? 23),
        upload_shell: Array.isArray(scanConfig.upload_shell) ? scanConfig.upload_shell : [],
        auto_scan: scanConfig.auto_scan,
      }),
    });
    setScanConfig(updated);
    setThresholdsOpen(false);
    flash('Scan thresholds saved');
  }

  async function openWhitelist() {
    const res = await apiFetch('/ftp/whitelist');
    setWhitelistIps(res.ips || []);
    setWhitelistOpen(true);
  }

  async function addWhitelistIp(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await apiFetch('/ftp/whitelist', { method: 'POST', body: JSON.stringify({ ip: newWhitelistIp }) });
      setWhitelistIps(res.ips || []);
      setNewWhitelistIp('');
      flash('IP added to FTP log whitelist');
    } catch (err: any) {
      flash(err.message, false);
    }
  }

  async function removeWhitelistIp(ip: string) {
    const res = await apiFetch(`/ftp/whitelist/${encodeURIComponent(ip)}`, { method: 'DELETE' });
    setWhitelistIps(res.ips || []);
    flash('IP removed from whitelist');
  }

  async function ignoreRiskIp(ip: string) {
    await apiFetch('/ftp/whitelist', { method: 'POST', body: JSON.stringify({ ip }) });
    flash(`Whitelisted IP ${ip}`);
    await runLogScan();
  }

  const items = overview.items || [];
  const hostAddr = window.location.hostname || '127.0.0.1';
  const ftpAddrUrl = `ftp://${hostAddr}:${overview.port}`;

  return (
    <div className="space-y-3 text-xs">
      {toast && (
        <div className={`fixed top-14 right-5 z-[60] px-4 py-2.5 rounded-md shadow-lg border text-xs font-medium flex items-center gap-2 ${toast.ok ? 'bg-emerald-600 text-white border-emerald-700' : 'bg-rose-600 text-white border-rose-700'}`}>
          {toast.ok ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
          <span>{toast.msg}</span>
        </div>
      )}

      {/* FTP Address & Service Status Banner (aaPanel style) */}
      <div className="bg-white rounded-md border border-slate-200 p-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="flex items-center gap-2.5 text-slate-700">
          <span className="w-2 h-2 rounded-full bg-amber-400"></span>
          <span>FTP address:</span>
          <strong className="font-mono text-slate-900 bg-slate-100 px-2 py-0.5 rounded">{ftpAddrUrl}</strong>
          <button
            onClick={() => copyText(ftpAddrUrl, 'addr')}
            className="text-slate-400 hover:text-emerald-600 p-1"
            title="Copy FTP Address"
          >
            {copiedId === 'addr' ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
          </button>
          <span className="text-slate-400 hidden sm:inline">| Passive Ports: {overview.passive_range}</span>
        </div>

        <div className="flex items-center gap-2">
          {overview.security?.weak_password_accounts?.length > 0 && (
            <button onClick={() => setShowSecurity(true)} className="px-2.5 py-1 rounded bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1 font-medium">
              <ShieldAlert size={13} />
              <span>{overview.security.weak_password_accounts.length} Weak Password(s)</span>
            </button>
          )}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-700 font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span>Pure-Ftpd 1.0.49</span>
          </div>
        </div>
      </div>

      {/* Main Toolbar */}
      <div className="bg-white rounded-md border border-slate-200 p-2.5 flex flex-wrap items-center justify-between gap-2 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setShowAdd(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-3.5 py-1.5 rounded shadow-sm transition-colors">
            Add FTP
          </button>
          <button onClick={() => setShowPort(true)} className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 px-3 py-1.5 rounded transition-colors">
            Change FTP Port
          </button>
          <button onClick={openLogAnalysis} className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 px-3 py-1.5 rounded flex items-center gap-1.5 transition-colors">
            <ShieldAlert size={13} className="text-amber-500" />
            <span>FTP log analysis</span>
          </button>
          <button onClick={() => setShowSecurity(true)} className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 px-3 py-1.5 rounded flex items-center gap-1.5 transition-colors">
            <Shield size={13} className="text-emerald-600" />
            <span>Security Config</span>
          </button>
        </div>

        <form onSubmit={(e) => { e.preventDefault(); setPage(1); load(); }} className="relative flex items-center">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="FTP search"
            className="bg-white border border-slate-300 rounded pl-2.5 pr-8 py-1.5 text-xs focus:outline-none focus:border-emerald-500 w-52"
          />
          <button type="submit" className="absolute right-2 text-slate-400 hover:text-emerald-600">
            <Search size={13} />
          </button>
        </form>
      </div>

      {/* FTP Accounts Table */}
      <div className="bg-white rounded-md border border-slate-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-500 text-[11px] font-medium">
                <th className="py-2.5 px-3 w-8">
                  <input
                    type="checkbox"
                    checked={items.length > 0 && selectedIds.length === items.length}
                    onChange={(e) => setSelectedIds(e.target.checked ? items.map((i: any) => i.id) : [])}
                    className="rounded border-slate-300 text-emerald-600"
                  />
                </th>
                <th className="py-2.5 px-3">Username</th>
                <th className="py-2.5 px-3">Password</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Document Root</th>
                <th className="py-2.5 px-3">Quota</th>
                <th className="py-2.5 px-3">Note</th>
                <th className="py-2.5 px-3 text-right pr-4">Operate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {items.map((a: any) => {
                const isRevealed = Boolean(revealedIds[a.id]);
                const quickConn = `ftp://${a.username}:${a.password}@${hostAddr}:${overview.port}`;
                return (
                  <tr key={a.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2.5 px-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(a.id)}
                        onChange={(e) => {
                          if (e.target.checked) setSelectedIds([...selectedIds, a.id]);
                          else setSelectedIds(selectedIds.filter((x) => x !== a.id));
                        }}
                        className="rounded border-slate-300 text-emerald-600"
                      />
                    </td>
                    <td className="py-2.5 px-3 font-mono font-semibold text-slate-900">{a.username}</td>

                    {/* Password with Eye Reveal, Copy Password, & Quick-Connect Copy */}
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5 font-mono">
                        <span className="text-slate-600 min-w-[85px]">{isRevealed ? a.password : '••••••••••'}</span>
                        <button
                          onClick={() => setRevealedIds({ ...revealedIds, [a.id]: !isRevealed })}
                          className="text-slate-400 hover:text-slate-700 p-0.5"
                          title={isRevealed ? 'Hide password' : 'Show password'}
                        >
                          {isRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                        <button
                          onClick={() => copyText(a.password, `pw-${a.id}`)}
                          className="text-slate-400 hover:text-emerald-600 p-0.5"
                          title="Copy password"
                        >
                          {copiedId === `pw-${a.id}` ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                        </button>
                        <button
                          onClick={() => copyText(quickConn, `qc-${a.id}`)}
                          className="text-slate-400 hover:text-blue-600 p-0.5"
                          title="Copy quick connection URI"
                        >
                          {copiedId === `qc-${a.id}` ? <Check size={13} className="text-blue-600" /> : <Link2 size={13} />}
                        </button>
                      </div>
                    </td>

                    {/* Status Toggle */}
                    <td className="py-2.5 px-3">
                      <button
                        onClick={() => toggleStatus(a)}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                          a.status === 'active'
                            ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                            : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
                        }`}
                      >
                        {a.status === 'active' ? <Play size={10} className="fill-emerald-600" /> : <Pause size={10} className="fill-rose-600" />}
                        <span>{a.status === 'active' ? 'Activated' : 'Stopped'}</span>
                      </button>
                    </td>

                    {/* Document Root Link */}
                    <td className="py-2.5 px-3">
                      <Link
                        to={`/files?path=${encodeURIComponent(a.document_root.replace(/^\/www\/wwwroot\/?/, ''))}`}
                        className="font-mono text-[11px] text-emerald-600 hover:underline flex items-center gap-1"
                      >
                        <Folder size={12} />
                        <span>{a.document_root}</span>
                      </Link>
                    </td>

                    {/* Quota */}
                    <td className="py-2.5 px-3">
                      <button
                        onClick={() => setQuotaModal({ open: true, row: a, quota_mb: a.quota_mb || 0 })}
                        className="text-slate-600 hover:text-emerald-600 underline decoration-dotted text-[11px]"
                      >
                        {a.quota_mb ? `${a.quota_mb} MB` : 'Unlimited'}
                      </button>
                    </td>

                    {/* Inline Editable Note */}
                    <td className="py-2.5 px-3">
                      <input
                        value={editingNotes[a.id] ?? ''}
                        onChange={(e) => setEditingNotes({ ...editingNotes, [a.id]: e.target.value })}
                        onBlur={() => saveNote(a)}
                        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
                        placeholder="Edit notes"
                        className="bg-transparent border border-transparent hover:border-slate-200 focus:border-emerald-500 focus:bg-white rounded px-1.5 py-0.5 text-xs w-36 focus:outline-none"
                      />
                    </td>

                    {/* Operate Actions: Set Path | Password | Log | Delete */}
                    <td className="py-2.5 px-3 text-right pr-4">
                      <div className="inline-flex items-center gap-2 text-[11px]">
                        <button
                          onClick={() => setHomeModal({ open: true, row: a, path: a.document_root, migrate: false })}
                          className="text-emerald-600 hover:underline font-medium"
                        >
                          Set Path
                        </button>
                        <span className="text-slate-300">|</span>
                        <button
                          onClick={() => setPassModal({ open: true, row: a, password: a.password })}
                          className="text-emerald-600 hover:underline font-medium"
                        >
                          Password
                        </button>
                        <span className="text-slate-300">|</span>
                        <button
                          onClick={() => openUserLogs(a)}
                          className="text-blue-600 hover:underline font-medium"
                        >
                          Log
                        </button>
                        <span className="text-slate-300">|</span>
                        <button
                          onClick={() => deleteUser(a)}
                          className="text-rose-600 hover:underline"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!items.length && (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-slate-400">
                    No FTP accounts found. Click "Add FTP" to create one.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom Batch Actions & Pagination */}
        <div className="bg-slate-50 border-t border-slate-200 px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <select
              value={batchAction}
              onChange={(e) => setBatchAction(e.target.value)}
              className="bg-white border border-slate-300 rounded px-2.5 py-1 text-slate-700 text-xs"
            >
              <option value="">Please choose</option>
              <option value="delete">Delete</option>
            </select>
            <button
              onClick={executeBatch}
              disabled={!selectedIds.length || !batchAction}
              className="bg-white hover:bg-slate-100 disabled:opacity-50 border border-slate-300 text-slate-700 font-medium px-3 py-1 rounded"
            >
              Execute
            </button>
            <span className="text-slate-400">{selectedIds.length} selected</span>
          </div>

          <div className="flex items-center gap-3 text-slate-600">
            <div className="flex items-center gap-1">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-2 py-0.5 rounded border border-slate-200 disabled:opacity-40">&lt;</button>
              <span className="px-2 py-0.5 rounded bg-emerald-600 text-white font-medium">{page}</span>
              <button disabled={page * limit >= overview.total} onClick={() => setPage(page + 1)} className="px-2 py-0.5 rounded border border-slate-200 disabled:opacity-40">&gt;</button>
            </div>
            <select
              value={limit}
              onChange={(e) => { setLimit(Number(e.target.value)); setPage(1); }}
              className="bg-white border border-slate-300 rounded px-1.5 py-0.5 text-xs"
            >
              {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n} / page</option>)}
            </select>
            <span className="font-medium">Total {overview.total}</span>
          </div>
        </div>
      </div>

      {/* 1. Add FTP User Modal (with auto-fill path & note like aaPanel) */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form onSubmit={handleCreate} className="bg-white rounded-lg shadow-xl w-full max-w-lg overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold text-slate-800">Add FTP User</h3>
              <button type="button" onClick={() => setShowAdd(false)} className="text-slate-400 hover:text-slate-600"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3.5">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Username <span className="text-rose-500">*</span></label>
                <input
                  required
                  value={addForm.username}
                  onChange={(e) => {
                    const u = e.target.value;
                    setAddForm({
                      ...addForm,
                      username: u,
                      note: u,
                      document_root: u ? `/www/wwwroot/${u}` : '/www/wwwroot',
                    });
                  }}
                  placeholder="Letters, numbers, and underscores (>= 3 chars)"
                  className="input-field font-mono"
                />
              </div>
              <div>
                <label className="block text-slate-700 font-medium mb-1">Password <span className="text-rose-500">*</span></label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      required
                      type={showAddPass ? 'text' : 'password'}
                      value={addForm.password}
                      onChange={(e) => setAddForm({ ...addForm, password: e.target.value })}
                      className="input-field font-mono pr-8"
                    />
                    <button type="button" onClick={() => setShowAddPass(!showAddPass)} className="absolute right-2.5 top-2 text-slate-400">
                      {showAddPass ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                  <button type="button" onClick={() => setAddForm({ ...addForm, password: generatePassword(14) })} className="btn-secondary whitespace-nowrap">
                    Random
                  </button>
                </div>
              </div>
              <div>
                <label className="block text-slate-700 font-medium mb-1">Document Root</label>
                <input
                  required
                  value={addForm.document_root}
                  onChange={(e) => setAddForm({ ...addForm, document_root: e.target.value })}
                  className="input-field font-mono"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Quota (MB, 0=Unlimited)</label>
                  <input
                    type="number"
                    min={0}
                    value={addForm.quota_mb}
                    onChange={(e) => setAddForm({ ...addForm, quota_mb: Number(e.target.value) })}
                    className="input-field"
                  />
                </div>
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Note</label>
                  <input
                    value={addForm.note}
                    onChange={(e) => setAddForm({ ...addForm, note: e.target.value })}
                    placeholder="Edit notes"
                    className="input-field"
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Confirm</button>
            </div>
          </form>
        </div>
      )}

      {/* 2. Change FTP Port Modal */}
      {showPort && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form onSubmit={savePort} className="bg-white rounded-lg shadow-xl w-full max-w-sm overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">Change FTP Port</h3>
              <button type="button" onClick={() => setShowPort(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Default port</label>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  required
                  value={portInput}
                  onChange={(e) => setPortInput(Number(e.target.value))}
                  className="input-field font-mono"
                />
              </div>
              <p className="text-[11px] text-slate-500">
                Updating the port also automatically adds an inbound allow rule in Security Firewall. Ensure passive range ({overview.passive_range}) stays open in your cloud firewall.
              </p>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setShowPort(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        </div>
      )}

      {/* 3. Set Path (Change FTP user home + Migrate) Modal */}
      {homeModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form onSubmit={saveHome} className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold flex items-center gap-1.5"><FolderInput size={15} className="text-emerald-600" /> Change ftp user home</h3>
              <button type="button" onClick={() => setHomeModal({ open: false, row: null, path: '', migrate: false })} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Username</label>
                <input disabled value={homeModal.row?.username || ''} className="input-field bg-slate-50 font-mono text-slate-500" />
              </div>
              <div>
                <label className="block text-slate-700 font-medium mb-1">Home</label>
                <input required value={homeModal.path} onChange={(e) => setHomeModal({ ...homeModal, path: e.target.value })} className="input-field font-mono" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer pt-1">
                <input type="checkbox" checked={homeModal.migrate} onChange={(e) => setHomeModal({ ...homeModal, migrate: e.target.checked })} className="rounded text-emerald-600" />
                <span className="font-medium text-slate-700">Migrate existing directory files</span>
              </label>
              <ul className="bg-amber-50 border border-amber-200 rounded p-2.5 text-[11px] text-amber-800 list-disc pl-6 space-y-0.5">
                <li>Migrating data is by copying</li>
                <li>If the amount of data is large, manual migration is recommended</li>
                <li>Need to manually clean up old data after migration is complete</li>
              </ul>
            </div>
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setHomeModal({ open: false, row: null, path: '', migrate: false })} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        </div>
      )}

      {/* 4. Change Password Modal */}
      {passModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form onSubmit={savePassword} className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold flex items-center gap-1.5"><KeyRound size={15} className="text-emerald-600" /> Change FTP User Password</h3>
              <button type="button" onClick={() => setPassModal({ open: false, row: null, password: '' })} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Username</label>
                <input disabled value={passModal.row?.username || ''} className="input-field bg-slate-50 font-mono text-slate-500" />
              </div>
              <div>
                <label className="block text-slate-700 font-medium mb-1">New Password</label>
                <div className="flex gap-2">
                  <input required minLength={6} value={passModal.password} onChange={(e) => setPassModal({ ...passModal, password: e.target.value })} className="input-field font-mono flex-1" />
                  <button type="button" onClick={() => setPassModal({ ...passModal, password: generatePassword(14) })} className="btn-secondary">Random</button>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setPassModal({ open: false, row: null, password: '' })} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        </div>
      )}

      {/* 5. Quota Modal */}
      {quotaModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <form onSubmit={saveQuota} className="bg-white rounded-lg shadow-xl w-full max-w-sm overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">Set Quota — {quotaModal.row?.username}</h3>
              <button type="button" onClick={() => setQuotaModal({ open: false, row: null, quota_mb: 0 })} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <label className="block text-slate-700 font-medium">Capacity Quota (MB, 0 = Unlimited)</label>
              <input type="number" min={0} value={quotaModal.quota_mb} onChange={(e) => setQuotaModal({ ...quotaModal, quota_mb: Number(e.target.value) })} className="input-field font-mono" />
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setQuotaModal({ open: false, row: null, quota_mb: 0 })} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        </div>
      )}

      {/* 6. Security Config Modal (sw_ftp_login, sw_ftp_root, sw_ftp_pass) */}
      {showSecurity && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold flex items-center gap-1.5"><Shield size={15} className="text-emerald-600" /> FTP Security Hardening (Pure-FTPd)</h3>
              <button onClick={() => setShowSecurity(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between p-3 rounded border border-slate-200">
                <div>
                  <div className="font-semibold text-slate-800">Disable Anonymous FTP Login</div>
                  <div className="text-[11px] text-slate-500">Enforces <code className="bg-slate-100 px-1 rounded">NoAnonymous yes</code> in pure-ftpd.conf</div>
                </div>
                <input
                  type="checkbox"
                  checked={overview.security?.no_anonymous ?? true}
                  onChange={(e) => toggleSecuritySetting('no_anonymous', e.target.checked)}
                  className="w-4 h-4 accent-emerald-600 cursor-pointer"
                />
              </div>
              <div className="flex items-center justify-between p-3 rounded border border-slate-200">
                <div>
                  <div className="font-semibold text-slate-800">Forbid Root User Login</div>
                  <div className="text-[11px] text-slate-500">Enforces <code className="bg-slate-100 px-1 rounded">MinUID 100</code> to block root FTP sessions</div>
                </div>
                <input
                  type="checkbox"
                  checked={overview.security?.forbid_root ?? true}
                  onChange={(e) => toggleSecuritySetting('forbid_root', e.target.checked)}
                  className="w-4 h-4 accent-emerald-600 cursor-pointer"
                />
              </div>
              <div className="p-3 rounded border border-slate-200">
                <div className="font-semibold text-slate-800 mb-1">Weak Password Audit</div>
                {overview.security?.weak_password_accounts?.length ? (
                  <p className="text-rose-600 text-[11px]">Weak passwords detected on: {overview.security.weak_password_accounts.join(', ')}</p>
                ) : (
                  <p className="text-emerald-600 text-[11px]">Risk-free: all FTP accounts meet password complexity baseline.</p>
                )}
              </div>
            </div>
            <div className="flex justify-end px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button onClick={() => setShowSecurity(false)} className="btn-secondary">Close</button>
            </div>
          </div>
        </div>
      )}

      {/* 7. Per-User View FTP Log Modal (Login Log + Action Log tabs) */}
      {logsModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-3xl overflow-hidden border border-slate-200 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">View FTP log — [{logsModal.row?.username}]</h3>
              <button onClick={() => setLogsModal({ open: false, row: null, tab: 'login' })} className="text-slate-400"><X size={16} /></button>
            </div>

            <div className="flex border-b border-slate-200 px-5 gap-4 bg-white">
              {(['login', 'action'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setLogsModal({ ...logsModal, tab: t });
                    fetchUserLogs(logsModal.row.id, t, logSearch, actionTypeFilter);
                  }}
                  className={`py-2.5 text-xs font-medium border-b-2 transition-colors ${logsModal.tab === t ? 'border-emerald-600 text-emerald-600' : 'border-transparent text-slate-600'}`}
                >
                  {t === 'login' ? 'Login Log' : 'Action Log'}
                </button>
              ))}
            </div>

            <div className="p-4 space-y-3 overflow-y-auto flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  onClick={() => fetchUserLogs(logsModal.row.id, logsModal.tab, logSearch, actionTypeFilter)}
                  className="btn-secondary flex items-center gap-1.5"
                >
                  <RefreshCw size={12} /> Refresh log
                </button>
                <div className="flex items-center gap-2">
                  {logsModal.tab === 'action' && (
                    <select
                      value={actionTypeFilter}
                      onChange={(e) => {
                        setActionTypeFilter(e.target.value);
                        fetchUserLogs(logsModal.row.id, 'action', logSearch, e.target.value);
                      }}
                      className="input-field w-32"
                    >
                      <option value="all">All</option>
                      <option value="upload">Upload</option>
                      <option value="download">Download</option>
                      <option value="delete">Delete</option>
                      <option value="rename">Rename</option>
                    </select>
                  )}
                  <input
                    value={logSearch}
                    onChange={(e) => setLogSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') fetchUserLogs(logsModal.row.id, logsModal.tab, logSearch, actionTypeFilter); }}
                    placeholder="Operate IP / Status / time"
                    className="input-field w-56"
                  />
                </div>
              </div>

              {logsModal.tab === 'login' ? (
                <table className="data-table">
                  <thead>
                    <tr><th>Username</th><th>Login IP</th><th>State</th><th>Login time</th><th>Logout time</th></tr>
                  </thead>
                  <tbody>
                    {loginLogs.map((l) => (
                      <tr key={l.id}>
                        <td className="font-mono">{l.user}</td>
                        <td className="font-mono">{l.ip}</td>
                        <td className={l.status.toLowerCase().includes('fail') ? 'text-rose-600 font-medium' : 'text-emerald-600 font-medium'}>{l.status}</td>
                        <td className="text-slate-500">{l.in_time}</td>
                        <td className="text-slate-500">{l.out_time}</td>
                      </tr>
                    ))}
                    {!loginLogs.length && <tr><td colSpan={5} className="text-center text-slate-400 py-6">No login records found.</td></tr>}
                  </tbody>
                </table>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>Username</th><th>Operating IP</th><th>Document</th><th>Operation Type</th><th>Operation time</th></tr>
                  </thead>
                  <tbody>
                    {actionLogs.map((l) => (
                      <tr key={l.id}>
                        <td className="font-mono">{l.name}</td>
                        <td className="font-mono">{l.ip}</td>
                        <td className="font-mono text-[11px]">{l.file}</td>
                        <td className="uppercase text-[11px] font-semibold">{l.type}</td>
                        <td className="text-slate-500">{l.time}</td>
                      </tr>
                    ))}
                    {!actionLogs.length && <tr><td colSpan={5} className="text-center text-slate-400 py-6">No file action records found.</td></tr>}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 8. FTP Log Scanning Tool Modal */}
      {analysisOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-3xl overflow-hidden border border-slate-200 flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">FTP log scanning tool</h3>
              <button onClick={() => setAnalysisOpen(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-6 space-y-5 overflow-y-auto">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-base font-bold text-slate-800">
                    {scanned
                      ? scanRisks.length
                        ? `The scan is completed, ${scanRisks.length} risk records are scanned`
                        : 'The scan is completed, No risk records were scanned'
                      : 'Quickly scan the security details of the current FTP'}
                  </div>
                  <div className="text-slate-500 mt-0.5">It is recommended to enable automatic scanning & IP whitelist rules</div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={openWhitelist} className="btn-secondary">Whitelist</button>
                  <button onClick={() => setConditionsOpen(true)} className="btn-primary">
                    {scanned ? 'Rescan' : 'Scan now'}
                  </button>
                </div>
              </div>

              {!scanned ? (
                <div className="border border-slate-200 rounded-md p-4 bg-slate-50/70 space-y-3">
                  <div className="font-semibold text-slate-700">The following log risk scans are supported:</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-slate-600">
                    {['Multiple login failures', 'Abnormal login area', 'Upload script file', 'Anonymous user login', 'Abnormal login time'].map((label) => (
                      <div key={label} className="flex items-center gap-2 bg-white border border-slate-200 rounded px-3 py-2">
                        <ShieldAlert size={14} className="text-amber-500 shrink-0" />
                        <span>{label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>Type</th><th>Username</th><th>IP</th><th>Operation time</th><th className="text-right">Operate</th></tr>
                  </thead>
                  <tbody>
                    {scanRisks.map((r, idx) => (
                      <tr key={idx}>
                        <td className="text-rose-600 font-medium">{r.type}</td>
                        <td className="font-mono">{r.user}</td>
                        <td className="font-mono">{r.ip}</td>
                        <td className="text-slate-500">{r.exec_time}</td>
                        <td className="text-right space-x-2">
                          <button onClick={() => ignoreRiskIp(r.ip)} className="text-emerald-600 hover:underline">Ignore</button>
                          {r.id > 0 && (
                            <button
                              onClick={async () => {
                                await apiFetch(`/ftp/${r.id}`, { method: 'PUT', body: JSON.stringify({ status: 'disabled' }) });
                                flash(`Disabled ${r.user}`);
                                await load();
                              }}
                              className="text-amber-600 hover:underline"
                            >
                              Disable
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {!scanRisks.length && <tr><td colSpan={5} className="text-center py-6 text-emerald-600 font-medium">No security risks detected in scanned FTP logs.</td></tr>}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 9. Scan Conditions Modal */}
      {conditionsOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[55] p-4">
          <form onSubmit={runLogScan} className="bg-white rounded-lg shadow-2xl w-full max-w-2xl overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">FTP log analysis conditions</h3>
              <button type="button" onClick={() => setConditionsOpen(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Security risk items</span>
                  <button type="button" onClick={() => setThresholdsOpen(true)} className="text-emerald-600 hover:underline font-medium">
                    [Set Scan Conditions]
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2.5 bg-slate-50 p-3 rounded border border-slate-200">
                  {[
                    { k: 'login_error', label: `Multiple login failures (> ${scanConfig.login_error}x in 5m)` },
                    { k: 'area', label: `Abnormal login area (Allowed: ${(scanConfig.area?.country || []).join(', ')})` },
                    { k: 'upload_shell', label: `Upload script file (${(scanConfig.upload_shell || []).join(', ')})` },
                    { k: 'time', label: `Abnormal login time (${scanConfig.time?.start_time ?? 0}:00 - ${scanConfig.time?.end_time ?? 23}:00)` },
                    { k: 'anonymous', label: 'Anonymous user login' },
                  ].map((opt) => (
                    <label key={opt.k} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={scanParams.types.includes(opt.k)}
                        onChange={(e) => {
                          setScanParams({
                            ...scanParams,
                            types: e.target.checked ? [...scanParams.types, opt.k] : scanParams.types.filter((x) => x !== opt.k),
                          });
                        }}
                      />
                      <span>{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Log Days</label>
                  <div className="flex items-center gap-3">
                    {[7, 30].map((d) => (
                      <label key={d} className="flex items-center gap-1">
                        <input type="radio" checked={scanParams.day === d} onChange={() => setScanParams({ ...scanParams, day: d })} />
                        <span>{d} Day</span>
                      </label>
                    ))}
                    <label className="flex items-center gap-1">
                      <input type="radio" checked={scanParams.day === 0} onChange={() => setScanParams({ ...scanParams, day: 0 })} />
                      <span>Customize</span>
                    </label>
                  </div>
                  {scanParams.day === 0 && (
                    <input type="number" min={1} value={scanParams.customDay} onChange={(e) => setScanParams({ ...scanParams, customDay: Number(e.target.value) })} className="input-field mt-2 w-28" />
                  )}
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1">FTP User</label>
                  <select value={scanParams.userMode} onChange={(e) => setScanParams({ ...scanParams, userMode: e.target.value })} className="input-field">
                    <option value="all">All Users</option>
                    <option value="custom">Selected Users</option>
                  </select>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setConditionsOpen(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Confirm Scan</button>
            </div>
          </form>
        </div>
      )}

      {/* 10. Threshold Conditions Sub-Modal */}
      {thresholdsOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
          <form onSubmit={saveScanThresholds} className="bg-white rounded-lg shadow-2xl w-full max-w-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">Scan for touch conditions</h3>
              <button type="button" onClick={() => setThresholdsOpen(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="block font-medium mb-1">Login failed threshold (times in 5 min)</label>
                <input type="number" min={1} value={scanConfig.login_error} onChange={(e) => setScanConfig({ ...scanConfig, login_error: Number(e.target.value) })} className="input-field" />
              </div>
              <div>
                <label className="block font-medium mb-1">Allowed Countries (comma-separated)</label>
                <input
                  value={(scanConfig.area?.country || []).join(', ')}
                  onChange={(e) => setScanConfig({ ...scanConfig, area: { country: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) } })}
                  className="input-field"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block font-medium mb-1">Start Hour (0-23)</label>
                  <input type="number" min={0} max={23} value={scanConfig.time?.start_time ?? 6} onChange={(e) => setScanConfig({ ...scanConfig, time: { ...scanConfig.time, start_time: Number(e.target.value) } })} className="input-field" />
                </div>
                <div>
                  <label className="block font-medium mb-1">End Hour (0-23)</label>
                  <input type="number" min={0} max={23} value={scanConfig.time?.end_time ?? 23} onChange={(e) => setScanConfig({ ...scanConfig, time: { ...scanConfig.time, end_time: Number(e.target.value) } })} className="input-field" />
                </div>
              </div>
              <div>
                <label className="block font-medium mb-1">Flagged Script Extensions (comma-separated)</label>
                <input
                  value={(scanConfig.upload_shell || []).join(', ')}
                  onChange={(e) => setScanConfig({ ...scanConfig, upload_shell: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
                  className="input-field font-mono"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-slate-200 bg-slate-50">
              <button type="button" onClick={() => setThresholdsOpen(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Save</button>
            </div>
          </form>
        </div>
      )}

      {/* 11. Whitelist Modal */}
      {whitelistOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">FTP log whitelist</h3>
              <button onClick={() => setWhitelistOpen(false)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-4 space-y-3">
              <form onSubmit={addWhitelistIp} className="flex gap-2">
                <input required value={newWhitelistIp} onChange={(e) => setNewWhitelistIp(e.target.value)} placeholder="Please enter an IP address" className="input-field flex-1 font-mono" />
                <button type="submit" className="btn-primary whitespace-nowrap">Add whitelist</button>
              </form>
              <table className="data-table">
                <thead><tr><th>IP</th><th className="text-right">Operate</th></tr></thead>
                <tbody>
                  {whitelistIps.map((ip) => (
                    <tr key={ip}>
                      <td className="font-mono">{ip}</td>
                      <td className="text-right"><button onClick={() => removeWhitelistIp(ip)} className="text-rose-600 hover:underline">Delete</button></td>
                    </tr>
                  ))}
                  {!whitelistIps.length && <tr><td colSpan={2} className="text-center text-slate-400 py-4">No whitelisted IPs.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 12. Batch Delete Result Summary Modal */}
      {batchResults && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50">
              <h3 className="text-sm font-bold">Batch Delete FTP Result</h3>
              <button onClick={() => setBatchResults(null)} className="text-slate-400"><X size={16} /></button>
            </div>
            <div className="p-4">
              <table className="data-table">
                <thead><tr><th>FTP</th><th className="text-right">Status</th></tr></thead>
                <tbody>
                  {batchResults.map((r, i) => (
                    <tr key={i}>
                      <td className="font-mono">{r.username}</td>
                      <td className={`text-right font-medium ${r.ok ? 'text-emerald-600' : 'text-rose-600'}`}>{r.msg}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex justify-end px-4 py-3 border-t border-slate-200 bg-slate-50">
              <button onClick={() => setBatchResults(null)} className="btn-primary">Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
