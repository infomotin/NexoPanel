import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Globe, FolderOpen, Database, HardDrive, Activity,
  Shield, Terminal, Clock, Store, Settings, LogOut, Search,
  PanelLeftClose, PanelLeftOpen, RefreshCw, Container
} from 'lucide-react';
import { clearToken } from '../api';

const navItems = [
  { to: '/home', label: 'Home', icon: LayoutDashboard },
  { to: '/website', label: 'Website', icon: Globe },
  { to: '/ftp', label: 'FTP', icon: HardDrive },
  { to: '/databases', label: 'Databases', icon: Database },
  { to: '/docker', label: 'Docker', icon: Container },
  { to: '/monitor', label: 'Monitor', icon: Activity },
  { to: '/security', label: 'Security', icon: Shield },
  { to: '/files', label: 'Files', icon: FolderOpen },
  { to: '/terminal', label: 'Terminal', icon: Terminal },
  { to: '/cron', label: 'Cron', icon: Clock },
  { to: '/app-store', label: 'App Store', icon: Store },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const navigate = useNavigate();

  function handleLogout() {
    clearToken();
    navigate('/login');
  }

  const filteredNav = navItems.filter((item) =>
    item.label.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      {/* Dark Left Sidebar */}
      <aside className={`${collapsed ? 'w-16' : 'w-56'} bg-[#161b26] text-slate-300 flex flex-col transition-all duration-200 shrink-0 border-r border-slate-800`}>
        <div className="h-12 px-3 flex items-center justify-between border-b border-slate-800">
          {!collapsed && (
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded bg-emerald-500 flex items-center justify-center text-white font-bold text-xs">N</div>
              <span className="font-semibold text-white text-sm">NexoPanel</span>
            </div>
          )}
          <button onClick={() => setCollapsed(!collapsed)} className="p-1 rounded hover:bg-slate-800 text-slate-400" title="Toggle Sidebar">
            {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>

        {!collapsed && (
          <div className="p-2 border-b border-slate-800">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search (Ctrl+K)"
                className="w-full bg-slate-900/80 border border-slate-700 rounded pl-8 pr-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5 text-xs">
          {filteredNav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-2.5 py-2 rounded transition-colors ${
                    isActive
                      ? 'bg-emerald-600/20 text-emerald-400 border-l-2 border-emerald-500'
                      : 'hover:bg-slate-800/70 text-slate-300'
                  }`
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        <div className="p-2 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded text-xs text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            {!collapsed && <span>Log out</span>}
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-12 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-800">127.0.0.1</span>
            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">Linux</span>
            <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">PRO · v1.0.0</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => window.location.reload()} className="btn-secondary">
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Refresh</span>
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4">
          <Outlet />
        </main>

        <footer className="h-8 bg-white border-t border-slate-200 px-4 flex items-center justify-between text-[11px] text-slate-500 shrink-0">
          <span>NexoPanel Server Control Plane</span>
          <span>Documentation · Support</span>
        </footer>
      </div>
    </div>
  );
}
