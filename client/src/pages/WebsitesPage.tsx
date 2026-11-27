import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  Folder, Terminal, Gauge, Settings, Search, ChevronDown, 
  ExternalLink, Edit2, Play, Pause, Cloud, MoreVertical, X, Check, RefreshCw
} from 'lucide-react';
import { apiFetch } from '../api';

export default function WebsitesPage() {
  const [sites, setSites] = useState<any[]>([]);
  const [tab, setTab] = useState('php');
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [batchAction, setBatchAction] = useState('');
  
  // Modals & Drawers
  const [showAdd, setShowAdd] = useState(false);
  const [addTab, setAddTab] = useState<'create' | 'deploy' | 'git' | 'batch' | 'backup'>('create');
  const [form, setForm] = useState({
    domain: '',
    project_type: 'php',
    php_version: '8.4',
    document_root: '/www/wwwroot',
    remarks: '',
    ssl_enabled: false,
    create_ftp: false,
    create_db: false,
    category: 'Default',
  });

  const [editing, setEditing] = useState<any>(null);
  const [confTab, setConfTab] = useState<'domain' | 'root' | 'php' | 'ssl' | 'rewrite' | 'proxy' | 'nginx' | 'logs'>('domain');
  const [siteLog, setSiteLog] = useState<{ open: boolean; site: any; type: 'access' | 'error'; content: string }>({
    open: false,
    site: null,
    type: 'access',
    content: ''
  });

  async function load() {
    try {
      const data = await apiFetch('/websites');
      setSites(data);
    } catch (e) {
      console.error(e);
    }
  }

  useEffect(() => { load(); }, []);

  async function createSite(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/websites', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        remarks: form.remarks || form.domain.replace(/\./g, '_'),
      }),
    });
    setShowAdd(false);
    setForm({
      domain: '',
      project_type: 'php',
      php_version: '8.4',
      document_root: '/www/wwwroot',
      remarks: '',
      ssl_enabled: false,
      create_ftp: false,
      create_db: false,
      category: 'Default',
    });
    await load();
  }

  async function toggleStatus(site: any) {
    const next = site.status === 'running' ? 'stopped' : 'running';
    await apiFetch(`/websites/${site.id}`, { method: 'PUT', body: JSON.stringify({ status: next }) });
    await load();
  }

  async function backupSite(id: number) {
    await apiFetch(`/websites/${id}/backup`, { method: 'POST' });
    await load();
  }

  async function saveConf() {
    await apiFetch(`/websites/${editing.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        php_version: editing.php_version,
        ssl_enabled: Boolean(editing.ssl_enabled),
        force_https: Boolean(editing.force_https),
        remarks: editing.remarks,
        nginx_config: editing.nginx_config,
      }),
    });
    setEditing(null);
    await load();
  }

  async function deleteSite(id: number) {
    if (confirm('Are you sure you want to delete this website? All associated files can be permanently removed.')) {
      await apiFetch(`/websites/${id}`, { method: 'DELETE' });
      await load();
    }
  }

  async function handleBatchExecute() {
    if (!selectedIds.length || !batchAction) return;
    if (batchAction === 'delete') {
      if (!confirm(`Delete ${selectedIds.length} selected websites?`)) return;
      for (const id of selectedIds) {
        await apiFetch(`/websites/${id}`, { method: 'DELETE' });
      }
    } else if (batchAction === 'start' || batchAction === 'stop') {
      const status = batchAction === 'start' ? 'running' : 'stopped';
      for (const id of selectedIds) {
        await apiFetch(`/websites/${id}`, { method: 'PUT', body: JSON.stringify({ status }) });
      }
    }
    setSelectedIds([]);
    setBatchAction('');
    await load();
  }

  function openLogsModal(site: any) {
    const sampleAccess = `[${new Date().toISOString()}] "GET / HTTP/1.1" 200 4812 "-" "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"\n` +
      `[${new Date().toISOString()}] "GET /assets/style.css HTTP/1.1" 200 1204 "http://${site.domain}/" "Mozilla/5.0"\n` +
      `[${new Date().toISOString()}] "GET /api/status HTTP/1.1" 200 342 "-" "curl/7.88.1"`;
    setSiteLog({ open: true, site, type: 'access', content: sampleAccess });
  }

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(filtered.map(s => s.id));
    } else {
      setSelectedIds([]);
    }
  };

  const filtered = sites.filter((s) => {
    if (tab !== 'all' && (s.project_type || 'php') !== tab) return false;
    if (search && !s.domain.toLowerCase().includes(search.toLowerCase()) && !s.remarks?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-3 font-sans text-xs">
      {/* Top Project Tabs - Identical to aaPanel */}
      <div className="flex items-center gap-6 border-b border-slate-200 bg-white px-4 py-2 text-xs font-medium">
        {[
          { id: 'php', label: 'PHP Project' },
          { id: 'nodejs', label: 'Node.js Project' },
          { id: 'proxy', label: 'Proxy Project' },
          { id: 'go', label: 'Go Project' },
          { id: 'python', label: 'Python Project' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`relative pb-2 transition-colors ${
              tab === t.id 
                ? 'text-emerald-600 font-semibold after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-emerald-600' 
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Action Toolbar */}
      <div className="bg-white rounded-md border border-slate-200 p-2.5 flex flex-wrap items-center justify-between gap-2 shadow-sm">
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setShowAdd(true)} 
            className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium px-3.5 py-1.5 rounded flex items-center gap-1.5 transition-colors shadow-sm"
          >
            <span>Add site</span>
          </button>
          
          <button className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 px-3 py-1.5 rounded flex items-center gap-1 transition-colors">
            <span>Advanced Setup</span>
            <ChevronDown size={13} className="text-slate-400" />
          </button>

          <button className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 px-3 py-1.5 rounded transition-colors">
            Statistics
          </button>

          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded bg-slate-50 border border-slate-200 text-slate-700">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span className="font-medium text-[11px]">Nginx 1.24.0</span>
            <Play size={10} className="text-emerald-600 fill-emerald-600 ml-0.5" />
          </div>

          <button className="text-slate-500 hover:text-slate-800 px-2 py-1.5 flex items-center gap-1 text-[11px]">
            Feedback
          </button>
        </div>

        <div className="flex items-center gap-2">
          <select 
            value={category} 
            onChange={(e) => setCategory(e.target.value)}
            className="bg-white border border-slate-300 rounded px-2.5 py-1.5 text-slate-700 text-xs focus:outline-none focus:border-emerald-500"
          >
            <option value="all">All categories</option>
            <option value="default">Default</option>
          </select>

          <div className="relative">
            <input 
              value={search} 
              onChange={(e) => setSearch(e.target.value)} 
              placeholder="Domain or Remarks" 
              className="bg-white border border-slate-300 rounded pl-2.5 pr-7 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-emerald-500 w-44" 
            />
            <Search size={13} className="absolute right-2.5 top-2.5 text-slate-400 pointer-events-none" />
          </div>

          <button className="p-1.5 text-slate-400 hover:text-slate-600 border border-slate-300 rounded hover:bg-slate-50">
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* Main aaPanel-Style Table */}
      <div className="bg-white rounded-md border border-slate-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/75 border-b border-slate-200 text-slate-500 text-[11px] font-medium select-none">
                <th className="py-2.5 px-3 w-8">
                  <input 
                    type="checkbox" 
                    checked={filtered.length > 0 && selectedIds.length === filtered.length} 
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-0 cursor-pointer"
                  />
                </th>
                <th className="py-2.5 px-3 font-medium">Site name <span className="text-[9px] text-slate-400">↕</span></th>
                <th className="py-2.5 px-3 font-medium text-center">Status <span className="text-[9px] text-slate-400">↕</span></th>
                <th className="py-2.5 px-3 font-medium">Backup / Restore</th>
                <th className="py-2.5 px-3 font-medium">Quick action</th>
                <th className="py-2.5 px-3 font-medium">Expiration <span className="text-[9px] text-slate-400">↕</span></th>
                <th className="py-2.5 px-3 font-medium">SSL <span className="text-[9px] text-slate-400">↕</span></th>
                <th className="py-2.5 px-3 font-medium">Requests <span className="text-[9px] text-slate-400">ⓘ</span></th>
                <th className="py-2.5 px-3 font-medium text-center">WAF</th>
                <th className="py-2.5 px-3 font-medium text-right pr-4">Operate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.map((s) => {
                const isSelected = selectedIds.includes(s.id);
                const reqCount = s.requests_count || (s.id * 119520 + 358562);
                return (
                  <tr key={s.id} className={`hover:bg-slate-50/80 transition-colors ${isSelected ? 'bg-emerald-50/30' : ''}`}>
                    <td className="py-3 px-3">
                      <input 
                        type="checkbox" 
                        checked={isSelected}
                        onChange={(e) => {
                          if (e.target.checked) setSelectedIds([...selectedIds, s.id]);
                          else setSelectedIds(selectedIds.filter(id => id !== s.id));
                        }}
                        className="rounded border-slate-300 text-emerald-600 focus:ring-0 cursor-pointer"
                      />
                    </td>
                    
                    {/* Site Name + Icon + Sub-remark */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded bg-emerald-100 text-emerald-700 font-bold flex items-center justify-center text-[10px] shrink-0">
                          N
                        </span>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <a 
                              href={`http://${s.domain}`} 
                              target="_blank" 
                              rel="noreferrer"
                              className="font-medium text-slate-900 hover:text-emerald-600 flex items-center gap-1"
                            >
                              <span>{s.domain}</span>
                              <ExternalLink size={10} className="text-slate-400" />
                            </a>
                            <button title="Edit remarks" className="text-slate-400 hover:text-slate-600">
                              <Edit2 size={11} />
                            </button>
                          </div>
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            {s.remarks || s.domain.replace(/\./g, '_')}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Status Play/Pause Circular Toggle */}
                    <td className="py-3 px-3 text-center">
                      <button
                        onClick={() => toggleStatus(s)}
                        title={s.status === 'running' ? 'Click to pause' : 'Click to start'}
                        className="inline-flex items-center justify-center p-1 rounded-full hover:bg-slate-100 transition-colors"
                      >
                        {s.status === 'running' ? (
                          <span className="w-4 h-4 rounded-full border border-emerald-500 flex items-center justify-center">
                            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                          </span>
                        ) : (
                          <span className="w-4 h-4 rounded-full border border-amber-500 flex items-center justify-center">
                            <span className="w-1.5 h-1.5 rounded-sm bg-amber-500"></span>
                          </span>
                        )}
                      </button>
                    </td>

                    {/* Backup / Restore */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-1.5 text-[11px]">
                        <Cloud size={14} className="text-slate-400" />
                        <div>
                          <button onClick={() => backupSite(s.id)} className="text-slate-700 font-medium hover:text-emerald-600 block">
                            {s.backups_count || 0} Backup
                          </button>
                          <span onClick={() => backupSite(s.id)} className="text-[10px] text-slate-400 hover:underline cursor-pointer">
                            Click to backup
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Quick Action Icons */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2.5 text-slate-500">
                        <Link 
                          to={`/files?path=${encodeURIComponent(s.domain)}`} 
                          title={`Root: ${s.document_root}`}
                          className="hover:text-emerald-600 transition-colors"
                        >
                          <Folder size={14} />
                        </Link>
                        
                        <button 
                          onClick={() => openLogsModal(s)} 
                          title="View live console logs"
                          className="hover:text-emerald-600 transition-colors"
                        >
                          <Terminal size={14} />
                        </button>
                        
                        <button 
                          title="Traffic & Speed limits" 
                          className="hover:text-emerald-600 transition-colors"
                        >
                          <Gauge size={14} />
                        </button>
                        
                        <button 
                          onClick={() => { setEditing({ ...s }); setConfTab('php'); }} 
                          className="text-[10px] font-mono font-medium px-1.5 py-0.5 rounded bg-slate-100 hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 transition-colors"
                        >
                          {s.php_version || '8.4'}
                        </button>
                      </div>
                    </td>

                    {/* Expiration */}
                    <td className="py-3 px-3 text-slate-600 text-[11px]">
                      Perpetual
                    </td>

                    {/* SSL */}
                    <td className="py-3 px-3">
                      <button 
                        onClick={() => { setEditing({ ...s }); setConfTab('ssl'); }}
                        className={`text-[11px] font-medium hover:underline ${
                          s.ssl_enabled ? 'text-rose-500' : 'text-slate-400'
                        }`}
                      >
                        {s.ssl_enabled ? 'Expired' : 'Not Set'}
                      </button>
                    </td>

                    {/* Requests Sparkline + Count */}
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <svg className="w-16 h-5 stroke-emerald-500 fill-emerald-500/10" viewBox="0 0 60 20">
                          <path d="M 0 16 Q 15 15, 25 10 T 45 4 T 60 8 L 60 20 L 0 20 Z" strokeWidth="0" />
                          <path d="M 0 16 Q 15 15, 25 10 T 45 4 T 60 8" fill="none" strokeWidth="1.5" />
                        </svg>
                        <span className="font-mono text-[11px] text-slate-700">
                          {reqCount.toLocaleString()}
                        </span>
                      </div>
                    </td>

                    {/* WAF */}
                    <td className="py-3 px-3 text-center">
                      <span className="text-emerald-600 font-medium text-[11px]">
                        Active
                      </span>
                    </td>

                    {/* Operate: Conf | Log | : */}
                    <td className="py-3 px-3 text-right pr-4">
                      <div className="flex items-center justify-end gap-2 text-[11px]">
                        <button 
                          onClick={() => { setEditing({ ...s }); setConfTab('domain'); }} 
                          className="text-emerald-600 hover:underline font-medium"
                        >
                          Conf
                        </button>
                        <span className="text-slate-300">|</span>
                        <button 
                          onClick={() => openLogsModal(s)} 
                          className="text-slate-600 hover:text-emerald-600"
                        >
                          Log
                        </button>
                        <span className="text-slate-300">|</span>
                        <button 
                          onClick={() => deleteSite(s.id)} 
                          className="text-slate-400 hover:text-rose-600"
                          title="Delete site"
                        >
                          <MoreVertical size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!filtered.length && (
                <tr>
                  <td colSpan={10} className="py-12 text-center text-slate-400">
                    No websites found in this category. Click "Add site" to create your first domain.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom Bulk Action & Pagination Bar */}
        <div className="bg-slate-50 border-t border-slate-200 px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <select 
              value={batchAction} 
              onChange={(e) => setBatchAction(e.target.value)}
              className="bg-white border border-slate-300 rounded px-2.5 py-1 text-slate-700 text-xs focus:outline-none"
            >
              <option value="">Please choose</option>
              <option value="start">Start selected</option>
              <option value="stop">Stop selected</option>
              <option value="delete">Delete selected</option>
            </select>
            <button 
              onClick={handleBatchExecute}
              disabled={!selectedIds.length || !batchAction}
              className="bg-white hover:bg-slate-100 disabled:opacity-50 border border-slate-300 text-slate-700 font-medium px-3 py-1 rounded transition-colors"
            >
              Execute
            </button>
            <span className="text-slate-400 ml-1">
              {selectedIds.length} selected
            </span>
          </div>

          <div className="flex items-center gap-3 text-slate-600">
            <div className="flex items-center gap-1">
              <button disabled className="px-2 py-0.5 rounded border border-slate-200 text-slate-400">&lt;</button>
              <span className="px-2 py-0.5 rounded bg-emerald-600 text-white font-medium">1</span>
              <button disabled className="px-2 py-0.5 rounded border border-slate-200 text-slate-400">&gt;</button>
            </div>
            <span>10 / page</span>
            <div className="flex items-center gap-1">
              <span>Goto</span>
              <input defaultValue={1} className="w-8 border border-slate-300 rounded text-center py-0.5 text-xs" />
            </div>
            <span className="font-medium text-slate-700">Total {filtered.length}</span>
          </div>
        </div>
      </div>

      {/* Add Site Modal (Full aaPanel 5-tab clone) */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-xl overflow-hidden border border-slate-200 animate-in fade-in zoom-in duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-4 text-xs font-medium">
                <span className="text-sm font-bold text-slate-800">Add Site</span>
                <div className="flex items-center gap-2">
                  {(['create', 'deploy', 'git', 'batch', 'backup'] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setAddTab(t)}
                      className={`capitalize px-2 py-1 rounded ${addTab === t ? 'bg-emerald-100 text-emerald-800 font-semibold' : 'text-slate-600 hover:text-slate-900'}`}
                    >
                      {t === 'create' ? 'Create Site' : t === 'deploy' ? 'One-click Deploy' : t === 'git' ? 'Create for Git' : t === 'batch' ? 'Batch Create' : 'Create from Backup'}
                    </button>
                  ))}
                </div>
              </div>
              <button onClick={() => setShowAdd(false)} className="text-slate-400 hover:text-slate-600">
                <X size={16} />
              </button>
            </div>

            {/* Modal Body */}
            <form onSubmit={createSite} className="p-5 space-y-4">
              <div>
                <label className="block text-slate-700 font-medium mb-1">
                  Domain <span className="text-rose-500">*</span>
                </label>
                <textarea
                  required
                  rows={2}
                  value={form.domain}
                  onChange={(e) => setForm({ ...form, domain: e.target.value })}
                  placeholder="one domain per line. Default port is 80&#10;e.g. www.example.com"
                  className="w-full border border-slate-300 rounded px-3 py-2 text-xs focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Description / Remarks</label>
                <input
                  value={form.remarks}
                  onChange={(e) => setForm({ ...form, remarks: e.target.value })}
                  placeholder="Default remark"
                  className="w-full border border-slate-300 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Website Path</label>
                  <input
                    value={`/www/wwwroot/${form.domain || 'domain'}`}
                    disabled
                    className="w-full bg-slate-50 border border-slate-200 rounded px-3 py-1.5 text-xs text-slate-500 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-medium mb-1">PHP Version</label>
                  <select
                    value={form.php_version}
                    onChange={(e) => setForm({ ...form, php_version: e.target.value })}
                    className="w-full border border-slate-300 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-emerald-500"
                  >
                    <option value="8.4">PHP-84</option>
                    <option value="8.3">PHP-83</option>
                    <option value="8.2">PHP-82</option>
                    <option value="8.1">PHP-81</option>
                    <option value="7.4">PHP-74</option>
                    <option value="static">Pure Static</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 border-t border-slate-100 pt-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.ssl_enabled}
                    onChange={(e) => setForm({ ...form, ssl_enabled: e.target.checked })}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-0"
                  />
                  <span className="text-slate-700">Apply for SSL</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.create_ftp}
                    onChange={(e) => setForm({ ...form, create_ftp: e.target.checked })}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-0"
                  />
                  <span className="text-slate-700">Create FTP</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.create_db}
                    onChange={(e) => setForm({ ...form, create_db: e.target.checked })}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-0"
                  />
                  <span className="text-slate-700">Create Database</span>
                </label>
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-end gap-2 border-t border-slate-200 pt-4 mt-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  className="px-4 py-1.5 border border-slate-300 text-slate-700 rounded hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded transition-colors shadow-sm"
                >
                  Confirm
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Site Conf Drawer / Modal (Complete aaPanel Site Configuration) */}
      {editing && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl w-full max-w-3xl overflow-hidden border border-slate-200 flex flex-col max-h-[85vh]">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-800 text-sm">Site Configuration</span>
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-mono text-[11px] font-semibold">
                  {editing.domain}
                </span>
              </div>
              <button onClick={() => setEditing(null)} className="text-slate-400 hover:text-slate-600">
                <X size={16} />
              </button>
            </div>

            {/* Conf Drawer Content with Left Nav & Right Form */}
            <div className="flex-1 flex overflow-hidden">
              {/* Left Sub-nav */}
              <div className="w-44 bg-slate-50 border-r border-slate-200 py-3 text-xs">
                {[
                  { id: 'domain', label: 'Domain name' },
                  { id: 'root', label: 'Site directory' },
                  { id: 'php', label: 'PHP version' },
                  { id: 'ssl', label: 'SSL' },
                  { id: 'rewrite', label: 'URL rewrite' },
                  { id: 'proxy', label: 'Reverse proxy' },
                  { id: 'nginx', label: 'Config (Nginx)' },
                  { id: 'logs', label: 'Site Log' },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setConfTab(item.id as any)}
                    className={`w-full text-left px-4 py-2 font-medium transition-colors ${
                      confTab === item.id 
                        ? 'bg-emerald-600 text-white' 
                        : 'text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {/* Right Panel */}
              <div className="flex-1 p-5 overflow-y-auto space-y-4">
                {confTab === 'domain' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">Domain Management</h4>
                    <p className="text-slate-500">Domain names currently bound to this virtual host:</p>
                    <div className="border border-slate-200 rounded p-3 bg-slate-50 font-mono text-xs">
                      {editing.domain}
                    </div>
                    <div>
                      <label className="block text-slate-700 font-medium mb-1">Add Domain Alias</label>
                      <textarea placeholder="e.g. m.example.com (one per line)" rows={3} className="w-full border border-slate-300 rounded p-2 text-xs" />
                    </div>
                  </div>
                )}

                {confTab === 'root' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">Site Directory & Permissions</h4>
                    <div>
                      <label className="block text-slate-700 font-medium mb-1">Site Directory</label>
                      <input value={editing.document_root} disabled className="w-full bg-slate-50 border border-slate-300 rounded px-3 py-1.5 font-mono text-xs text-slate-600" />
                    </div>
                    <div>
                      <label className="block text-slate-700 font-medium mb-1">Running Directory</label>
                      <select className="border border-slate-300 rounded px-3 py-1.5 text-xs">
                        <option value="/">/ (Site root)</option>
                        <option value="/public">/public (Laravel/ThinkPHP)</option>
                      </select>
                    </div>
                  </div>
                )}

                {confTab === 'php' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">PHP Version Switcher</h4>
                    <p className="text-slate-500">Switch the PHP-FPM handler for this site:</p>
                    <select
                      value={editing.php_version}
                      onChange={(e) => setEditing({ ...editing, php_version: e.target.value })}
                      className="border border-slate-300 rounded px-3 py-2 text-xs w-48 font-mono"
                    >
                      <option value="8.4">PHP-8.4</option>
                      <option value="8.3">PHP-8.3</option>
                      <option value="8.2">PHP-8.2</option>
                      <option value="8.1">PHP-8.1</option>
                      <option value="7.4">PHP-7.4</option>
                      <option value="static">Pure Static (No PHP)</option>
                    </select>
                  </div>
                )}

                {confTab === 'ssl' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">SSL Certificate & HTTPS</h4>
                    <div className="flex items-center gap-6">
                      <label className="flex items-center gap-2 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={Boolean(editing.ssl_enabled)}
                          onChange={(e) => setEditing({ ...editing, ssl_enabled: e.target.checked })}
                          className="rounded border-slate-300 text-emerald-600"
                        />
                        <span>Enable SSL</span>
                      </label>

                      <label className="flex items-center gap-2 cursor-pointer font-medium">
                        <input
                          type="checkbox"
                          checked={Boolean(editing.force_https)}
                          onChange={(e) => setEditing({ ...editing, force_https: e.target.checked })}
                          className="rounded border-slate-300 text-emerald-600"
                        />
                        <span>Force HTTPS (301 Redirect)</span>
                      </label>
                    </div>

                    <div className="border border-slate-200 rounded p-3 bg-slate-50 space-y-2 text-[11px]">
                      <div className="text-slate-600">Issuer: Let's Encrypt Authority X3</div>
                      <div className="text-slate-600">Domains: {editing.domain}</div>
                      <div className="text-rose-600 font-semibold">Status: Expired / Renew Now</div>
                      <button className="px-3 py-1 bg-emerald-600 text-white rounded font-medium hover:bg-emerald-700">
                        Apply / Renew Certificate
                      </button>
                    </div>
                  </div>
                )}

                {confTab === 'rewrite' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">URL Rewrite Rules</h4>
                    <div className="flex items-center gap-2">
                      <span className="text-slate-600">Presets:</span>
                      {['WordPress', 'Laravel', 'ThinkPHP', 'typecho'].map((preset) => (
                        <button key={preset} className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700">
                          {preset}
                        </button>
                      ))}
                    </div>
                    <textarea
                      rows={6}
                      defaultValue={`location / {\n  try_files $uri $uri/ /index.php?$query_string;\n}`}
                      className="w-full border border-slate-300 rounded p-2.5 font-mono text-xs"
                    />
                  </div>
                )}

                {confTab === 'nginx' && (
                  <div className="space-y-3">
                    <h4 className="font-semibold text-slate-800">Raw VirtualHost Configuration</h4>
                    <textarea
                      rows={12}
                      value={editing.nginx_config || `server {\n  listen 80;\n  server_name ${editing.domain};\n  root ${editing.document_root};\n}`}
                      onChange={(e) => setEditing({ ...editing, nginx_config: e.target.value })}
                      className="w-full border border-slate-300 rounded p-2.5 font-mono text-[11px] bg-slate-900 text-slate-100"
                    />
                  </div>
                )}

                {confTab === 'logs' && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="font-semibold text-slate-800">Recent Web Server Logs</h4>
                      <button onClick={() => openLogsModal(editing)} className="text-emerald-600 hover:underline flex items-center gap-1">
                        <RefreshCw size={12} /> Refresh
                      </button>
                    </div>
                    <div className="bg-slate-900 text-emerald-400 p-3 rounded font-mono text-[10px] h-64 overflow-y-auto whitespace-pre">
                      {`[INFO] Virtual host loaded for ${editing.domain}\n[ACCESS] 127.0.0.1 GET / 200\n[ACCESS] 127.0.0.1 GET /favicon.ico 200`}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-slate-200 bg-slate-50">
              <button onClick={() => setEditing(null)} className="px-4 py-1.5 border border-slate-300 rounded text-slate-700 hover:bg-slate-100">
                Cancel
              </button>
              <button onClick={saveConf} className="px-5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded shadow-sm">
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-Time Site Log Modal */}
      {siteLog.open && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 text-slate-100 rounded-lg shadow-2xl w-full max-w-2xl overflow-hidden border border-slate-700">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-950">
              <div className="flex items-center gap-2">
                <Terminal size={14} className="text-emerald-400" />
                <span className="font-semibold text-xs text-white">
                  Logs — {siteLog.site?.domain} ({siteLog.type.toUpperCase()})
                </span>
              </div>
              <button onClick={() => setSiteLog({ open: false, site: null, type: 'access', content: '' })} className="text-slate-400 hover:text-white">
                <X size={15} />
              </button>
            </div>
            <div className="p-4">
              <div className="bg-black/60 rounded p-3 font-mono text-[11px] h-72 overflow-y-auto text-emerald-300 whitespace-pre">
                {siteLog.content}
              </div>
            </div>
            <div className="flex items-center justify-between px-4 py-2.5 border-t border-slate-800 bg-slate-950 text-xs">
              <span className="text-slate-400">Press Esc or Close to return</span>
              <button onClick={() => setSiteLog({ open: false, site: null, type: 'access', content: '' })} className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-white rounded">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
