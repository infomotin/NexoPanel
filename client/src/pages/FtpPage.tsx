import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function FtpPage() {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', document_root: '/www/wwwroot', quota_mb: 0, note: '' });

  async function load() {
    setAccounts(await apiFetch('/ftp'));
  }
  useEffect(() => { load(); }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/ftp', { method: 'POST', body: JSON.stringify(form) });
    setShowAdd(false);
    await load();
  }

  async function toggle(a: any) {
    await apiFetch(`/ftp/${a.id}`, { method: 'PUT', body: JSON.stringify({ status: a.status === 'active' ? 'disabled' : 'active' }) });
    await load();
  }

  async function remove(id: number) {
    await apiFetch(`/ftp/${id}`, { method: 'DELETE' });
    await load();
  }

  return (
    <div className="space-y-3">
      <div className="card p-3 bg-emerald-50 border-emerald-200 text-xs text-emerald-800">
        FTP address: <strong className="font-mono">ftp://127.0.0.1:21</strong>
      </div>
      <div className="card p-3 flex justify-between items-center">
        <button onClick={() => setShowAdd(true)} className="btn-primary">+ Add FTP</button>
        <span className="text-xs text-slate-500">Total: {accounts.length}</span>
      </div>
      <div className="card overflow-hidden">
        <table className="data-table">
          <thead><tr><th>Username</th><th>Status</th><th>Document Root</th><th>Quota</th><th>Note</th><th className="text-right">Operate</th></tr></thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td className="font-mono font-semibold">{a.username}</td>
                <td><button onClick={() => toggle(a)} className="text-emerald-600 hover:underline">{a.status}</button></td>
                <td className="font-mono text-[11px]">{a.document_root}</td>
                <td>{a.quota_mb ? `${a.quota_mb} MB` : 'Unlimited'}</td>
                <td>{a.note}</td>
                <td className="text-right"><button onClick={() => remove(a.id)} className="text-rose-600 hover:underline">Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={create} className="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
            <h3 className="text-sm font-bold">Add FTP Account</h3>
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="Username" className="input-field" required />
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Password" className="input-field" required />
            <input value={form.document_root} onChange={(e) => setForm({ ...form, document_root: e.target.value })} placeholder="/www/wwwroot" className="input-field font-mono" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Create</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
