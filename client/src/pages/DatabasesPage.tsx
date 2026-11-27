import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function DatabasesPage() {
  const [dbs, setDbs] = useState<any[]>([]);
  const [engine, setEngine] = useState('mysql');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ engine: 'mysql', db_name: '', username: '', password: '', location: 'localhost', note: '' });
  const [pwTarget, setPwTarget] = useState<any>(null);
  const [newPassword, setNewPassword] = useState('');

  async function load() {
    setDbs(await apiFetch('/databases'));
  }
  useEffect(() => { load(); }, []);

  async function createDb(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/databases', { method: 'POST', body: JSON.stringify({ ...form, engine }) });
    setShowAdd(false);
    setForm({ engine, db_name: '', username: '', password: '', location: 'localhost', note: '' });
    await load();
  }

  async function rotatePw(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch(`/databases/${pwTarget.id}/password`, { method: 'PUT', body: JSON.stringify({ password: newPassword }) });
    setPwTarget(null);
    setNewPassword('');
    await load();
  }

  async function backupDb(id: number) {
    await apiFetch(`/databases/${id}/backup`, { method: 'POST' });
    await load();
  }

  async function restoreDb(id: number) {
    await apiFetch(`/databases/${id}/restore`, { method: 'POST' });
    alert('Database restored from latest snapshot.');
  }

  async function deleteDb(id: number) {
    await apiFetch(`/databases/${id}`, { method: 'DELETE' });
    await load();
  }

  const filtered = dbs.filter((d) => d.engine === engine);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 border-b border-slate-200 text-xs font-medium">
        {['mysql', 'pgsql', 'mongodb', 'redis'].map((eng) => (
          <button
            key={eng}
            onClick={() => setEngine(eng)}
            className={`px-3 py-2 uppercase ${engine === eng ? 'border-b-2 border-emerald-600 text-emerald-700 font-semibold' : 'text-slate-600'}`}
          >
            {eng}
          </button>
        ))}
      </div>

      <div className="card p-3 flex items-center justify-between">
        <button onClick={() => setShowAdd(true)} className="btn-primary">+ Add DB</button>
        <span className="text-xs text-slate-500">Total ({engine.toUpperCase()}): {filtered.length}</span>
      </div>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr><th>Database Name</th><th>Username</th><th>Password</th><th>Backup</th><th>Location</th><th>Note</th><th className="text-right">Operate</th></tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr key={d.id}>
                <td className="font-mono font-semibold">{d.db_name}</td>
                <td className="font-mono">{d.username}</td>
                <td className="font-mono text-[11px]">••••••••</td>
                <td className="space-x-2">
                  <button onClick={() => backupDb(d.id)} className="text-emerald-600 hover:underline">Backup ({d.backup_count})</button>
                  <button onClick={() => restoreDb(d.id)} className="text-blue-600 hover:underline">Restore</button>
                </td>
                <td>{d.location}</td>
                <td>{d.note}</td>
                <td className="text-right space-x-2">
                  <button onClick={() => setPwTarget(d)} className="text-emerald-600 hover:underline">Password</button>
                  <button onClick={() => deleteDb(d.id)} className="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={createDb} className="bg-white rounded-lg p-5 w-full max-w-md space-y-3">
            <h3 className="text-sm font-bold">Add Database ({engine.toUpperCase()})</h3>
            <input value={form.db_name} onChange={(e) => setForm({ ...form, db_name: e.target.value })} placeholder="Database name" className="input-field" required />
            <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="Username" className="input-field" required />
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Password" className="input-field" required />
            <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Note" className="input-field" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Create</button>
            </div>
          </form>
        </div>
      )}

      {pwTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={rotatePw} className="bg-white rounded-lg p-5 w-full max-w-sm space-y-3">
            <h3 className="text-sm font-bold">Change Password — {pwTarget.db_name}</h3>
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="New password" className="input-field" required />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setPwTarget(null)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Update</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
