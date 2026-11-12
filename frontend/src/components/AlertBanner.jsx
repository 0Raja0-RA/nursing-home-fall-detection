import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellOff, CheckCircle2, FlaskConical, Footprints, TriangleAlert, Video, VolumeX, WifiOff } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { usePengunjung } from '../context/auth';
import { useLive } from '../context/LiveContext';
import { aktifkanSuara, bunyikan, useStatusSuara } from '../hooks/useAlarmSound';
import { jamDari } from '../statusKamera';
import { msDari } from '../waktu';
import FormPenutupan from './FormPenutupan';

const JUDUL_HALAMAN = 'FallDetect';
const BISU_MENIT = 5;
const ULANG_BUNYI_MS = 4000;

const jam = (iso) => {
    const ms = msDari(iso);
    return Number.isFinite(ms) ? jamDari(ms) : '';
};

// Warna mengikuti aturan tunggal: merah hanya untuk alarm yang belum direspons,
// amber untuk alarm yang sudah ada yang menuju lokasi, biru untuk latihan.
const GAYA = {
    merah: {
        kotak: 'bg-red-700 text-white border-red-900',
        utama: 'bg-white text-red-800 hover:bg-red-50',
        garis: 'border-white/70 hover:bg-white/10',
        hantu: 'hover:bg-white/10',
        redup: 'text-white/85',
    },
    amber: {
        kotak: 'bg-amber-400 text-slate-950 border-amber-600',
        utama: 'bg-slate-950 text-white hover:bg-slate-800',
        garis: 'border-slate-950/50 hover:bg-black/10',
        hantu: 'hover:bg-black/10',
        redup: 'text-slate-900',
    },
    biru: {
        kotak: 'bg-blue-700 text-white border-blue-900',
        utama: 'bg-white text-blue-800 hover:bg-blue-50',
        garis: 'border-white/70 hover:bg-white/10',
        hantu: 'hover:bg-white/10',
        redup: 'text-white/85',
    },
};

/**
 * Banner alarm jatuh, tampil di semua halaman dashboard.
 *
 * Alur penanganan dipecah dua langkah, mengikuti pola sistem panggilan perawat:
 *   1. "Saya ke sana": nama penekan tampil di semua dashboard dan di Telegram,
 *      banner berubah amber, dan bunyi berhenti, supaya perawat lain tidak
 *      saling menunggu atau sama-sama berangkat.
 *   2. "Tandai Ditangani" setelah penghuni ditolong, dengan putusan: jatuh
 *      sungguhan, alarm palsu (beralasan), atau belum yakin.
 *
 * Banner sengaja diam: teks dan tombol yang berdenyut sulit dibaca dan tampak
 * nonaktif. Perhatian ditarik lewat warna, bunyi yang berulang, dan judul tab.
 */
