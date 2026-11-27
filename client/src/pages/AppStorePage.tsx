import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function AppStorePage() {
  const [apps, setApps] = useState<any[]>([]);
  const [category, setCategory] = useState('ALL');
  const [search, setSearch] = useState('');

  async function load() {
    setApps(await apiFetch('/apps'));
  }
  useEffect(() => { load(); }, []);

  async function install(id: number) {
    await apiFetch(`/apps/${id}/install`, { method: 'POST' });
    await load();
  }

  async function uninstall(id: number) {
    await apiFetch(`/apps/${id}/uninstall`, { method: 'POST' });
    await load();
  }

  async function toggleHome(id: number) {
    await apiFetch(`/apps/${id}/home-toggle`, { method: 'POST' });
    await load();
  }

  const filtered = apps.filter((a) => {
    if (category === 'Installed' && a.status !== 'installed') return false;
    if (category !== 'ALL' && category !== 'Installed' && a.category !== category) return false;
    if (search && !a.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-3">
      <div className="card p-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1.5 text-xs">
          {['ALL', 'Installed', 'Deployment', 'Tools', 'Plug-ins'].map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-2.5 py-1 rounded ${category === cat ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700'}`}
            >
              {cat}
            </button>
          ))}
        </div>
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search App..." className="input-field w-48" />
      </div>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr><th>Software Name</th><th>Developer</th><th>Instructions</th><th>Status</th><th>Display on Home</th><th className="text-right">Operate</th></tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id}>
                <td className="font-semibold text-slate-900">{a.name} <span className="text-[10px] font-mono text-slate-400">v{a.version}</span></td>
                <td>{a.developer}</td>
                <td>{a.description}</td>
                <td>
                  <span className={`px-2 py-0.5 rounded text-[11px] ${a.status === 'installed' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {a.status === 'installed' ? 'Installed' : 'Not Installed'}
                  </span>
                </td>
                <td>
                  <input type="checkbox" checked={Boolean(a.display_on_home)} disabled={a.status !== 'installed'} onChange={() => toggleHome(a.id)} />
                </td>
                <td className="text-right">
                  {a.status === 'installed' ? (
                    <button onClick={() => uninstall(a.id)} className="text-rose-600 hover:underline">Uninstall</button>
                  ) : (
                    <button onClick={() => install(a.id)} className="text-emerald-600 hover:underline font-medium">Install</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
