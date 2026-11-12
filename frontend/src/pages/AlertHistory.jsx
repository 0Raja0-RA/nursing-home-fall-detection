import { useCallback, useEffect, useState } from 'react';
import { Clock, MapPin, AlertTriangle, CheckCircle2, Send, SendHorizonal, FlaskConical, Pencil, Plus } from 'lucide-react';
import { API_BASE } from '../config';

export default function AlertHistory() {
    const [history, setHistory] = useState([]);
    const [galat, setGalat] = useState('');
    // Catatan yang sedang disunting. Disimpan terpisah dari `history` supaya
    // penyegaran otomatis tiap 5 detik tidak menghapus apa yang sedang diketik.
    const [sunting, setSunting] = useState(null);   // { id, teks } | null
    const [menyimpan, setMenyimpan] = useState(false);

    const ambil = useCallback(async () => {
        try {
            const r = await fetch(`${API_BASE}/api/alerts/`);
            if (!r.ok) throw new Error(String(r.status));
            setHistory(await r.json());
            setGalat('');
        } catch {
            setGalat(`Tidak bisa menghubungi backend di ${API_BASE}. Jalankan run-backend.bat dulu.`);
        }
    }, []);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
        const t = setInterval(ambil, 5000);
        return () => clearInterval(t);
    }, [ambil]);

    const tandaiDitangani = async (id) => {
        try {
            await fetch(`${API_BASE}/api/alerts/${id}/ack`, { method: 'PUT' });
            await ambil();
        } catch {
            setGalat('Gagal menandai alert. Periksa koneksi ke backend.');
        }
    };

    const simpanCatatan = async () => {
        if (!sunting) return;
        setMenyimpan(true);
        try {
            const r = await fetch(`${API_BASE}/api/alerts/${sunting.id}/note`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: sunting.teks }),
            });
            if (!r.ok) throw new Error(String(r.status));
            setSunting(null);
            await ambil();
        } catch {
            setGalat('Gagal menyimpan catatan. Periksa koneksi ke backend; tulisanmu masih ada.');
        } finally {
            setMenyimpan(false);
        }
    };

    const waktuLokal = (iso) => {
        // Backend menyimpan waktu UTC tanpa zona, jadi penandanya ditambahkan di sini
        // supaya browser menampilkannya dalam waktu setempat, bukan mundur 7 jam.
        const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
        return isNaN(d) ? iso : d.toLocaleString('id-ID');
    };

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0">
            <h1 className="text-xl md:text-2xl font-bold mb-6">Riwayat Insiden</h1>

            {galat && (
                <div className="mb-6 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400 text-sm">
                    {galat}
                </div>
            )}

            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 text-sm uppercase tracking-wider">
                                <th className="p-4 font-medium">Waktu Kejadian</th>
                                <th className="p-4 font-medium">Lokasi Kamera</th>
                                <th className="p-4 font-medium">Status Validasi</th>
                                <th className="p-4 font-medium">Notifikasi</th>
                                <th className="p-4 font-medium">Catatan Caregiver</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-800/50">
                            {history.length === 0 && !galat && (
                                <tr>
                                    <td colSpan={5} className="p-8 text-center text-sm text-slate-500">
                                        Belum ada insiden tercatat.
                                    </td>
                                </tr>
                            )}
                            {history.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                                    <td className="p-4">
                                        <div className="flex items-center gap-2">
                                            <Clock className="w-4 h-4 text-slate-500" />
                                            {waktuLokal(item.created_at)}
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        <div className="flex items-center gap-2">
                                            <MapPin className="w-4 h-4 text-slate-500" />
                                            {item.camera_id}
                                            {item.simulated && (
                                                <span
                                                    title="Dipicu tombol simulasi, bukan deteksi sungguhan"
                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20"
                                                >
                                                    <FlaskConical className="w-3 h-3" /> Simulasi
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        {item.acknowledged ? (
                                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                                                <CheckCircle2 className="w-3.5 h-3.5" /> Sudah Ditangani
                                            </span>
                                        ) : (
                                            <button
                                                onClick={() => tandaiDitangani(item.id)}
                                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                                            >
                                                <AlertTriangle className="w-3.5 h-3.5" /> Tandai Ditangani
                                            </button>
                                        )}
                                    </td>
                                    <td className="p-4">
                                        {item.notified ? (
                                            <span
                                                title="Notifikasi Telegram terkirim"
                                                className="inline-flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400"
                                            >
                                                <Send className="w-3.5 h-3.5" /> Terkirim
                                            </span>
                                        ) : (
                                            <span
                                                title="Telegram gagal atau belum dikonfigurasi. Alert tetap tersimpan."
                                                className="inline-flex items-center gap-1.5 text-xs text-slate-500"
                                            >
                                                <SendHorizonal className="w-3.5 h-3.5" /> Tidak terkirim
                                            </span>
                                        )}
                                    </td>
                                    <td className="p-4 text-sm min-w-[16rem]">
                                        {sunting?.id === item.id ? (
                                            <form
                                                onSubmit={(e) => { e.preventDefault(); simpanCatatan(); }}
                                                className="flex flex-col gap-2"
                                            >
                                                <textarea
                                                    autoFocus
                                                    rows={2}
                                                    maxLength={500}
                                                    value={sunting.teks}
                                                    onChange={(e) => setSunting({ id: item.id, teks: e.target.value })}
                                                    onKeyDown={(e) => {
                                                        if (e.key === 'Escape') setSunting(null);
                                                        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); simpanCatatan(); }
                                                    }}
                                                    placeholder="Tindakan yang diambil..."
                                                    className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg p-2 text-slate-800 dark:text-slate-200 text-sm focus:outline-none focus:border-blue-500 resize-y"
                                                />
                                                <div className="flex gap-2">
                                                    <button type="submit" disabled={menyimpan}
                                                        className="px-3 py-1 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white">
                                                        {menyimpan ? 'Menyimpan…' : 'Simpan'}
                                                    </button>
                                                    <button type="button" onClick={() => setSunting(null)}
                                                        className="px-3 py-1 rounded-lg text-xs font-medium bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300">
                                                        Batal
                                                    </button>
                                                </div>
                                            </form>
                                        ) : item.caregiver_note ? (
                                            <div className="flex items-start gap-2 group">
                                                <p className="text-slate-800 dark:text-slate-200 whitespace-pre-wrap break-words">{item.caregiver_note}</p>
                                                <button
                                                    onClick={() => setSunting({ id: item.id, teks: item.caregiver_note })}
                                                    title="Ubah catatan"
                                                    aria-label="Ubah catatan"
                                                    className="shrink-0 p-1 rounded text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                                                >
                                                    <Pencil className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={() => setSunting({ id: item.id, teks: '' })}
                                                className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                                            >
                                                <Plus className="w-3.5 h-3.5" /> Tambah catatan
                                            </button>
                                        )}
                                        {/* Pesan sistem tetap ditampilkan: hanya di sini durasi jatuhnya tercatat. */}
                                        <p className="mt-1 text-xs text-slate-500">{item.message}</p>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
