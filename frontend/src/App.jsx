import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, History, Settings as SettingsIcon, Video, ShieldCheck, Sun, Moon, LogOut, Camera, Menu, X } from 'lucide-react';
import { ThemeProvider, useTheme } from './context/ThemeContext';

import LandingPage from './pages/LandingPage';
import SimulationDashboard from './pages/SimulationDashboard';
import AlertHistory from './pages/AlertHistory';
import Settings from './pages/Settings';
import Cameras from './pages/Cameras';
import Login from './pages/Login';
import LiveCamera from './pages/LiveCamera';

// Komponen Sidebar untuk Dashboard Caregiver
function DashboardLayout({ historyItems, onClearHistory }) {
  const { darkMode, setDarkMode } = useTheme();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false); // State untuk buka/tutup sidebar

  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Simulasi Live' },
    { to: '/dashboard/camera-test', icon: Camera, label: 'Testing Kamera HP' },
    { to: '/dashboard/cameras', icon: Video, label: 'Kelola Kamera' },
    { to: '/dashboard/history', icon: History, label: 'Riwayat Insiden' },
    { to: '/dashboard/settings', icon: SettingsIcon, label: 'Pengaturan' },
  ];

  return (
    <div className="flex min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200 font-sans transition-colors overflow-x-hidden relative">

      {/* Tombol Hamburger Floating untuk Membuka Sidebar di Mobile */}
      <button
        onClick={() => setSidebarOpen(true)}
        className="md:hidden fixed top-4 left-4 z-30 p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-lg text-slate-700 dark:text-slate-200"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Overlay Gelap saat Sidebar Terbuka di HP */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="md:hidden fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
        />
      )}

      {/* Sidebar (Collapsible Drawer) */}
      <aside className={`
        fixed md:static inset-y-0 left-0 z-50
        w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 
        flex flex-col p-4 shrink-0 transition-transform duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
      `}>
        <div className="mb-8 px-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center text-white font-bold">
              FD
            </span>
            <span className="font-bold tracking-tight text-lg">FallDetect</span>
          </div>
          {/* Tombol Tutup Sidebar khusus Mobile */}
          <button
            onClick={() => setSidebarOpen(false)}
            className="md:hidden p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex flex-col gap-2 flex-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/dashboard'}
              onClick={() => setSidebarOpen(false)} // Otomatis tutup sidebar saat menu diklik di HP
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl transition-colors font-medium text-sm ${isActive
                  ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/20'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`
              }
            >
              <item.icon className="w-5 h-5 shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Footer Sidebar: Toggle Dark/Light & Logout */}
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <button
            onClick={() => setDarkMode(!darkMode)}
            className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:opacity-80 transition-opacity"
            title="Ubah Tema"
          >
            {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-500/10 text-red-600 dark:text-red-400 text-xs font-semibold hover:bg-red-500/20 transition-colors"
          >
            <LogOut className="w-4 h-4" /> Keluar
          </button>
        </div>
      </aside>

      {/* Main Content Area dengan min-w-0 agar tidak meluber */}
      <main className="flex-1 min-w-0 overflow-y-auto pb-10 md:pb-0 pt-16 md:pt-0 bg-slate-100 dark:bg-slate-950">
        <Routes>
          <Route path="" element={<SimulationDashboard addHistoryItem={onClearHistory} />} />
          <Route path="camera-test" element={<LiveCamera addHistoryItem={onClearHistory} />} />
          <Route path="cameras" element={<Cameras />} />
          <Route path="history" element={<AlertHistory history={historyItems} />} />
          <Route path="settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [historyItems, setHistoryItems] = useState([
    { id: 1, location: 'Kamar 01', time: '02/10/2026, 12:00:00', status: 'confirmed', note: 'Contoh: Lansia terpeleset saat bangun tidur.' }
  ]);

  const addHistoryItem = (newItem) => {
    setHistoryItems(prev => [newItem, ...prev]);
  };

  return (
    <ThemeProvider>
      <Router>
        <Routes>
          {/* Landing Page Utama */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<Login />} />
          {/* Dashboard Area untuk Caregiver */}
          <Route path="/dashboard/*" element={<DashboardLayout historyItems={historyItems} onClearHistory={addHistoryItem} />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}