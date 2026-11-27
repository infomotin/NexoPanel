import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function AppStorePage() {
  const [catalog, setCatalog] = useState<any[]>([]);
  const [category, setCategory] = useState('ALL');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [logModal, setLogModal] = useState<string[] | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await apiFetch(`/system/packages/catalog?category=${encodeURIComponent(category)}&search=${encodeURIComponent(search)}`);
      if (Array.isArray(res) && res.length) {
        setCatalog(res);
      } else {
        const apps = await apiFetch('/apps');
        setCatalog(apps || []);
      }
    } catch {
      try {
        const apps = await apiFetch('/apps');
        setCatalog(apps || []);
      } catch {
        setCatalog([]);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [category]);

  async function install(item: any) {
    if (item.slug) {
      setLogModal([`Installing ${item.name}...`]);
      await apiFetch(`/system/packages/curated/${item.slug}/install`, { method: 'POST' });
      setLogModal((prev) => [...(prev || []), `✓ ${item.name} installed successfully and service activated.`]);
    } else {
      await apiFetch(`/apps/${item.id}/install`, { method: 'POST' });
    }
    await load();
  }

  async function uninstall(item: any) {
    if (item.slug) {
      setLogModal([`Removing ${item.name}...`]);
      await apiFetch(`/system/packages/curated/${item.slug}/uninstall`, { method: 'POST' });
      setLogModal((prev) => [...(prev || []), `✓ ${item.name} removed cleanly.`]);
    } else {
      await apiFetch(`/apps/${item.id}/uninstall`, { method: 'POST' });
    }
    await load();
  }

  async function controlService(slug: string, action: string) {
    try {
      await apiFetch(`/system/packages/curated/${slug}/control`, {
        method: 'POST',
        body: { service: slug, action },
      });
      await load();
    } catch (err: any) {
      alert(`Service action failed: ${err.message}`);
    }
  }

  const filtered = catalog.filter((a) => {
    const isInst = a.is_installed ?? (a.status === 'installed');
    if (category === 'Installed' && !isInst) return false;
    if (category !== 'ALL' && category !== 'Installed' && a.category?.toLowerCase() !== category.toLowerCase()) return false;
    if (search && !a.name.toLowerCase().includes(search.toLowerCase()) && !a.slug?.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-3 text-xs">
      <div className="card p-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {['ALL', 'Web Server', 'PHP', 'Database', 'FTP', 'Security', 'Tools', 'Installed'].map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-2.5 py-1 rounded font-medium transition-colors ${category === cat ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
            >
              {cat}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyUp={(e) => e.key === 'Enter' && load()}
            placeholder="Search software / package..."
            className="input-field w-56"
          />
          <button onClick={load} className="btn-secondary">Search</button>
        </div>
      </div>

      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading software catalog...</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th className="w-56">Software Name</th>
                <th className="w-24">Category</th>
                <th>Description</th>
                <th className="w-32 text-center">Service Status</th>
                <th className="w-36 text-center">Control</th>
                <th className="text-right w-28">Operate</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => {
                const isInst = a.is_installed ?? (a.status === 'installed');
                return (
                  <tr key={a.slug || a.id} className="hover:bg-slate-50">
                    <td className="font-semibold text-slate-900">
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded bg-slate-100 border border-slate-200 flex items-center justify-center font-bold text-[10px] text-slate-600">
                          {a.category?.[0] || 'S'}
                        </span>
                        <div>
                          <span>{a.name}</span>
                          {a.version && <span className="ml-1 text-[10px] font-mono text-slate-400">v{a.version.split('+')[0]}</span>}
                        </div>
                      </div>
                    </td>
                    <td><span className="px-1.5 py-0.5 rounded bg-slate-100 text-[10px] font-medium text-slate-600">{a.category}</span></td>
                    <td className="text-slate-600">{a.description}</td>
                    <td className="text-center">
                      {isInst ? (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${a.service_status === 'active' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-slate-100 text-slate-700'}`}>
                          ● {a.service_status === 'active' ? 'Running' : (a.service ? 'Stopped' : 'Installed')}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[10px]">Not Installed</span>
                      )}
                    </td>
                    <td className="text-center">
                      {isInst && a.service ? (
                        <div className="flex justify-center gap-1">
                          <button onClick={() => controlService(a.slug, 'restart')} className="px-1.5 py-0.5 border border-slate-200 rounded hover:bg-slate-50 text-[10px]">Restart</button>
                          <button onClick={() => controlService(a.slug, a.service_status === 'active' ? 'stop' : 'start')} className="px-1.5 py-0.5 border border-slate-200 rounded hover:bg-slate-50 text-[10px]">
                            {a.service_status === 'active' ? 'Stop' : 'Start'}
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="text-right">
                      {isInst ? (
                        <button onClick={() => uninstall(a)} className="text-rose-600 hover:underline">Uninstall</button>
                      ) : (
                        <button onClick={() => install(a)} className="text-emerald-600 hover:underline font-semibold">+ Install</button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="p-8 text-center text-slate-400">No software items found.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {logModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 text-emerald-400 rounded-lg p-4 w-full max-w-lg font-mono text-xs space-y-2">
            <div className="flex justify-between items-center text-slate-200 border-b border-slate-800 pb-2">
              <span className="font-bold">Transaction Output</span>
              <button onClick={() => setLogModal(null)} className="text-slate-400 hover:text-white">Close</button>
            </div>
            <div className="max-h-60 overflow-y-auto space-y-1">
              {logModal.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
