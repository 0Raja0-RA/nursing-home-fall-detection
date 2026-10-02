import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Lock, LogIn, ArrowLeft, AlertCircle } from 'lucide-react';

export default function Login() {
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [errorMsg, setErrorMsg] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    // Akun pakem untuk simulasi
    const VALID_EMAIL = 'caregiver@panti.com';
    const VALID_PASSWORD = '123';

    const handleLogin = (e) => {
        e.preventDefault();
        setErrorMsg('');
        setIsLoading(true);

        setTimeout(() => {
            if (email === VALID_EMAIL && password === VALID_PASSWORD) {
                setIsLoading(false);
                navigate('/dashboard');
            } else {
                setIsLoading(false);
                setErrorMsg('Email atau password salah! Gunakan: caregiver@panti.com | 123');
            }
        }, 800);
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
            <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 p-8">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-blue-600 rounded-2xl mx-auto flex items-center justify-center text-white font-bold text-2xl mb-4 shadow-lg shadow-blue-600/30">
                        FD
                    </div>
                    <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Login Caregiver</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2">
                        Masuk untuk mengakses sistem pemantauan panti jompo.
                    </p>
                </div>

                {/* Informasi Akun Simulasi */}
                <div className="mb-6 p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-xs text-blue-600 dark:text-blue-400">
                    <p className="font-semibold mb-1">💡 Info Akun Simulasi:</p>
                    <p>Email: <span className="font-mono font-bold">caregiver@panti.com</span></p>
                    <p>Password: <span className="font-mono font-bold">123</span></p>
                </div>

                {errorMsg && (
                    <div className="mb-6 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-xs text-red-600 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        <span>{errorMsg}</span>
                    </div>
                )}

                <form onSubmit={handleLogin} className="space-y-6">
                    {/* Input Email */}
                    <div>
                        <label className="block text-sm font-semibold text-slate-600 dark:text-slate-300 mb-2">
                            Email
                        </label>
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <Mail className="w-5 h-5 text-slate-400" />
                            </div>
                            <input
                                type="email"
                                required
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl py-3 pl-11 pr-4 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-sm"
                                placeholder="caregiver@panti.com"
                            />
                        </div>
                    </div>

                    {/* Input Password */}
                    <div>
                        <label className="block text-sm font-semibold text-slate-600 dark:text-slate-300 mb-2">
                            Password
                        </label>
                        <div className="relative">
                            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                                <Lock className="w-5 h-5 text-slate-400" />
                            </div>
                            <input
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl py-3 pl-11 pr-4 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-sm"
                                placeholder="••••••••"
                            />
                        </div>
                    </div>

                    {/* Tombol Submit */}
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl shadow-lg shadow-blue-600/30 transition-all flex items-center justify-center gap-2 disabled:opacity-70 text-sm"
                    >
                        {isLoading ? (
                            <span className="animate-pulse">Memeriksa...</span>
                        ) : (
                            <>
                                <LogIn className="w-5 h-5" /> Masuk ke Dashboard
                            </>
                        )}
                    </button>
                </form>
            </div>
        </div>
    );
}