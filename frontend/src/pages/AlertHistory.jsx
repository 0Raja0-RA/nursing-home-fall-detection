import { useCallback, useEffect, useState } from 'react';
import { Clock, MapPin, AlertTriangle, CheckCircle2, Send, SendHorizonal, FlaskConical } from 'lucide-react';
import { API_BASE } from '../config';

export default function AlertHistory() {
    const [history, setHistory] = useState([]);
    const [galat, setGalat] = useState('');

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

    const waktuLokal = (iso) => {
        // Backend menyimpan waktu UTC tanpa zona, jadi penandanya ditambahkan di sini
        // supaya browser menampilkannya dalam waktu setempat, bukan mundur 7 jam.
        const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
        return isNaN(d) ? iso : d.toLocaleString('id-ID');
    };

    return (
        <div className="min-h-screen bg-slate-950 p-6 text-slate-300">
            <h1 className="text-2xl font-bold text-slate-100 mb-6">Riwayat Insiden</h1>

            {galat && (
                <div className="mb-6 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 text-sm">
                    {galat}
                </div>
            )}

            <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 text-sm uppercase tracking-wider">
                                <th className="p-4 font-medium">Waktu Kejadian</th>
                                <th className="p-4 font-medium">Lokasi Kamera</th>
                                <th className="p-4 font-medium">Status Validasi</th>
                                <th className="p-4 font-medium">Notifikasi</th>
                                <th className="p-4 font-medium">Catatan Caregiver</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                            {history.length === 0 && !galat && (
                                <tr>
                                    <td colSpan={5} className="p-8 text-center text-sm text-slate-500">
                                        Belum ada insiden tercatat.
                                    </td>
                                </tr>
                            )}
                            {history.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-800/50 transition-colors">
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
                                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                                >
                                                    <FlaskConical className="w-3 h-3" /> Simulasi
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        {item.acknowledged ? (
                                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                                <CheckCircle2 className="w-3.5 h-3.5" /> Sudah Ditangani
                                            </span>
                                        ) : (
                                            <button
                                                onClick={() => tandaiDitangani(item.id)}
                                                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                                            >
                                                <AlertTriangle className="w-3.5 h-3.5" /> Tandai Ditangani
                                            </button>
                                        )}
                                    </td>
                                    <td className="p-4">
                                        {item.notified ? (
                                            <span
                                                title="Notifikasi Telegram terkirim"
                                                className="inline-flex items-center gap-1.5 text-xs text-emerald-400"
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
                                    <td className="p-4 text-sm text-slate-400">{item.message}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
