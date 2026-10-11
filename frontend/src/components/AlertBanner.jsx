import { useEffect, useRef, useState } from 'react';
import { BellRing, WifiOff } from 'lucide-react';
import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';

// Bunyi pendek tiga kali, tanpa berkas audio. Browser menolak bersuara sebelum
// ada interaksi di halaman; gagal diam-diam itu tidak apa-apa karena banner
// merahnya tetap tampil.
function bunyikan() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.35, 0.7].forEach((t) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'square';
            osc.frequency.value = 880;
            gain.gain.value = 0.15;
            osc.connect(gain).connect(ctx.destination);
            osc.start(ctx.currentTime + t);
            osc.stop(ctx.currentTime + t + 0.2);
        });
        setTimeout(() => ctx.close(), 1500);
    } catch { /* tanpa suara */ }
}

/**
 * Banner alarm jatuh, tampil di semua halaman dashboard.
 *
 * Alert datang dari backend lewat WebSocket begitu state machine mengonfirmasi
 * jatuh (timer mencapai ambang). Banner bertahan sampai perawat menandainya
 * ditangani, sehingga tidak terlewat kalau sedang membuka halaman lain.
 */
export default function AlertBanner() {
    const { alerts, connected, dismissAlert } = useLive();
    const [galat, setGalat] = useState('');
    const jumlahSebelumnya = useRef(0);

    useEffect(() => {
        if (alerts.length > jumlahSebelumnya.current) bunyikan();
        jumlahSebelumnya.current = alerts.length;
    }, [alerts.length]);

    const tandaiDitangani = async (id) => {
        setGalat('');
        try {
            const r = await fetch(`${API_BASE}/api/alerts/${id}/ack`, { method: 'PUT' });
            if (!r.ok) throw new Error(String(r.status));
            dismissAlert(id);
        } catch {
            setGalat('Gagal menandai alert ke backend. Alarm tetap ditampilkan; coba lagi.');
        }
    };

    return (
        <div className="sticky top-0 z-30">
            {!connected && (
                <div className="bg-amber-500/15 border-b border-amber-500/30 text-amber-600 dark:text-amber-400 text-xs px-4 py-2 flex items-center gap-2">
                    <WifiOff className="w-4 h-4 shrink-0" />
                    Terputus dari backend — alarm tidak akan tampil sampai tersambung kembali.
                </div>
            )}

            {alerts.map((a) => (
                <div
                    key={a.id}
                    className="bg-red-600 text-white px-4 py-3 border-b border-red-800 shadow-lg animate-pulse flex flex-col md:flex-row md:items-center justify-between gap-3"
                >
                    <div className="flex items-center gap-3">
                        <BellRing className="w-7 h-7 shrink-0 animate-bounce" />
                        <div>
                            <p className="font-bold">
                                {a.simulated ? 'SIMULASI' : 'DARURAT TERKONFIRMASI'}
                                : {a.camera_name || a.camera_id}
                            </p>
                            <p className="text-sm text-red-50">
                                {a.message}
                                {a.simulated && ' — dipicu tombol simulasi, bukan kejadian sungguhan.'}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={() => tandaiDitangani(a.id)}
                        className="bg-white text-red-700 hover:bg-red-50 px-4 py-2 rounded-lg text-sm font-semibold whitespace-nowrap"
                    >
                        Tandai Ditangani
                    </button>
                </div>
            ))}

            {galat && (
                <div className="bg-red-950 text-red-200 text-xs px-4 py-2">{galat}</div>
            )}
        </div>
    );
}
