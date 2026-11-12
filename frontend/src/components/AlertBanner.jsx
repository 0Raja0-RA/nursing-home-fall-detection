import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellOff, FlaskConical, TriangleAlert, Video, VolumeX, WifiOff } from 'lucide-react';
import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';
import { aktifkanSuara, bunyikan, useStatusSuara } from '../hooks/useAlarmSound';
import { jamDari } from '../statusKamera';

const JUDUL_HALAMAN = 'FallDetect';
const BISU_MENIT = 5;
const ULANG_BUNYI_MS = 4000;

/** Jam kejadian. Backend mengirim waktu UTC tanpa zona, jadi penandanya ditambahkan. */
function jamKejadian(iso) {
    if (!iso) return '';
    const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`);
    return isNaN(d) ? '' : jamDari(d.getTime());
}

/**
 * Banner alarm jatuh, tampil di semua halaman dashboard.
 *
 * Alert datang dari backend lewat WebSocket begitu state machine mengonfirmasi
 * jatuh (timer mencapai ambang). Banner bertahan sampai perawat menandainya
 * ditangani, sehingga tidak terlewat kalau sedang membuka halaman lain.
 *
 * Banner sengaja diam: teks dan tombol yang berdenyut sulit dibaca dan tampak
 * nonaktif. Perhatian ditarik lewat warna, bunyi yang berulang, dan judul tab.
 */
export default function AlertBanner() {
    const { alerts, connected, dismissAlert } = useLive();
    const suara = useStatusSuara();
    const navigate = useNavigate();
    const [galat, setGalat] = useState('');
    // Catatan per alert, karena beberapa alarm bisa tampil bersamaan.
    const [catatan, setCatatan] = useState({});
    // Bisu hanya berlaku untuk alarm yang sedang tampil: alarm baru tetap berbunyi.
    const [bisu, setBisu] = useState(null);   // { sampai: ms epoch, ids: number[] }

    // Bunyi berulang sampai alarm ditandai ditangani atau dibisukan.
    useEffect(() => {
        if (!alerts.length || suara !== 'aktif') return undefined;
        const dering = () => {
            const berbunyi = alerts.filter((a) => !bisu?.ids.includes(a.id));
            if (berbunyi.length) bunyikan(berbunyi.every((a) => a.simulated));
        };
        dering();
        const t = setInterval(dering, ULANG_BUNYI_MS);
        return () => clearInterval(t);
    }, [alerts, bisu, suara]);

    // Bisu habis dengan sendirinya.
    useEffect(() => {
        if (!bisu) return undefined;
        const t = setTimeout(() => setBisu(null), Math.max(0, bisu.sampai - Date.now()));
        return () => clearTimeout(t);
    }, [bisu]);

    // Judul tab ikut memberi tahu perawat yang sedang membuka tab lain.
    useEffect(() => {
        if (!alerts.length) {
            document.title = JUDUL_HALAMAN;
            return undefined;
        }
        const a = alerts[0];
        document.title = `(${alerts.length}) ${a.simulated ? 'Latihan' : 'Kemungkinan jatuh'}, ${a.camera_name || a.camera_id}`;
        return () => { document.title = JUDUL_HALAMAN; };
    }, [alerts]);

    const tandaiDitangani = async (id) => {
        setGalat('');
        try {
            // Catatan opsional: dalam keadaan darurat perawat boleh menandai dulu,
            // lalu menulis catatannya belakangan dari halaman Riwayat Insiden.
            const r = await fetch(`${API_BASE}/api/alerts/${id}/ack`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: catatan[id] || null }),
            });
            if (!r.ok) throw new Error(String(r.status));
            dismissAlert(id);
            setCatatan((c) => {
                const sisa = { ...c };
                delete sisa[id];
                return sisa;
            });
        } catch {
            setGalat('Gagal menandai alert ke backend. Alarm tetap ditampilkan; coba lagi.');
        }
    };

    const bisukan = () => setBisu({ sampai: Date.now() + BISU_MENIT * 60_000, ids: alerts.map((a) => a.id) });

    return (
        <div className="sticky top-0 z-30">
            {!connected && (
                <div role="status" className="bg-amber-500/15 border-b border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs px-4 py-2 flex items-center gap-2">
                    <WifiOff className="w-4 h-4 shrink-0" aria-hidden="true" />
                    Terputus dari backend — alarm tidak akan tampil sampai tersambung kembali.
                </div>
            )}

            {/* Browser memblokir suara sampai ada klik. Tanpa pemberitahuan ini, alarm
                bisa muncul tanpa bunyi dan tidak ada yang tahu. */}
            {suara === 'belum' && (
                <div role="status" className="bg-amber-500/15 border-b border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs px-4 py-2 flex items-center gap-2">
                    <VolumeX className="w-4 h-4 shrink-0" aria-hidden="true" />
                    <span>Suara alarm belum aktif. Browser menunggu klik pertama di halaman ini.</span>
                    <button type="button" onClick={aktifkanSuara} className="ml-auto font-semibold underline underline-offset-2 whitespace-nowrap">
                        Aktifkan suara
                    </button>
                </div>
            )}

            {alerts.map((a) => {
                const nama = a.camera_name || a.camera_id;
                const latihan = Boolean(a.simulated);
                // Tanpa membaca jam di sini: bisu dihapus oleh timer begitu waktunya habis.
                const dibisukan = Boolean(bisu?.ids.includes(a.id));
                const Ikon = latihan ? FlaskConical : TriangleAlert;
                return (
                    <div
                        key={a.id}
                        role="alert"
                        className={`${latihan ? 'bg-blue-700 border-blue-900' : 'bg-red-700 border-red-900'} text-white px-4 py-3 border-b flex flex-col xl:flex-row xl:items-center gap-3`}
                    >
                        <div className="flex items-start gap-3 min-w-0 flex-1">
                            <Ikon className="w-6 h-6 shrink-0 mt-0.5" aria-hidden="true" />
                            <div className="min-w-0">
                                <p className="font-semibold text-base">
                                    {latihan ? `Latihan, ${nama}` : `Kemungkinan jatuh, ${nama}`}
                                </p>
                                <p className="text-sm text-white/85 tabular-nums">
                                    {latihan && 'Bukan kejadian sungguhan. '}
                                    Terbaca berbaring {Math.round(Number(a.fall_duration) || 0)} detik · {jamKejadian(a.created_at)}
                                </p>
                            </div>
                        </div>
                        <form
                            onSubmit={(e) => { e.preventDefault(); tandaiDitangani(a.id); }}
                            className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 w-full xl:w-auto"
                        >
                            <button
                                type="button"
                                onClick={() => navigate('/dashboard', { state: { fokus: a.camera_id } })}
                                className="min-h-11 px-4 rounded-lg text-sm font-semibold border border-white/70 hover:bg-white/10 inline-flex items-center justify-center gap-2 whitespace-nowrap"
                            >
                                <Video className="w-4 h-4" aria-hidden="true" /> Lihat kamera
                            </button>
                            <input
                                type="text"
                                value={catatan[a.id] || ''}
                                onChange={(e) => setCatatan((c) => ({ ...c, [a.id]: e.target.value }))}
                                maxLength={500}
                                placeholder="Catatan tindakan (opsional)"
                                aria-label="Catatan tindakan perawat"
                                className="min-h-11 bg-white text-slate-800 placeholder:text-slate-500 rounded-lg px-3 text-sm sm:w-64 focus:outline-none focus:ring-2 focus:ring-white/70"
                            />
                            <button
                                type="submit"
                                className={`min-h-11 bg-white ${latihan ? 'text-blue-800' : 'text-red-800'} hover:bg-slate-100 px-4 rounded-lg text-sm font-semibold whitespace-nowrap`}
                            >
                                Tandai Ditangani
                            </button>
                            {dibisukan ? (
                                <span className="text-xs text-white/85 px-1 whitespace-nowrap tabular-nums">
                                    Dibisukan sampai {jamDari(bisu.sampai)}
                                </span>
                            ) : (
                                <button
                                    type="button"
                                    onClick={bisukan}
                                    className="min-h-11 px-3 rounded-lg text-sm font-medium hover:bg-white/10 inline-flex items-center justify-center gap-2 whitespace-nowrap"
                                >
                                    <BellOff className="w-4 h-4" aria-hidden="true" /> Bisukan {BISU_MENIT} menit
                                </button>
                            )}
                        </form>
                    </div>
                );
            })}

            {galat && (
                <div role="alert" className="bg-red-950 text-red-200 text-xs px-4 py-2">{galat}</div>
            )}
        </div>
    );
}
