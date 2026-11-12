import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Mail, Lock, LogIn, ArrowLeft, AlertCircle, Eye } from 'lucide-react';
import { api, PESAN_TERPUTUS } from '../api';
import { useAuth } from '../context/auth';

const INPUT = 'w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl py-3 pl-11 pr-4 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all text-sm';

/**
 * Token pengunjung dari QR di stand: /lihat#t=TOKEN.
 *
 * Token ditaruh di fragmen (#), bukan query (?), karena fragmen tidak pernah dikirim
 * ke server: tidak tercatat di log backend maupun log tunnel.
 */
function tokenDariFragmen() {
    if (typeof window === 'undefined') return '';
    return new URLSearchParams(window.location.hash.replace(/^#/, '')).get('t') || '';
}

export default function Login() {
    const navigate = useNavigate();
    const lokasi = useLocation();
    const { status, sesiHabis, masuk, masukPengunjung } = useAuth();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [errorMsg, setErrorMsg] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [infoBackend, setInfoBackend] = useState(null);   // { ada_akun, pengunjung_aktif }
    // Dibaca sekali saat halaman dibuka. Fragmennya lalu dihapus dari alamat, supaya
    // token tidak ikut tersalin kalau alamat halaman ini dibagikan.
    const [tokenQr] = useState(tokenDariFragmen);

    useEffect(() => {
        if (tokenQr) window.history.replaceState(window.history.state, '', window.location.pathname);
    }, [tokenQr]);

    // Sudah masuk: langsung ke halaman yang tadi dituju.
    useEffect(() => {
        if (status === 'masuk') navigate(lokasi.state?.dari || '/dashboard', { replace: true });
    }, [status, navigate, lokasi.state]);

    useEffect(() => {
        let batal = false;
        api('/api/auth/status')
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (!batal && d) setInfoBackend(d); })
            .catch(() => { if (!batal) setErrorMsg(PESAN_TERPUTUS); });
        return () => { batal = true; };
    }, []);

    const jalankan = async (aksi) => {
        setErrorMsg('');
        setIsLoading(true);
        try {
            await aksi();
        } catch (err) {
            setErrorMsg(err instanceof TypeError ? PESAN_TERPUTUS : err.message);
        } finally {
            setIsLoading(false);
        }
    };

    const handleLogin = (e) => {
        e.preventDefault();
        jalankan(() => masuk(email, password));
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col justify-center items-center p-4 transition-colors">
            {/* Tombol Kembali */}
            <button
                onClick={() => navigate('/')}
                className="absolute top-6 left-6 flex items-center gap-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors text-sm font-medium"
            >
                <ArrowLeft className="w-4 h-4" /> Kembali ke Beranda
            </button>

            {/* Kartu Login */}
            <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 p-8 mt-12 sm:mt-0">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-emerald-600 rounded-2xl mx-auto flex items-center justify-center text-white font-bold text-2xl mb-4 shadow-lg shadow-emerald-600/30">
                        FD
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Login Caregiver</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
                        Masuk untuk mengakses sistem pemantauan panti jompo.
                    </p>
                </div>

                {sesiHabis && !errorMsg && (
                    <div role="status" className="mb-6 p-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs text-slate-700 dark:text-slate-300">
                        Sesi berakhir. Silakan masuk lagi.
                    </div>
                )}

                {infoBackend && !infoBackend.ada_akun && (
                    <div role="status" className="mb-6 p-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs text-slate-700 dark:text-slate-300">
                        Belum ada akun. Isi <code>DEMO_USERNAME</code> dan <code>DEMO_PASSWORD</code> di
                        {' '}<code>backend/.env</code>, lalu jalankan ulang backend.
                    </div>
                )}

                {errorMsg && (
                    <div role="alert" className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-600 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                        <span>{errorMsg}</span>
                    </div>
                )}

                <form onSubmit={handleLogin} className="space-y-6">
                    {/* Input Email */}
                    <div>
                        <label htmlFor="email" className="block text-sm font-semibold text-slate-600 dark:text-slate-300 mb-2">
                            Email
                        </label>
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <Mail className="w-5 h-5 text-slate-400" aria-hidden="true" />
                            </div>
                            <input
                                id="email"
                                type="text"
                                inputMode="email"
                                autoComplete="username"
                                autoCapitalize="none"
                                spellCheck={false}
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className={INPUT}
                                placeholder="nama@panti.com"
                            />
                        </div>
                    </div>

                    {/* Input Password */}
                    <div>
                        <label htmlFor="password" className="block text-sm font-semibold text-slate-600 dark:text-slate-300 mb-2">
                            Password
                        </label>
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <Lock className="w-5 h-5 text-slate-400" aria-hidden="true" />
                            </div>
                            <input
                                id="password"
                                type="password"
                                autoComplete="current-password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className={INPUT}
                                placeholder="••••••••"
                            />
                        </div>
                    </div>

                    {/* Tombol Submit */}
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full bg-emerald-700 hover:bg-emerald-800 text-white font-bold py-3.5 rounded-xl shadow-lg shadow-emerald-700/30 transition-all flex items-center justify-center gap-2 disabled:opacity-70 text-sm"
                    >
                        {isLoading ? 'Memeriksa…' : <><LogIn className="w-5 h-5" aria-hidden="true" /> Masuk ke Dashboard</>}
                    </button>
                </form>

                {/* Pengunjung pameran: hanya lewat QR di stand, yang membawa token. */}
                {tokenQr ? (
                    <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-800">
                        <button
                            type="button"
                            onClick={() => jalankan(() => masukPengunjung(tokenQr))}
                            disabled={isLoading}
                            className="w-full min-h-11 rounded-xl border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-100 font-semibold text-sm flex items-center justify-center gap-2 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-70"
                        >
                            <Eye className="w-5 h-5" aria-hidden="true" /> Masuk sebagai pengunjung
                        </button>
                        <p className="mt-2 text-center text-xs text-slate-500">
                            Hanya melihat kamera, status, dan riwayat. Tidak bisa mengubah apa pun.
                        </p>
                    </div>
                ) : infoBackend?.pengunjung_aktif && (
                    <p className="mt-6 text-center text-xs text-slate-500">
                        Pengunjung pameran? Pindai QR di stand untuk melihat dashboard.
                    </p>
                )}

                <p className="mt-6 text-center text-xs text-slate-500">
                    Prototipe proyek mahasiswa, bukan alat kesehatan bersertifikat.{' '}
                    <Link to="/#privasi" className="font-semibold underline underline-offset-2 hover:text-slate-800 dark:hover:text-slate-200">
                        Apa yang disimpan dan siapa yang melihat
                    </Link>
                </p>
            </div>
        </div>
    );
}
