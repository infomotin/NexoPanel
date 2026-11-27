import React, { useState } from 'react';
import { apiFetch } from '../api';

export default function TerminalPage() {
  const [history, setHistory] = useState<string[]>(['NexoPanel Web Terminal — type "help" for commands.']);
  const [cmd, setCmd] = useState('');

  async function runCmd(e: React.FormEvent) {
    e.preventDefault();
    if (!cmd.trim()) return;
    const res = await apiFetch('/terminal/exec', { method: 'POST', body: JSON.stringify({ command: cmd }) });
    setHistory((prev) => [...prev, `$ ${cmd}`, res.output]);
    setCmd('');
  }

  return (
    <div className="card p-4 bg-[#0f172a] text-emerald-400 font-mono text-xs h-[75vh] flex flex-col">
      <div className="flex-1 overflow-y-auto space-y-1 mb-3">
        {history.map((line, i) => (
          <div key={i} className="whitespace-pre-wrap">{line}</div>
        ))}
      </div>
      <form onSubmit={runCmd} className="flex items-center gap-2 border-t border-slate-800 pt-2">
        <span className="text-emerald-500 font-bold">root@nexopanel:~#</span>
        <input
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          className="flex-1 bg-transparent text-white focus:outline-none"
          placeholder="Enter command..."
          autoFocus
        />
      </form>
    </div>
  );
}
