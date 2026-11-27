import React from 'react';
import { Link } from 'react-router-dom';

export default function DockerPage() {
  return (
    <div className="space-y-4">
      <div className="card p-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-slate-900">Docker & Container Manager</h2>
          <p className="text-xs text-slate-500">Manage Docker containers, images, Compose stacks, networks, and daemon settings.</p>
        </div>
        <Link to="/app-store" className="btn-primary">Install / Manage in App Store</Link>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div className="card p-4 space-y-2">
          <h3 className="font-bold text-slate-700">Daemon Configuration</h3>
          <div className="flex justify-between py-1 border-b"><span>Unix Socket</span><span className="font-mono">unix:///var/run/docker.sock</span></div>
          <div className="flex justify-between py-1 border-b"><span>One-Click Install Dir</span><span className="font-mono">/www/dk_project</span></div>
          <div className="flex justify-between py-1"><span>iptables / live_restore</span><span className="text-emerald-600 font-medium">Enabled</span></div>
        </div>
        <div className="card p-4 space-y-2">
          <h3 className="font-bold text-slate-700">Host Environment</h3>
          <div className="flex justify-between py-1 border-b"><span>Architecture</span><span>x86_64</span></div>
          <div className="flex justify-between py-1 border-b"><span>Compose</span><span>v2.27.0</span></div>
          <div className="flex justify-between py-1"><span>Status</span><span className="text-slate-600">Ready</span></div>
        </div>
      </div>
    </div>
  );
}
