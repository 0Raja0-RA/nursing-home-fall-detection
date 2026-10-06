import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowRight, Sun, Moon, HeartHandshake } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import logoSvg from '../assets/logo.svg';

export default function LandingPage() {
    const navigate = useNavigate();
    const { darkMode, toggleTheme } = useTheme();

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 transition-colors">
            {/* Navbar */}
            <nav className="flex justify-between items-center px-8 py-6 max-w-7xl mx-auto">
                <div className="flex items-center gap-3">
                    {/* Logo Kustom: Perisai Kesehatan (Emerald Green) */}
                    <div className="flex items-center gap-2.5">
                        <img src={logoSvg} alt="Fall-Care AI" className="w-20 h-20 object-contain" />
                        <div>
                            <span className="text-3xl font-bold tracking-tight block text-slate-900 dark:text-white">Fall-Care AI</span>
                            <span className="text-2xs text-emerald-600 dark:text-emerald-400 font-medium">Fall Detection Monitoring</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <button
                        onClick={toggleTheme}
                        className="p-2.5 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors hover:bg-emerald-50 dark:hover:bg-emerald-950/50"
                        title="Ubah Tema"
                    >
                        {darkMode ? <Sun className="w-5 h-5 text-emerald-400" /> : <Moon className="w-5 h-5 text-emerald-600" />}
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
                        Sistem Monitoring Panti Jompo Berbasis AI
                    </span>
                    <h1 className="text-4xl md:text-5xl font-extrabold mt-6 mb-6 tracking-tight leading-tight">
                        Monitoring Lansia 24/7 <br />
                        <span className="text-emerald-600 dark:text-emerald-400">Aman & Real-time</span>
                    </h1>
                    <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                        Menghadirkan rasa tenang bagi perawat dan keluarga. Memanfaatkan kecerdasan buatan YOLO11 untuk mengenali risiko jatuh secara akurat di setiap detik, serta mengaktifkan alarm darurat instan ke dasbor web dan Telegram sebelum terlambat.
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
                    <div className="absolute -inset-2 bg-gradient-to-r from-emerald-600 to-teal-600 rounded-3xl blur-xl opacity-30 animate-pulse"></div>
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