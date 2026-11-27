import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../api';

export default function WebsitesPage() {
  const [sites, setSites] = useState<any[]>([]);
  const [tab, setTab] = useState('all');
  const [search, setSearch] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ domain: '', project_type: 'php', php_version: '8.2', remarks: '', ssl_enabled: false });
  const [editing, setEditing] = useState<any>(null);

  async function load() {
    setSites(await apiFetch('/websites'));
  }

  useEffect(() => { load(); }, []);

  async function createSite(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/websites', { method: 'POST', body: JSON.stringify(form) });
    setShowAdd(false);
    setForm({ domain: '', project_type: 'php', php_version: '8.2', remarks: '', ssl_enabled: false });
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
    await apiFetch(`/websites/${id}`, { method: 'DELETE' });
    await load();
  }

  const filtered = sites.filter((s) => {
    if (tab !== 'all' && s.project_type !== tab) return false;
    if (search && !s.domain.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 border-b border-slate-200 text-xs font-medium">
        {[
          { id: 'all', label: 'All Projects' },
          { id: 'php', label: 'PHP Project' },
          { id: 'nodejs', label: 'Node.js Project' },
          { id: 'proxy', label: 'Proxy Project' },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 ${tab === t.id ? 'border-b-2 border-emerald-600 text-emerald-700 font-semibold' : 'text-slate-600'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card p-3 flex items-center justify-between gap-2">
        <button onClick={() => setShowAdd(true)} className="btn-primary">+ Add Site</button>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Domain or Remarks..." className="input-field w-56" />
      </div>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>Site Name</th>
              <th>Status</th>
              <th>Backup</th>
              <th>Quick Action</th>
              <th>PHP</th>
              <th>SSL</th>
              <th className="text-right">Operate</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr key={s.id}>
                <td>
                  <div className="font-semibold text-slate-900">{s.domain}</div>
                  <div className="text-[10px] font-mono text-slate-400">{s.document_root}</div>
                </td>
                <td>
                  <button
                    onClick={() => toggleStatus(s)}
                    className={`px-2 py-0.5 rounded text-[11px] font-medium ${s.status === 'running' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}
                  >
                    {s.status === 'running' ? '▶ Running' : '⏸ Stopped'}
                  </button>
                </td>
                <td>
                  <button onClick={() => backupSite(s.id)} className="text-slate-600 hover:text-emerald-600 underline">
                    {s.backups_count} Backup
                  </button>
                </td>
                <td>
                  <Link to={`/files?path=${encodeURIComponent(s.domain)}`} className="text-emerald-600 hover:underline">📁 Root</Link>
                </td>
                <td className="font-mono">{s.php_version}</td>
                <td>
                  <span className={s.ssl_enabled ? 'text-emerald-600 font-medium' : 'text-slate-400'}>
                    {s.ssl_enabled ? 'SSL Active' : 'Not Set'}
                  </span>
                </td>
                <td className="text-right space-x-2">
                  <button onClick={() => setEditing({ ...s })} className="text-emerald-600 hover:underline font-medium">Conf</button>
                  <button onClick={() => deleteSite(s.id)} className="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={createSite} className="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
            <h3 className="text-sm font-bold">Add Site</h3>
            <input value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="example.com" className="input-field" required />
            <select value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })} className="input-field">
              <option value="php">PHP Project</option>
              <option value="nodejs">Node.js Project</option>
              <option value="proxy">Proxy Project</option>
            </select>
            <select value={form.php_version} onChange={(e) => setForm({ ...form, php_version: e.target.value })} className="input-field">
              <option value="8.3">PHP-83</option>
              <option value="8.2">PHP-82</option>
              <option value="8.1">PHP-81</option>
              <option value="static">Pure Static</option>
            </select>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={form.ssl_enabled} onChange={(e) => setForm({ ...form, ssl_enabled: e.target.checked })} />
              <span>Apply for SSL</span>
            </label>
            <input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} placeholder="Description / Remarks" className="input-field" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Confirm</button>
            </div>
          </form>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-5 w-full max-w-lg space-y-3">
            <h3 className="text-sm font-bold">Site Conf — {editing.domain}</h3>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] font-medium text-slate-600">PHP Version</label>
                <select value={editing.php_version} onChange={(e) => setEditing({ ...editing, php_version: e.target.value })} className="input-field">
                  <option value="8.3">PHP 8.3</option>
                  <option value="8.2">PHP 8.2</option>
                  <option value="8.1">PHP 8.1</option>
                  <option value="static">Static</option>
                </select>
              </div>
              <div className="flex items-end gap-3 pb-1">
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={Boolean(editing.ssl_enabled)} onChange={(e) => setEditing({ ...editing, ssl_enabled: e.target.checked })} />
                  <span>SSL Enabled</span>
                </label>
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={Boolean(editing.force_https)} onChange={(e) => setEditing({ ...editing, force_https: e.target.checked })} />
                  <span>Force HTTPS</span>
                </label>
              </div>
            </div>
            <div>
              <label className="text-[11px] font-medium text-slate-600">Nginx Configuration</label>
              <textarea rows={7} value={editing.nginx_config} onChange={(e) => setEditing({ ...editing, nginx_config: e.target.value })} className="input-field font-mono text-[11px]" />
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditing(null)} className="btn-secondary">Cancel</button>
              <button onClick={saveConf} className="btn-primary">Save Configuration</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
