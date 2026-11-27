import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { getToken } from './api';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import WebsitesPage from './pages/WebsitesPage';
import DatabasesPage from './pages/DatabasesPage';
import FilesPage from './pages/FilesPage';
import CronPage from './pages/CronPage';
import SecurityPage from './pages/SecurityPage';
import AppStorePage from './pages/AppStorePage';
import MonitorPage from './pages/MonitorPage';
import FtpPage from './pages/FtpPage';
import DockerPage from './pages/DockerPage';
import TerminalPage from './pages/TerminalPage';
import SettingsPage from './pages/SettingsPage';

function Protected({ children }: { children: React.ReactNode }) {
  return getToken() ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Protected><Layout /></Protected>}>
          <Route index element={<Navigate to="/home" replace />} />
          <Route path="home" element={<HomePage />} />
          <Route path="website" element={<WebsitesPage />} />
          <Route path="ftp" element={<FtpPage />} />
          <Route path="databases" element={<DatabasesPage />} />
          <Route path="docker" element={<DockerPage />} />
          <Route path="monitor" element={<MonitorPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="files" element={<FilesPage />} />
          <Route path="terminal" element={<TerminalPage />} />
          <Route path="cron" element={<CronPage />} />
          <Route path="app-store" element={<AppStorePage />} />
          <Route path="packages" element={<AppStorePage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
