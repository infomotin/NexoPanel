import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function CronPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [form, setForm] = useState({ name: '', task_type: 'shell', schedule: '0 2 * * *', execute_user: 'root', script_content: '' });
  const [logView, setLogView] = useState<string | null>(null);

  async function load() {
    setJobs(await apiFetch('/cron'));
  }
  useEffect(() => { load(); }, []);

  async function addTask(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/cron', { method: 'POST', body: JSON.stringify(form) });
    setForm({ name: '', task_type: 'shell', schedule: '0 2 * * *', execute_user: 'root', script_content: '' });
    await load();
  }

  async function runNow(id: number) {
    const res = await apiFetch(`/cron/${id}/run`, { method: 'POST' });
    setLogView(res.last_output);
    await load();
  }

  async function toggle(id: number) {
    await apiFetch(`/cron/${id}/toggle`, { method: 'POST' });
    await load();
  }

  async function remove(id: number) {
    await apiFetch(`/cron/${id}`, { method: 'DELETE' });
    await load();
  }

  return (
    <div className="space-y-4">
      <form onSubmit={addTask} className="card p-4 space-y-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">Add Cron Task</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select value={form.task_type} onChange={(e) => setForm({ ...form, task_type: e.target.value })} className="input-field">
            <option value="shell">Shell Script</option>
            <option value="backup_site">Backup Site</option>
            <option value="backup_db">Backup Database</option>
            <option value="url">Access URL</option>
          </select>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Task name" className="input-field" required />
          <input value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} placeholder="0 2 * * *" className="input-field font-mono" required />
          <input value={form.execute_user} onChange={(e) => setForm({ ...form, execute_user: e.target.value })} placeholder="root" className="input-field" />
        </div>
        <textarea value={form.script_content} onChange={(e) => setForm({ ...form, script_content: e.target.value })} rows={2} placeholder="Script content or target..." className="input-field font-mono" required />
        <button type="submit" className="btn-primary">+ Add Task</button>
      </form>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Type</th><th>Execute Cycle</th><th>Status</th><th>Last Execute Time</th><th className="text-right">Operate</th></tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="font-semibold">{j.name}</td>
                <td className="uppercase text-[11px]">{j.task_type}</td>
                <td className="font-mono text-[11px]">{j.schedule}</td>
                <td>
                  <button onClick={() => toggle(j.id)} className={`px-2 py-0.5 rounded text-[11px] ${j.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {j.status}
                  </button>
                </td>
                <td className="text-[11px]">{j.last_run_at ? new Date(j.last_run_at).toLocaleString() : 'Never'}</td>
                <td className="text-right space-x-2">
                  <button onClick={() => runNow(j.id)} className="text-emerald-600 hover:underline">Run Now</button>
                  <button onClick={() => setLogView(j.last_output || 'No logs yet.')} className="text-blue-600 hover:underline">Log</button>
                  <button onClick={() => remove(j.id)} className="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {logView && (
        <div className="card p-3 bg-slate-900 text-emerald-400 font-mono text-xs flex justify-between items-center">
          <span>{logView}</span>
          <button onClick={() => setLogView(null)} className="text-slate-400 hover:text-white">Close</button>
        </div>
      )}
    </div>
  );
}
