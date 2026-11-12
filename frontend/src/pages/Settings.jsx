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

    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
    }, [ambil]);

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
        <div className="p-4 md:p-8 w-full max-w-full min-w-0">
            <h1 className="text-xl md:text-2xl font-bold mb-6">Pengaturan</h1>

            <form onSubmit={handleSave} className="max-w-xl bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
                <div>
                    <label htmlFor="pilih-model" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Model deteksi
                    </label>
                    <select
                        id="pilih-model"
                        value={mode}
                        onChange={(e) => setMode(e.target.value)}
                        disabled={memuat || daftarMode.length === 0}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg p-2.5 text-slate-800 dark:text-slate-200 focus:outline-none focus:border-blue-500 disabled:opacity-50"
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
                        <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
                            Mengganti model akan mereset hitungan durasi di semua kamera.
                        </p>
                    )}
                </div>

                <div>
                    <label htmlFor="ambang" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Tunggu sebelum memberi alarm
                    </label>
                    <div className="flex items-center gap-4">
                        <input
                            id="ambang"
                            type="range"
                            min="3" max="30"
                            value={threshold}
                            onChange={(e) => setThreshold(e.target.value)}
                            disabled={memuat}
                            className="w-full accent-blue-500"
                        />
                        <span className="text-lg font-bold text-slate-800 dark:text-slate-200 w-24 text-right tabular-nums">{threshold} detik</span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Alarm berbunyi setelah seseorang terbaca berbaring selama {threshold} detik. Lebih pendek,
                        lebih banyak alarm palsu. Lebih panjang, pertolongan bisa terlambat.
                    </p>
                </div>

                <div>
                    <p className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                        Notifikasi Telegram
                    </p>
                    <div className="flex items-center gap-3">
                        <span className={`inline-flex items-center gap-2 text-sm ${telegramSiap ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-500'}`}>
                            <span className={`w-2 h-2 rounded-full ${telegramSiap ? 'bg-emerald-500' : 'bg-slate-400 dark:bg-slate-600'}`} />
                            {telegramSiap ? 'Terkonfigurasi' : 'Belum dikonfigurasi'}
                        </span>
                        <button
                            type="button"
                            onClick={ujiTelegram}
                            disabled={sibuk}
                            className="ml-auto bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 disabled:opacity-50 text-slate-800 dark:text-slate-200 text-sm px-3 py-1.5 rounded-lg transition-colors"
                        >
                            Kirim pesan uji
                        </button>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Token bot dan ID chat Telegram diatur di server oleh pengelola sistem, bukan dari halaman
                        ini, karena keduanya rahasia.
                    </p>
                </div>

                {kabar && (
                    <div role="status" className={`text-sm rounded-lg px-3 py-2 border ${kabar.tipe === 'ok'
                        ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
                        : 'bg-red-500/10 border-red-500/20 text-red-700 dark:text-red-400'}`}>
                        {kabar.teks}
                    </div>
                )}

                <button
                    type="submit"
                    disabled={sibuk || memuat}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition-colors"
                >
                    {sibuk ? 'Menyimpan…' : 'Simpan pengaturan'}
                </button>
            </form>
        </div>
    );
}
