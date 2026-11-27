import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { apiFetch } from '../api';

export default function MonitorPage() {
  const [range, setRange] = useState('today');
  const [series, setSeries] = useState<any[]>([]);

  async function load(r = range) {
    const res = await apiFetch(`/monitor/history?range=${r}`);
    setSeries(res.series);
  }

  useEffect(() => { load(range); }, [range]);

  const charts = [
    { title: 'Load Average', key: 'load', color: '#10b981' },
    { title: 'CPU (%)', key: 'cpu', color: '#3b82f6' },
    { title: 'Memory (%)', key: 'memory', color: '#8b5cf6' },
    { title: 'Disk I/O (MB/s)', key: 'diskIo', color: '#f59e0b' },
    { title: 'Network Inbound (KB/s)', key: 'netIn', color: '#06b6d4' },
    { title: 'Swap Usage (%)', key: 'swap', color: '#ec4899' },
  ];

  return (
    <div className="space-y-4">
      <div className="card p-3 flex items-center justify-between">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">System Monitor</h2>
        <div className="flex gap-1.5 text-xs">
          {[
            { id: 'yesterday', label: 'Yesterday' },
            { id: 'today', label: 'Today' },
            { id: '7d', label: 'Last 7 days' },
          ].map((r) => (
            <button
              key={r.id}
              onClick={() => setRange(r.id)}
              className={`px-2.5 py-1 rounded ${range === r.id ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700'}`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {charts.map((c) => (
          <div key={c.key} className="card p-4">
            <h3 className="text-xs font-bold text-slate-700 mb-3">{c.title}</h3>
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey={c.key} stroke={c.color} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
