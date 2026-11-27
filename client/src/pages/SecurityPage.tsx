import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function SecurityPage() {
  const [fw, setFw] = useState<any>({ firewall_enabled: true, block_icmp: false, rules: [] });
  const [form, setForm] = useState({ protocol: 'tcp', port: '', strategy: 'allow', direction: 'inbound', source_ip: '0.0.0.0/0', remarks: '' });
  const [scanResult, setScanResult] = useState<any>(null);

  async function load() {
    setFw(await apiFetch('/security/firewall'));
  }
  useEffect(() => { load(); }, []);

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch('/security/firewall/rules', { method: 'POST', body: JSON.stringify(form) });
    setForm({ protocol: 'tcp', port: '', strategy: 'allow', direction: 'inbound', source_ip: '0.0.0.0/0', remarks: '' });
    await load();
  }

  async function deleteRule(id: number) {
    await apiFetch(`/security/firewall/rules/${id}`, { method: 'DELETE' });
    await load();
  }

  async function runScan() {
    setScanResult(await apiFetch('/security/scan', { method: 'POST' }));
  }

  return (
    <div className="space-y-4">
      <div className="card p-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-4 text-xs">
          <span className="font-semibold">Firewall: <span className="text-emerald-600">{fw.firewall_enabled ? 'Active' : 'Disabled'}</span></span>
          <span className="font-semibold">Block ICMP: <span className="text-slate-600">{fw.block_icmp ? 'On' : 'Off'}</span></span>
        </div>
        <button onClick={runScan} className="btn-secondary">Run Security Scan</button>
      </div>

      {scanResult && (
        <div className="card p-3 bg-emerald-50 border-emerald-200 text-xs text-emerald-800">
          Security scan completed at {new Date(scanResult.scannedAt).toLocaleTimeString()}: <strong>{scanResult.risksFound} risks found</strong> ({scanResult.checks.join(', ')}).
        </div>
      )}

      <form onSubmit={addRule} className="card p-4 space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">Add Port Rule</h3>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <select value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value })} className="input-field">
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
          <input value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} placeholder="Port (e.g. 8080)" className="input-field" required />
          <select value={form.strategy} onChange={(e) => setForm({ ...form, strategy: e.target.value })} className="input-field">
            <option value="allow">Allow</option>
            <option value="block">Block</option>
          </select>
          <select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })} className="input-field">
            <option value="inbound">Inbound</option>
            <option value="outbound">Outbound</option>
          </select>
          <input value={form.source_ip} onChange={(e) => setForm({ ...form, source_ip: e.target.value })} placeholder="Source IP" className="input-field" />
          <input value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} placeholder="Remarks" className="input-field" />
        </div>
        <button type="submit" className="btn-primary">+ Add Port Rule</button>
      </form>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr><th>Protocol</th><th>Port</th><th>Strategy</th><th>Direction</th><th>Source IP</th><th>Remarks</th><th className="text-right">Operate</th></tr>
          </thead>
          <tbody>
            {fw.rules.map((r: any) => (
              <tr key={r.id}>
                <td className="uppercase font-mono">{r.protocol}</td>
                <td className="font-mono font-semibold">{r.port}</td>
                <td>
                  <span className={`px-2 py-0.5 rounded text-[11px] font-semibold uppercase ${r.strategy === 'allow' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                    {r.strategy}
                  </span>
                </td>
                <td className="capitalize">{r.direction}</td>
                <td className="font-mono">{r.source_ip}</td>
                <td>{r.remarks}</td>
                <td className="text-right"><button onClick={() => deleteRule(r.id)} className="text-rose-600 hover:underline">Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