export default function AlertBanner() {
    const { alerts, connected, dismissAlert, perbaruiAlert } = useLive();
    const suara = useStatusSuara();
    // Pengunjung pameran hanya melihat: tanpa tombol aksi, dan HP-nya tidak ikut
    // berbunyi di tengah keramaian stand.
    const pengunjung = usePengunjung();
    const navigate = useNavigate();
    const [galat, setGalat] = useState('');
    const [menutup, setMenutup] = useState(null);   // id alert yang formulir penutupannya terbuka
    const [mengklaim, setMengklaim] = useState(null);
    // Bisu hanya berlaku untuk alarm yang sedang tampil: alarm baru tetap berbunyi.
    const [bisu, setBisu] = useState(null);   // { sampai: ms epoch, ids: number[] }

    // Bunyi berulang sampai ada yang menekan "Saya ke sana", atau dibisukan.
    useEffect(() => {
        if (pengunjung || suara !== 'aktif') return undefined;
        const dering = () => {
            const berbunyi = alerts.filter((a) => !a.claimed_by && !bisu?.ids.includes(a.id));
            if (berbunyi.length) bunyikan(berbunyi.every((a) => a.simulated));
        };
        if (!alerts.some((a) => !a.claimed_by)) return undefined;
        dering();
        const t = setInterval(dering, ULANG_BUNYI_MS);
        return () => clearInterval(t);
    }, [alerts, bisu, suara, pengunjung]);

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
        const a = alerts.find((x) => !x.claimed_by) || alerts[0];
        const jenis = a.simulated ? 'Latihan' : a.claimed_by ? 'Ditangani' : 'Kemungkinan jatuh';
        document.title = `(${alerts.length}) ${jenis}, ${a.camera_name || a.camera_id}`;
        return () => { document.title = JUDUL_HALAMAN; };
    }, [alerts]);

    const klaim = async (id) => {
        setGalat('');
        setMengklaim(id);
        try {
            const r = await api(`/api/alerts/${id}/claim`, { method: 'PUT' });
            if (r.ok) {
                perbaruiAlert(await r.json());
            } else {
                // 409: sudah diklaim orang lain. Namanya ada di pesan backend, dan
                // banner ikut berubah lewat siaran WebSocket.
                setGalat(await bacaGalat(r));
            }
        } catch {
            setGalat(`${PESAN_TERPUTUS} Alarm tetap ditampilkan; coba lagi.`);
        } finally {
            setMengklaim(null);
        }
    };

    const bisukan = () => setBisu({ sampai: Date.now() + BISU_MENIT * 60_000, ids: alerts.map((a) => a.id) });

    const tombol = 'min-h-11 px-3 sm:px-4 rounded-lg text-sm font-semibold inline-flex items-center justify-center gap-1.5 sm:gap-2 whitespace-nowrap disabled:opacity-60';
    // Di HP dua tombol utama berbagi satu baris. Ikonnya baru tampil mulai lebar 400 px,
    // supaya "Tandai Ditangani" tetap muat di HP 360 px tanpa terpotong.
    const lebarRata = 'flex-1 min-w-0 sm:flex-none';
    const ikonKecil = 'w-4 h-4 hidden min-[400px]:block';

    return (
        // Di HP menempel tepat di bawah bilah atas (tinggi 3.5rem); di layar lebar di paling atas.
        <div id="banner-alarm" className="sticky top-14 md:top-0 z-20">
            {!connected && (
                <div role="status" className="bg-amber-50 dark:bg-amber-950 border-b border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs px-4 py-2 flex items-center gap-2">
                    <WifiOff className="w-4 h-4 shrink-0" aria-hidden="true" />
                    Terputus dari backend — alarm tidak akan tampil sampai tersambung kembali.
                </div>
            )}

            {/* Browser memblokir suara sampai ada klik. Tanpa pemberitahuan ini, alarm
                bisa muncul tanpa bunyi dan tidak ada yang tahu. */}
            {suara === 'belum' && !pengunjung && (
                <div role="status" className="bg-amber-50 dark:bg-amber-950 border-b border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs px-4 py-2 flex items-center gap-2">
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
                const diklaim = Boolean(a.claimed_by);
                const gaya = GAYA[latihan ? 'biru' : diklaim ? 'amber' : 'merah'];
                // Tanpa membaca jam di sini: bisu dihapus oleh timer begitu waktunya habis.
                const dibisukan = Boolean(bisu?.ids.includes(a.id));
                const Ikon = latihan ? FlaskConical : diklaim ? Footprints : TriangleAlert;
                const durasi = `Terbaca berbaring ${Math.round(Number(a.fall_duration) || 0)} detik · ${jam(a.created_at)}`;

                return (
                    <div
                        key={a.id}
                        role={diklaim ? 'status' : 'alert'}
                        className={`${gaya.kotak} px-4 py-3 border-b flex flex-col gap-3`}
                    >
                        <div className="flex flex-col xl:flex-row xl:items-center gap-3">
                            <div className="flex items-start gap-3 min-w-0 flex-1">
                                <Ikon className="w-6 h-6 shrink-0 mt-0.5" aria-hidden="true" />
                                <div className="min-w-0">
                                    <p className="font-semibold text-base">
                                        {latihan ? `Latihan, ${nama}` : `Kemungkinan jatuh, ${nama}`}
                                    </p>
                                    <p className={`text-sm tabular-nums ${gaya.redup}`}>
                                        {diklaim
                                            ? <><b className="font-semibold">{a.claimed_by}</b> menuju lokasi sejak {jam(a.claimed_at)} · {durasi}</>
                                            : <>{latihan && 'Bukan kejadian sungguhan. '}{durasi} · Belum ada yang merespons</>}
                                    </p>
                                </div>
                            </div>

                            {menutup !== a.id && (
                                <div className="flex items-center gap-2 w-full xl:w-auto">
                                    {pengunjung ? null : diklaim ? (
                                        <button type="button" onClick={() => setMenutup(a.id)} className={`${tombol} ${lebarRata} ${gaya.utama}`}>
                                            <CheckCircle2 className={ikonKecil} aria-hidden="true" /> Tandai Ditangani
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => klaim(a.id)}
                                            disabled={mengklaim === a.id}
                                            className={`${tombol} ${lebarRata} ${gaya.utama}`}
                                        >
                                            <Footprints className={ikonKecil} aria-hidden="true" />
                                            {mengklaim === a.id ? 'Mencatat…' : 'Saya ke sana'}
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => navigate('/dashboard', { state: { fokus: a.camera_id } })}
                                        className={`${tombol} ${lebarRata} border ${gaya.garis}`}
                                    >
                                        <Video className={ikonKecil} aria-hidden="true" /> Lihat kamera
                                    </button>
                                    {!diklaim && !pengunjung && (dibisukan ? (
                                        <span className={`shrink-0 text-xs px-1 whitespace-nowrap tabular-nums ${gaya.redup}`}>
                                            Dibisukan<span className="hidden sm:inline"> sampai</span> {jamDari(bisu.sampai)}
                                        </span>
                                    ) : (
                                        // Di HP hanya ikon; namanya tetap terbaca lewat aria-label dan tooltip.
                                        <button
                                            type="button"
                                            onClick={bisukan}
                                            aria-label={`Bisukan ${BISU_MENIT} menit`}
                                            title={`Bisukan ${BISU_MENIT} menit`}
                                            className={`${tombol} shrink-0 min-w-11 px-2.5 sm:px-3 font-medium ${gaya.hantu}`}
                                        >
                                            <BellOff className="w-4 h-4" aria-hidden="true" />
                                            <span className="hidden sm:inline">Bisukan {BISU_MENIT} menit</span>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>

                        {menutup === a.id && (
                            <FormPenutupan
                                alert={a}
                                onBatal={() => setMenutup(null)}
                                onSelesai={() => {
                                    setMenutup(null);
                                    dismissAlert(a.id);
                                }}
                            />
                        )}
                    </div>
                );
            })}

            {galat && (
                <div role="alert" className="bg-red-950 text-red-100 text-sm px-4 py-2 flex items-center gap-3">
                    <span className="flex-1">{galat}</span>
                    <button type="button" onClick={() => setGalat('')} className="text-xs underline underline-offset-2">Tutup</button>
                </div>
            )}
        </div>
    );
}
