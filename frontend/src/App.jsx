import { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { LayoutDashboard, History, Settings as SettingsIcon, Video, Sun, Moon, LogOut, Menu, X, Loader2, ServerOff } from 'lucide-react';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { LiveProvider, useLive } from './context/LiveContext';
import LayarDinding from './pages/LayarDinding';
import { AuthProvider } from './context/AuthContext';
import { useAuth, usePengunjung } from './context/auth';
import { API_BASE } from './config';
import AlertBanner from './components/AlertBanner';

import LandingPage from './pages/LandingPage';
import SimulationDashboard from './pages/SimulationDashboard';
import AlertHistory from './pages/AlertHistory';
import Settings from './pages/Settings';
import Cameras from './pages/Cameras';
import Login from './pages/Login';
import LiveCamera from './pages/LiveCamera';

/** Lencana jumlah insiden di menu. Merah hanya kalau ada alarm yang belum ditangani. */
function Lencana({ ringkasan }) {
  if (!ringkasan?.perlu_tindakan) return null;
  const alarm = ringkasan.belum_ditangani > 0;
  return (
    <span
      className={`ml-auto min-w-6 h-6 px-1.5 rounded-full text-xs font-semibold tabular-nums inline-flex items-center justify-center ${alarm
        ? 'bg-red-600 text-white'
        : 'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100'}`}
    >
      {ringkasan.perlu_tindakan}
      <span className="sr-only"> perlu tindakan</span>
    </span>
  );
}

// Komponen Sidebar untuk Dashboard Caregiver
function TataLetakDashboard() {
  const { darkMode, setDarkMode } = useTheme();
  const { akun, keluar } = useAuth();
  const pengunjung = usePengunjung();
  const { ringkasan } = useLive();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false); // State untuk buka/tutup sidebar

  // Menu bertanda `tim` tidak ditampilkan untuk pengunjung pameran: isinya alat kerja
  // tim (alamat kamera, pengaturan), bukan tontonan. Uji Kamera dibuka dari Daftar Kamera.
  const navItems = [
    { to: '/dashboard', icon: LayoutDashboard, label: 'Pemantauan' },
    { to: '/dashboard/cameras', icon: Video, label: 'Daftar Kamera', tim: true },
    { to: '/dashboard/history', icon: History, label: 'Riwayat Insiden', lencana: true },
    { to: '/dashboard/settings', icon: SettingsIcon, label: 'Pengaturan', tim: true },
  ].filter((item) => !(pengunjung && item.tim));
  const khususTim = (halaman) => (pengunjung ? <Navigate to="/dashboard" replace /> : halaman);

  const keluarSekarang = async () => {
    await keluar();
    navigate('/login', { replace: true });
  };

  return (
    // overflow-x-clip, bukan overflow-x-hidden: hidden menjadikan wadah ini wadah gulir,
    // sehingga banner alarm dan sidebar yang sticky ikut tergulir pergi alih-alih
    // menempel di atas layar. clip tetap memotong luapan ke samping tanpa efek itu.
    <div className="flex min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-200 font-sans transition-colors overflow-x-clip relative">

      {/* Overlay Gelap saat Sidebar Terbuka di HP */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="md:hidden fixed inset-0 bg-black/50 z-40 backdrop-blur-sm"
        />
      )}

      {/* Sidebar (Collapsible Drawer) */}
      <aside className={`
        fixed md:sticky md:top-0 md:h-screen md:self-start inset-y-0 left-0 z-50
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
            aria-label="Tutup menu"
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
                // Menu aktif berwarna netral: hijau disisihkan untuk logo, tombol utama, dan sukses.
                `flex items-center gap-3 px-4 py-3 rounded-xl transition-colors font-medium text-sm ${isActive
                  ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`
              }
            >
              <item.icon className="w-5 h-5 shrink-0" />
              <span>{item.label}</span>
              {item.lencana && <Lencana ringkasan={ringkasan} />}
            </NavLink>
          ))}
        </nav>

        {/* Footer Sidebar: siapa yang bertugas, tema, dan keluar */}
        <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
          <div className="px-1 mb-3 min-w-0">
            {pengunjung ? (
              <>
                <p className="font-semibold text-sm">Pengunjung</p>
                <p className="text-xs text-slate-500">Hanya melihat, tidak bisa mengubah apa pun</p>
              </>
            ) : (
              <>
                <p className="text-xs text-slate-500">Sedang bertugas</p>
                <p className="font-semibold text-sm truncate">{akun?.display_name}</p>
                <p className="text-xs text-slate-500">{akun?.role === 'pengelola' ? 'Pengelola' : 'Perawat'}</p>
              </>
            )}
          </div>
          <div className="flex items-center justify-between">
            <button
              onClick={() => setDarkMode(!darkMode)}
              className="p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:opacity-80 transition-opacity"
              title="Ubah tema"
              aria-label="Ubah tema"
            >
              {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <button
              onClick={keluarSekarang}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <LogOut className="w-4 h-4" /> Keluar
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area dengan min-w-0 agar tidak meluber */}
      {/* Tanpa overflow-y-auto: halaman digulir oleh jendela, supaya bilah atas dan
          banner alarm yang sticky menempel di atas layar. */}
      <main className="flex-1 min-w-0 pb-10 md:pb-0 bg-slate-100 dark:bg-slate-950">
        {/* Bilah atas khusus HP. Tombol menu ada di sini, bukan melayang di atas isi
            halaman, karena tombol melayang menutupi tombol dan teks saat digulir. */}
        <div className="md:hidden sticky top-0 z-30 h-14 px-4 flex items-center gap-3 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Buka menu"
            className="p-2 -ml-2 rounded-lg text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          >
            <Menu className="w-5 h-5" />
          </button>
          <span aria-hidden="true" className="w-7 h-7 rounded-lg bg-emerald-600 flex items-center justify-center text-white text-xs font-bold">
            FD
          </span>
          <span className="font-bold tracking-tight">FallDetect</span>
        </div>
        <AlertBanner />
        <Routes>
          <Route path="" element={<SimulationDashboard />} />
          <Route path="camera-test" element={khususTim(<LiveCamera />)} />
          <Route path="cameras" element={khususTim(<Cameras />)} />
          <Route path="history" element={<AlertHistory />} />
          <Route path="settings" element={khususTim(<Settings />)} />
        </Routes>
      </main>
    </div>
  );
}

function DashboardLayout() {
  return (
    <LiveProvider>
      <TataLetakDashboard />
    </LiveProvider>
  );
}

function LayarPenuh({ children }) {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-700 dark:text-slate-200 flex flex-col items-center justify-center gap-3 p-6 text-center">
      {children}
    </div>
  );
}

/**
 * Dashboard hanya untuk yang sudah masuk. Backend juga menolak semua API tanpa
 * sesi, jadi ini bukan satu-satunya pengaman, hanya supaya pengguna diarahkan
 * ke halaman Login alih-alih melihat dashboard kosong.
 */
function Terlindungi({ children }) {
  const { status, periksa } = useAuth();
  const lokasi = useLocation();

  if (status === 'memuat') {
    return (
      <LayarPenuh>
        <Loader2 className="w-6 h-6 animate-spin" aria-hidden="true" />
        <p className="text-sm">Memeriksa sesi…</p>
      </LayarPenuh>
    );
  }
  if (status === 'terputus') {
    return (
      <LayarPenuh>
        <ServerOff className="w-8 h-8" aria-hidden="true" />
        <p className="font-semibold">Backend tidak bisa dihubungi</p>
        <p className="text-sm text-slate-500 max-w-sm">
          Dashboard butuh backend di {API_BASE}. Jalankan run-backend.bat, lalu coba lagi.
        </p>
        <button
          type="button"
          onClick={periksa}
          className="min-h-11 px-4 rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white text-sm font-semibold"
        >
          Coba lagi
        </button>
      </LayarPenuh>
    );
  }
  if (status !== 'masuk') return <Navigate to="/login" replace state={{ dari: lokasi.pathname }} />;
  return children;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Landing Page Utama */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<Login />} />
            {/* QR di stand pameran: /lihat#t=TOKEN, halaman Login dengan tombol pengunjung. */}
            <Route path="/lihat" element={<Login />} />
            {/* Dashboard Area untuk Caregiver */}
            <Route path="/dashboard/*" element={<Terlindungi><DashboardLayout /></Terlindungi>} />
            {/* Layar besar di ruang jaga: baca saja, tanpa menu samping. */}
            <Route path="/dinding" element={<Terlindungi><LiveProvider><LayarDinding /></LiveProvider></Terlindungi>} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}
