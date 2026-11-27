import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiFetch } from '../api';

export default function FilesPage() {
  const [searchParams] = useSearchParams();
  const [currentPath, setCurrentPath] = useState(searchParams.get('path') || '');
  const [entries, setEntries] = useState<any[]>([]);
  const [editorFile, setEditorFile] = useState<{ path: string; content: string } | null>(null);
  const [chmodTarget, setChmodTarget] = useState<{ path: string; mode: string } | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function loadDir(p = currentPath) {
    const res = await apiFetch(`/files/list?path=${encodeURIComponent(p)}`);
    setCurrentPath(res.path);
    setEntries(res.entries);
  }

  useEffect(() => { loadDir(currentPath); }, []);

  async function openFile(path: string) {
    const res = await apiFetch(`/files/read?path=${encodeURIComponent(path)}`);
    setEditorFile({ path: res.path, content: res.content });
  }

  async function saveEditor() {
    if (!editorFile) return;
    await apiFetch('/files/write', { method: 'POST', body: JSON.stringify(editorFile) });
    setEditorFile(null);
    await loadDir();
  }

  async function createFolder() {
    const name = prompt('New folder name:');
    if (!name) return;
    const p = currentPath ? `${currentPath}/${name}` : name;
    await apiFetch('/files/mkdir', { method: 'POST', body: JSON.stringify({ path: p }) });
    await loadDir();
  }

  async function createFile() {
    const name = prompt('New file name:');
    if (!name) return;
    const p = currentPath ? `${currentPath}/${name}` : name;
    await apiFetch('/files/write', { method: 'POST', body: JSON.stringify({ path: p, content: '' }) });
    await loadDir();
  }

  async function renameEntry(oldPath: string, oldName: string) {
    const nextName = prompt('Rename to:', oldName);
    if (!nextName || nextName === oldName) return;
    const dir = oldPath.includes('/') ? oldPath.slice(0, oldPath.lastIndexOf('/')) : '';
    const dst = dir ? `${dir}/${nextName}` : nextName;
    await apiFetch('/files/rename', { method: 'POST', body: JSON.stringify({ source: oldPath, destination: dst }) });
    await loadDir();
  }

  async function saveChmod(e: React.FormEvent) {
    e.preventDefault();
    if (!chmodTarget) return;
    await apiFetch('/files/chmod', { method: 'POST', body: JSON.stringify(chmodTarget) });
    setChmodTarget(null);
    await loadDir();
  }

  async function uploadFile(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return;
    const fd = new FormData();
    fd.append('path', currentPath);
    fd.append('file', e.target.files[0]);
    await apiFetch('/files/upload', { method: 'POST', body: fd });
    await loadDir();
  }

  async function deleteEntry(p: string) {
    await apiFetch(`/files?path=${encodeURIComponent(p)}`, { method: 'DELETE' });
    await loadDir();
  }

  return (
    <div className="space-y-3">
      <div className="card p-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <input type="file" ref={fileRef} onChange={uploadFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} className="btn-primary">Upload</button>
          <button onClick={createFile} className="btn-secondary">+ New File</button>
          <button onClick={createFolder} className="btn-secondary">+ New Folder</button>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <button onClick={() => loadDir('')} className="btn-secondary">/wwwroot</button>
          <span className="font-mono text-slate-600">/{currentPath}</span>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr><th>Name</th><th>Permissions</th><th>Size</th><th>Modified</th><th className="text-right">Operate</th></tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.path}>
                <td>
                  {entry.isDir ? (
                    <button onClick={() => loadDir(entry.path)} className="font-semibold text-emerald-700 hover:underline">
                      📁 {entry.name}
                    </button>
                  ) : (
                    <button onClick={() => openFile(entry.path)} className="font-mono text-slate-800 hover:underline">
                      📄 {entry.name}
                    </button>
                  )}
                </td>
                <td>
                  <button onClick={() => setChmodTarget({ path: entry.path, mode: entry.mode })} className="font-mono text-blue-600 hover:underline">
                    {entry.mode}
                  </button>
                </td>
                <td>{entry.isDir ? '-' : `${entry.size} B`}</td>
                <td className="text-[11px]">{new Date(entry.modifiedAt).toLocaleString()}</td>
                <td className="text-right space-x-2">
                  {!entry.isDir && <button onClick={() => openFile(entry.path)} className="text-emerald-600 hover:underline">Edit</button>}
                  <button onClick={() => renameEntry(entry.path, entry.name)} className="text-blue-600 hover:underline">Rename</button>
                  <button onClick={() => setChmodTarget({ path: entry.path, mode: entry.mode })} className="text-slate-600 hover:underline">Chmod</button>
                  <button onClick={() => deleteEntry(entry.path)} className="text-rose-600 hover:underline">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editorFile && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-6">
          <div className="bg-white rounded-lg p-5 w-full max-w-3xl h-[75vh] flex flex-col">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold font-mono">/wwwroot/{editorFile.path}</h3>
              <button onClick={() => setEditorFile(null)} className="btn-secondary">Close</button>
            </div>
            <textarea
              value={editorFile.content}
              onChange={(e) => setEditorFile({ ...editorFile, content: e.target.value })}
              className="input-field font-mono text-xs flex-1"
            />
            <div className="flex justify-end mt-3">
              <button onClick={saveEditor} className="btn-primary">Save File</button>
            </div>
          </div>
        </div>
      )}

      {chmodTarget && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <form onSubmit={saveChmod} className="bg-white rounded-lg p-5 w-full max-w-xs space-y-3">
            <h3 className="text-sm font-bold">Permissions (chmod)</h3>
            <p className="text-xs font-mono text-slate-500">{chmodTarget.path}</p>
            <input value={chmodTarget.mode} onChange={(e) => setChmodTarget({ ...chmodTarget, mode: e.target.value })} className="input-field font-mono" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setChmodTarget(null)} className="btn-secondary">Cancel</button>
              <button type="submit" className="btn-primary">Apply</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
