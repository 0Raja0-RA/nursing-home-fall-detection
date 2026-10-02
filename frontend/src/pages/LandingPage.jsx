import { useNavigate } from 'react-router-dom';
import { ShieldAlert, Cpu, ArrowRight, Sun, Moon, HeartHandshake } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export default function LandingPage() {
    const navigate = useNavigate();
    const { darkMode, setDarkMode } = useTheme();

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 transition-colors">
            {/* Navbar */}
            <nav className="flex justify-between items-center px-8 py-6 max-w-7xl mx-auto">
                <div className="flex items-center gap-2">
                    <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white font-bold">
                        FD
                    </div>
                    <span className="text-xl font-bold tracking-tight">FallDetect AI</span>
                </div>
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setDarkMode(!darkMode)}
                        className="p-2.5 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors"
                    >
                        {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                    </button>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl font-medium transition-colors flex items-center gap-2 shadow-lg shadow-emerald-600/20"
                    >
                        Login Caregiver <ArrowRight className="w-4 h-4" />
                    </button>
                </div>
            </nav>

            {/* Hero Section */}
            <header className="max-w-7xl mx-auto px-6 py-12 md:py-20 grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                <div>
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        Sistem Pengawasan Panti Jompo Berbasis AI
                    </span>
                    <h1 className="text-4xl md:text-5xl font-extrabold mt-6 mb-6 tracking-tight leading-tight">
                        Pengawasan Lansia 24 Jam <br />
                        <span className="text-emerald-600">Tanpa Celah & Real-time</span>
                    </h1>
                    <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                        Solusi cerdas menggunakan model YOLO11 dan State Machine untuk mendeteksi insiden jatuh secara otomatis, memberikan peringatan instan ke perawat via Web dan Telegram.
                    </p>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg shadow-xl shadow-emerald-600/25 transition-all flex items-center gap-3"
                    >
                        <HeartHandshake className="w-5 h-5" /> Coba Simulasi Dashboard
                    </button>
                </div>

                {/* Gambar Ilustrasi Caregiver & Lansia */}
                <div className="relative">
                    <div className="absolute -inset-2 bg-gradient-to-r from-emerald-600 to-indigo-600 rounded-3xl blur-xl opacity-30 animate-pulse"></div>
                    <div className="relative rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl bg-slate-900">
                        <img
                            src="https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?q=80&w=1000&auto=format&fit=crop"
                            alt="Caregiver mendampingi lansia di panti jompo"
                            className="w-full h-[400px] object-cover opacity-90 hover:scale-105 transition-transform duration-700"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent flex items-end p-6">
                            <div className="text-white">
                                <p className="font-semibold text-sm">Keamanan & Kenyamanan Terjaga</p>
                                <p className="text-xs text-slate-300">Membantu perawat memantau keselamatan penghuni panti jompo.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </header>
        </div>
    );
}