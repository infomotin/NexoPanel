import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { apiFetch } from '../api';

function GaugeCard({ label, percent, display, sub, color }: { label: string; percent: number; display: string; sub: string; color: string }) {
  const dash = 97.4;
  const offset = dash - (dash * Math.min(percent, 100)) / 100;
  return (
    <div className="card p-4 flex items-center justify-between">
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
        <p className="text-xl font-bold text-slate-900 mt-1">{display}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">{sub}</p>
      </div>
      <svg className="w-14 h-14 -rotate-90" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e2e8f0" strokeWidth="3" />
        <circle cx="18" cy="18" r="15.5" fill="none" stroke={color} strokeWidth="3" strokeDasharray={dash} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
    </div>
  );
}

export default function HomePage() {
  const [data, setData] = useState<any>(null);
  const [traffic, setTraffic] = useState<any[]>([]);
  const [memo, setMemo] = useState('');
  const [memoSaved, setMemoSaved] = useState(false);

  async function loadDashboard() {
    const res = await apiFetch('/dashboard');
    setData(res);
    setMemo(res.memo || '');
    setTraffic((prev) => [
      ...prev.slice(-14),
      {
        time: new Date().toLocaleTimeString().slice(0, 8),
        up: res.network.upstreamKbps,
        down: res.network.downstreamKbps,
      },
    ]);
  }

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(loadDashboard, 3000);
    return () => clearInterval(timer);
  }, []);

  async function saveMemo() {
    await apiFetch('/dashboard/memo', { method: 'PUT', body: JSON.stringify({ memo }) });
    setMemoSaved(true);
    setTimeout(() => setMemoSaved(false), 1500);
  }

  if (!data) return <div className="text-xs text-slate-500 p-4">Loading dashboard telemetry...</div>;

  return (
    <div className="space-y-4">
      {/* 4 Circular Resource Gauges */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <GaugeCard
          label="Load Status"
          percent={Math.min(100, (data.load.avg1 / Math.max(data.cpu.cores, 1)) * 100)}
          display={data.load.status}
          sub={`${data.load.avg1} / ${data.load.avg5} / ${data.load.avg15}`}
          color="#10b981"
        />
        <GaugeCard label="CPU" percent={data.cpu.percent} display={`${data.cpu.percent}%`} sub={`${data.cpu.cores} Cores`} color="#3b82f6" />
        <GaugeCard
          label="RAM"
          percent={data.ram.percent}
          display={`${data.ram.percent}%`}
          sub={`${Math.round(data.ram.usedBytes / 1048576)} MB / ${(data.ram.totalBytes / 1073741824).toFixed(2)} GB`}
          color="#8b5cf6"
        />
        <GaugeCard label="Disk (/)" percent={data.disk.percent} display={`${data.disk.percent}%`} sub={`${data.disk.usedGb} GB / ${data.disk.totalGb} GB`} color="#f59e0b" />
      </div>

      {/* Overview Summary Cards + Memo */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <Link to="/website" className="card p-3 hover:border-emerald-400 transition-colors">
          <div className="text-[11px] text-slate-500 font-semibold uppercase">Site</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{data.counts.sitesAll}</div>
          <div className="text-[11px] text-emerald-600 mt-0.5">Running: {data.counts.sitesRunning} · Stopped: {data.counts.sitesStopped}</div>
        </Link>
        <Link to="/ftp" className="card p-3 hover:border-emerald-400 transition-colors">
          <div className="text-[11px] text-slate-500 font-semibold uppercase">FTP</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{data.counts.ftpCount}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Active Accounts</div>
        </Link>
        <Link to="/databases" className="card p-3 hover:border-emerald-400 transition-colors">
          <div className="text-[11px] text-slate-500 font-semibold uppercase">Databases</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{data.counts.dbCount}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Managed Schemas</div>
        </Link>
        <Link to="/security" className="card p-3 hover:border-emerald-400 transition-colors">
          <div className="text-[11px] text-slate-500 font-semibold uppercase">Security</div>
          <div className="text-2xl font-bold text-emerald-600 mt-1">{data.counts.securityRisks}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Risks Found</div>
        </Link>
        <div className="card p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-slate-500 font-semibold uppercase">Memo</span>
            <button onClick={saveMemo} className="text-[11px] text-emerald-600 hover:underline">{memoSaved ? 'Saved!' : 'Save'}</button>
          </div>
          <textarea value={memo} onChange={(e) => setMemo(e.target.value)} rows={2} className="input-field text-[11px]" />
        </div>
      </div>

      {/* Software Quick-Access Grid & Real-Time Traffic Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">Software Quick Access</h2>
            <Link to="/app-store" className="text-xs text-emerald-600 hover:underline">App Store</Link>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {data.softwareHome.map((sw: any) => (
              <div key={sw.id} className="p-2.5 rounded border border-slate-200 bg-slate-50 flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-slate-800">{sw.name}</div>
                  <div className="text-[10px] text-slate-500">v{sw.version}</div>
                </div>
                <span className="w-2 h-2 rounded-full bg-emerald-500" title="Running" />
              </div>
            ))}
          </div>
        </div>

        <div className="card p-4 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">Real-Time Traffic (KB/s)</h2>
            <div className="text-xs text-slate-500 space-x-3">
              <span>Up: <strong className="text-emerald-600">{data.network.upstreamKbps} KB/s</strong></span>
              <span>Down: <strong className="text-blue-600">{data.network.downstreamKbps} KB/s</strong></span>
            </div>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={traffic}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Area type="monotone" dataKey="up" stroke="#10b981" fill="#10b98133" name="Upstream" />
                <Area type="monotone" dataKey="down" stroke="#3b82f6" fill="#3b82f633" name="Downstream" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
