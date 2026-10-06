import { useState } from 'react';

export default function Settings() {
    const [threshold, setThreshold] = useState(10);
    const [telegramId, setTelegramId] = useState('');

    const handleSave = (e) => {
        e.preventDefault();
        // Logic untuk mengirim update settings via REST API (axios/fetch) ke backend[cite: 1]
        console.log('Tersimpan:', { threshold, telegramId });
    };

    return (
        <div className="min-h-screen bg-slate-950 p-6 text-slate-300">
            <h1 className="text-2xl font-bold text-slate-100 mb-6">Pengaturan Sistem</h1>

            <form onSubmit={handleSave} className="max-w-xl bg-slate-900 p-6 rounded-xl border border-slate-800 space-y-6">
                <div>
                    <label className="block text-sm font-medium text-slate-400 mb-2">
                        Threshold Durasi Jatuh (Detik)
                    </label>
                    <div className="flex items-center gap-4">
                        <input
                            type="range"
                            min="3" max="30"
                            value={threshold}
                            onChange={(e) => setThreshold(e.target.value)}
                            className="w-full accent-blue-500"
                        />
                        <span className="text-lg font-bold text-slate-200 w-12">{threshold}s</span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Waktu tunggu sebelum model mengirim notifikasi darurat saat mendeteksi status "lying_on_ground".
                    </p>
                </div>

                <div>
                    <label className="block text-sm font-medium text-slate-400 mb-2">
                        ID Bot Telegram
                    </label>
                    <input
                        type="text"
                        value={telegramId}
                        onChange={(e) => setTelegramId(e.target.value)}
                        placeholder="Masukkan Chat ID Telegram"
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500"
                    />
                </div>

                <button type="submit" className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg transition-colors">
                    Simpan Pengaturan
                </button>
            </form>
        </div>
    );
}