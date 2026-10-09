import { useCallback, useEffect, useState } from 'react';
import { API_BASE } from '../config';

export default function Settings() {
    const [threshold, setThreshold] = useState(10);
    const [mode, setMode] = useState('');
    const [daftarMode, setDaftarMode] = useState([]);
    const [telegramSiap, setTelegramSiap] = useState(false);

    // Nilai yang sedang berlaku di backend. Dipakai untuk tahu apa yang benar-benar
    // berubah, supaya tombol Simpan tidak mengirim PUT mode yang tidak perlu --
    // pergantian mode mereset timer semua kamera, jadi jangan dilakukan sia-sia.
    const [tersimpan, setTersimpan] = useState({ threshold: 10, mode: '' });

    const [memuat, setMemuat] = useState(true);
    const [sibuk, setSibuk] = useState(false);
    const [kabar, setKabar] = useState(null);   // { tipe: 'ok' | 'galat', teks }

    const ambil = useCallback(async () => {
        try {
            const r = await fetch(`${API_BASE}/api/settings/`);
            if (!r.ok) throw new Error(String(r.status));
            const d = await r.json();
            setThreshold(d.fall_duration_threshold);
            setMode(d.detection_mode);
            setDaftarMode(d.available_modes || []);
            setTelegramSiap(d.telegram_configured);
            setTersimpan({ threshold: d.fall_duration_threshold, mode: d.detection_mode });
            setKabar(null);
        } catch {
            setKabar({
                tipe: 'galat',
                teks: `Tidak bisa menghubungi backend di ${API_BASE}. Jalankan run-backend.bat dulu.`,
            });
        } finally {
            setMemuat(false);
        }
    }, []);

    useEffect(() => { ambil(); }, [ambil]);

    const handleSave = async (e) => {
        e.preventDefault();
        setSibuk(true);
        setKabar(null);
        try {
            const dilakukan = [];

            if (Number(threshold) !== Number(tersimpan.threshold)) {
                const r = await fetch(`${API_BASE}/api/settings/threshold`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ fall_duration_threshold: Number(threshold) }),
                });
                if (!r.ok) throw new Error((await r.json()).detail || `threshold: ${r.status}`);
                dilakukan.push(`ambang jadi ${threshold} detik`);
            }

            if (mode !== tersimpan.mode) {
                const r = await fetch(`${API_BASE}/api/settings/mode`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ detection_mode: mode }),
                });
                if (!r.ok) throw new Error((await r.json()).detail || `mode: ${r.status}`);
                const nama = daftarMode.find((m) => m.id === mode)?.label || mode;
                dilakukan.push(`model jadi ${nama}, timer semua kamera direset`);
            }

            await ambil();
            setKabar({
                tipe: 'ok',
                teks: dilakukan.length ? `Tersimpan — ${dilakukan.join('; ')}.` : 'Tidak ada yang berubah.',
            });
        } catch (err) {
            setKabar({ tipe: 'galat', teks: `Gagal menyimpan: ${err.message}` });
        } finally {
            setSibuk(false);
        }
    };

    const ujiTelegram = async () => {
        setSibuk(true);
        setKabar(null);
        try {
            const r = await fetch(`${API_BASE}/api/settings/test-telegram`, { method: 'POST' });
            const d = await r.json();
            setKabar({ tipe: d.terkirim ? 'ok' : 'galat', teks: d.pesan });
            setTelegramSiap(d.dikonfigurasi);
        } catch {
            setKabar({ tipe: 'galat', teks: 'Tidak bisa menghubungi backend.' });
        } finally {
            setSibuk(false);
        }
    };

    const modeTerpilih = daftarMode.find((m) => m.id === mode);

    return (
        <div className="min-h-screen bg-slate-950 p-6 text-slate-300">
            <h1 className="text-2xl font-bold text-slate-100 mb-6">Pengaturan Sistem</h1>

            <form onSubmit={handleSave} className="max-w-xl bg-slate-900 p-6 rounded-xl border border-slate-800 space-y-6">
                <div>
                    <label className="block text-sm font-medium text-slate-400 mb-2">
                        Model Deteksi
                    </label>
                    <select
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
                        disabled={memuat || daftarMode.length === 0}
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                    >
                        {daftarMode.length === 0 && <option value="">Memuat…</option>}
                        {daftarMode.map((m) => (
                            <option key={m.id} value={m.id}>
                                {m.label}{m.recommended ? ' (disarankan)' : ''}
                            </option>
                        ))}
                    </select>
                    <p className="text-xs text-slate-500 mt-1">
                        {modeTerpilih
                            ? modeTerpilih.description
                            : 'Model yang dipakai untuk membaca postur dari setiap frame.'}
                    </p>
                    {mode !== tersimpan.mode && (
                        <p className="text-xs text-amber-400 mt-1">
                            Mengganti model akan mereset hitungan durasi di semua kamera.
                        </p>
                    )}
                </div>

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
                            disabled={memuat}
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
                        Notifikasi Telegram
                    </label>
                    <div className="flex items-center gap-3">
                        <span className={`inline-flex items-center gap-2 text-sm ${telegramSiap ? 'text-emerald-400' : 'text-slate-500'}`}>
                            <span className={`w-2 h-2 rounded-full ${telegramSiap ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                            {telegramSiap ? 'Terkonfigurasi' : 'Belum dikonfigurasi'}
                        </span>
                        <button
                            type="button"
                            onClick={ujiTelegram}
                            disabled={sibuk}
                            className="ml-auto bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-sm px-3 py-1.5 rounded-lg transition-colors"
                        >
                            Kirim pesan uji
                        </button>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Token bot dan chat ID diisi di <code className="text-slate-400">backend/.env</code>, bukan dari
                        halaman ini — keduanya rahasia dan tidak boleh dikirim lewat browser.
                    </p>
                </div>

                {kabar && (
                    <div className={`text-sm rounded-lg px-3 py-2 border ${kabar.tipe === 'ok'
                        ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                        : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
                        {kabar.teks}
                    </div>
                )}

                <button
                    type="submit"
                    disabled={sibuk || memuat}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition-colors"
                >
                    {sibuk ? 'Menyimpan…' : 'Simpan Pengaturan'}
                </button>
            </form>
        </div>
    );
}
