import { useNavigate } from 'react-router-dom';
import { ArrowRight, Sun, Moon, HeartHandshake } from 'lucide-react';
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
                        <img src={logoSvg} alt="" className="w-20 h-20 object-contain" />
                        <div>
                            <span className="text-3xl font-bold tracking-tight block text-slate-900 dark:text-white">FallDetect</span>
                            <span className="text-2xs text-emerald-600 dark:text-emerald-400 font-medium">Pemantauan jatuh untuk panti</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <button
                        onClick={toggleTheme}
                        className="p-2.5 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors hover:bg-emerald-50 dark:hover:bg-emerald-950/50"
                        title="Ubah tema"
                        aria-label="Ubah tema"
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
                        Prototipe proyek mahasiswa, bukan alat kesehatan bersertifikat
                    </span>
                    <h1 className="text-4xl md:text-5xl font-extrabold mt-6 mb-6 tracking-tight leading-tight">
                        Membantu perawat tahu <br />
                        <span className="text-emerald-600 dark:text-emerald-400">lebih cepat saat penghuni jatuh</span>
                    </h1>
                    <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                        Kamera di kamar mengirim gambar ke server. Model AI membaca posisi tubuh, dan bila seseorang
                        terbaca berbaring melewati batas waktu, dasbor dan grup Telegram perawat diberi tahu. Sistem bisa
                        melewatkan kejadian dan bisa memberi alarm palsu, jadi tidak menggantikan pengawasan perawat.
                    </p>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg shadow-xl shadow-emerald-600/25 transition-all flex items-center gap-3"
                    >
                        <HeartHandshake className="w-5 h-5" aria-hidden="true" /> Masuk ke dasbor
                    </button>
                </div>

                {/* Gambar Ilustrasi Caregiver & Lansia */}
                <div className="relative">
                    <div className="relative rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl bg-slate-900">
                        <img
                            src="https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?q=80&w=1000&auto=format&fit=crop"
                            alt="Caregiver mendampingi lansia di panti jompo"
                            className="w-full h-[400px] object-cover opacity-90 hover:scale-105 transition-transform duration-700"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent flex items-end p-6">
                            <div className="text-white">
                                <p className="font-semibold text-sm">Dirancang untuk perawat panti</p>
                                <p className="text-xs text-slate-300">Foto ilustrasi.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </header>
        </div>
    );
}