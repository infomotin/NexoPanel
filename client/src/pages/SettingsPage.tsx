import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch('/settings').then(setSettings);
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSettings(await apiFetch('/settings', { method: 'PUT', body: JSON.stringify(settings) }));
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <form onSubmit={save} className="card p-5 max-w-2xl space-y-4 text-xs">
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <h2 className="text-sm font-bold text-slate-900">Global Panel Settings</h2>
        {saved && <span className="text-emerald-600 font-semibold">Saved!</span>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block font-medium text-slate-600 mb-1">Panel Port</label>
          <input value={settings.panel_port || ''} onChange={(e) => setSettings({ ...settings, panel_port: e.target.value })} className="input-field" />
        </div>
        <div>
          <label className="block font-medium text-slate-600 mb-1">Security Entrance</label>
          <input value={settings.security_entrance || ''} onChange={(e) => setSettings({ ...settings, security_entrance: e.target.value })} className="input-field" />
        </div>
        <div>
          <label className="block font-medium text-slate-600 mb-1">Panel Domain</label>
          <input value={settings.panel_domain || ''} onChange={(e) => setSettings({ ...settings, panel_domain: e.target.value })} className="input-field" />
        </div>
        <div>
          <label className="block font-medium text-slate-600 mb-1">Monitor Retention (Days)</label>
          <input value={settings.monitoring_days || ''} onChange={(e) => setSettings({ ...settings, monitoring_days: e.target.value })} className="input-field" />
        </div>
      </div>
      <button type="submit" className="btn-primary">Save Settings</button>
    </form>
  );
}
