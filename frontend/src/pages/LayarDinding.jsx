import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Clock, Expand, FlaskConical, Footprints, TriangleAlert, VideoOff, WifiOff } from 'lucide-react';
import { api } from '../api';
import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';
import StatusKamera from '../components/StatusKamera';
import StreamImg from '../components/StreamImg';
import logoKecil from '../assets/logo-falldetect-kecil.svg';
import { bacaStatus, jamDari, mmss } from '../statusKamera';
import { durasiTeks, msDari, useJam } from '../waktu';

const MAKS_ALARM = 4;

// Warna ruang di denah mengikuti aturan warna yang sama dengan banner dan tile.
const WARNA_RUANG = {
    jatuh: 'bg-red-700 border-red-500 text-white',
    diklaim: 'bg-amber-400 border-amber-300 text-slate-950',
    biru: 'bg-blue-950 border-blue-500 text-blue-100',
    terputus: 'border-dashed border-slate-500 text-slate-300',
    tenang: 'bg-slate-900 border-slate-700 text-slate-200',
};

/**
 * Layar dinding: tampilan baca-saja untuk layar besar di ruang jaga.
 *
 * Semua kamera tampil sekaligus, tanpa rotasi halaman, karena kamera penting tidak
 * boleh hilang dari pandangan. Kamera yang alarm naik ke depan. Alarm tampil dengan
 * siapa yang menuju lokasi, dan denah unit menunjukkan ruang mana yang bermasalah.
 * Tidak ada tombol aksi: penanganan dilakukan dari dashboard atau Telegram.
 */
export default function LayarDinding() {
    const { cameraData: dataLangsung, alerts, connected } = useLive();
    // Selama WebSocket putus, status terakhirnya basi: yang dipakai hasil polling REST.
    const cameraData = connected ? dataLangsung : null;
    const [kamera, setKamera] = useState([]);
    // memuat | siap | galat. Layar ini dibaca dari seberang ruangan: memuat, kosong, dan
    // galat harus terlihat beda dari malam yang tenang.
    const [statusDaftar, setStatusDaftar] = useState('memuat');
    const [terakhirOk, setTerakhirOk] = useState(null);
    const tanpaKabar = statusDaftar === 'galat';
    const sekarang = useJam(1000);

    const ambil = useCallback(async () => {
        try {
            const r = await api('/api/cameras/');
            if (!r.ok) throw new Error(String(r.status));
            setKamera(await r.json());
            setStatusDaftar('siap');
            setTerakhirOk(Date.now());
        } catch {
            setStatusDaftar('galat');
        }
    }, []);
    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
        const t = setInterval(ambil, 10_000);
        return () => clearInterval(t);
    }, [ambil]);

    // Urutan sama dengan banner: alarm sungguhan yang belum direspons, yang sudah ada yang ke
    // sana, lalu latihan; terlama lebih dulu. Latihan tidak boleh menggeser alarm sungguhan
    // dari empat pita yang tampil.
    const kelompok = (a) => (a.simulated ? 2 : a.claimed_by ? 1 : 0);
    const urutAlarm = [...alerts].sort((a, b) => kelompok(a) - kelompok(b)
        || msDari(a.created_at) - msDari(b.created_at));

    const keadaan = (cam) => {
        const live = cameraData?.[cam.camera_id];
        const aktif = !tanpaKabar && cam.is_active && (live?.is_active ?? true);
        const jedaMs = msDari(live ? live.dijeda_sampai : cam.dijeda_sampai);
        const sisaJeda = aktif && Number.isFinite(jedaMs) ? Math.max(0, (jedaMs - sekarang) / 1000) : 0;
        // Alarm terburuk di ruang ini: yang belum direspons, lalu yang sudah diklaim, lalu latihan.
        // Jatuh kedua yang belum direspons tidak boleh tertutup alarm pertama yang sudah diklaim.
        const alarm = urutAlarm.find((a) => a.camera_id === cam.camera_id);
        // Tanpa WebSocket, keadaan jatuh dibaca dari polling REST (cam.*), sama seperti Pemantauan.
        const status = bacaStatus({
            aktif, state: !aktif ? 'unknown' : (live?.fall_state || cam.fall_state || 'monitoring'),
            adaOrang: Boolean(live ? live.current_posture : cam.current_posture),
            durasi: live?.fall_duration ?? cam.fall_duration ?? 0,
            latihan: alarm ? Boolean(alarm.simulated) : Boolean(live?.simulated), sisaJeda, tanpaKabar,
        });
        let warna = 'tenang';
        let kata = status.label;
        if (alarm && !alarm.simulated) {
            warna = alarm.claimed_by ? 'diklaim' : 'jatuh';
            kata = alarm.claimed_by ? `${alarm.claimed_by} menuju` : 'Kemungkinan jatuh';
        } else if (alarm || status.kode === 'latihan' || status.kode === 'perawatan') {
            warna = 'biru';
        } else if (!aktif) {
            warna = 'terputus';
        }
        return { aktif, status, alarm, warna, kata, sisaJeda };
    };

    const diDenah = kamera.filter((c) => c.denah_baris && c.denah_kolom);
    const kolomDenah = Math.max(1, ...diDenah.map((c) => c.denah_kolom));
    const kolomVideo = kamera.length <= 1 ? 1 : kamera.length <= 4 ? 2 : kamera.length <= 9 ? 3 : 4;
    const aktifSemua = kamera.filter((c) => keadaan(c).aktif).length;

    const layarPenuh = () => {
        if (document.fullscreenElement) document.exitFullscreen?.();
        else document.documentElement.requestFullscreen?.().catch(() => { /* browser menolak */ });
    };

    return (
        <div className="permukaan-gelap min-h-screen bg-slate-950 text-slate-100 p-4 flex flex-col gap-4">
            <header className="flex flex-wrap items-center gap-3">
                <Link to="/dashboard" className="p-2 rounded-lg hover:bg-slate-800" aria-label="Kembali ke dashboard">
                    <ArrowLeft className="w-5 h-5" aria-hidden="true" />
                </Link>
                <img src={logoKecil} alt="" className="w-9 h-9" />
                <h1 className="text-xl font-bold">FallDetect · Layar dinding</h1>
                <span className="ml-auto flex flex-wrap items-center gap-2 text-sm">
                    <span className="px-2.5 py-1 rounded-lg bg-slate-800 tabular-nums">
                        {statusDaftar === 'siap' ? `${aktifSemua}/${kamera.length} kamera aktif` : 'Status kamera tidak diketahui'}
                    </span>
                    {/* Aturan sama dengan lencana menu: merah penuh hanya bila ada alarm sungguhan
                        yang belum diklaim. Ubin alarmnya tetap berwarna penuh supaya terlihat dari jauh. */}
                    {connected ? (
                        <span className={`px-2.5 py-1 rounded-lg tabular-nums ${alerts.some((a) => !a.simulated && !a.claimed_by)
                            ? 'bg-red-600 text-white font-semibold'
                            : alerts.some((a) => !a.simulated)
                                ? 'border border-amber-400 bg-amber-950 text-amber-100'
                                : alerts.length ? 'border border-blue-400 bg-blue-950 text-blue-100' : 'bg-slate-800'}`}>
                            {alerts.length} alarm
                        </span>
                    ) : (
                        <span className="px-2.5 py-1 rounded-lg border border-dashed border-slate-400">Alarm tidak terpantau</span>
                    )}
                    <span className="text-2xl font-bold tabular-nums">{jamDari(sekarang)}</span>
                    <button type="button" onClick={layarPenuh} aria-label="Layar penuh" className="p-2 rounded-lg hover:bg-slate-800">
                        <Expand className="w-5 h-5" aria-hidden="true" />
                    </button>
                </span>
            </header>

            {/* Putus dari server terlihat dari seberang ruangan: strip selebar layar, bukan chip kecil. */}
            {(tanpaKabar || !connected) && (
                <div role="alert" className="rounded-xl border-2 border-dashed border-slate-400 bg-slate-800 px-4 py-3 flex items-center gap-3">
                    <WifiOff className="w-7 h-7 shrink-0" aria-hidden="true" />
                    <p className="text-xl font-semibold">
                        {tanpaKabar
                            ? `Tidak ada kabar dari server${terakhirOk ? ` sejak ${jamDari(terakhirOk)}` : ''}. Status kamera dan alarm di layar ini tidak terbaru.`
                            : 'Sambungan langsung ke server terputus. Alarm baru tidak akan tampil sampai tersambung lagi.'}
                    </p>
                </div>
            )}

            {kamera.length === 0 && !tanpaKabar && (
                <p role="status" className="text-xl text-slate-300">
                    {statusDaftar === 'memuat' ? 'Memuat daftar kamera…' : 'Belum ada kamera yang terdaftar.'}
                </p>
            )}

            {urutAlarm.length > 0 && (
                <section aria-label="Alarm" className="grid gap-2">
                    {urutAlarm.slice(0, MAKS_ALARM).map((a) => {
                        const nama = a.camera_name || a.camera_id;
                        const lama = durasiTeks((sekarang - msDari(a.created_at)) / 1000);
                        const gaya = a.simulated ? 'bg-blue-700' : a.claimed_by ? 'bg-amber-400 text-slate-950' : 'bg-red-700';
                        const Ikon = a.simulated ? FlaskConical : a.claimed_by ? Footprints : TriangleAlert;
                        return (
                            <div key={a.id} role={a.claimed_by ? 'status' : 'alert'} className={`${gaya} rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1`}>
                                <Ikon className="w-7 h-7 shrink-0" aria-hidden="true" />
                                <span className="text-2xl font-bold min-w-0 wrap-anywhere">{a.simulated ? `Latihan, ${nama}` : `Kemungkinan jatuh, ${nama}`}</span>
                                <span className="text-lg tabular-nums">
                                    {a.claimed_by ? `${a.claimed_by} menuju lokasi sejak ${jamDari(msDari(a.claimed_at))}` : `Belum ada yang merespons · ${lama}`}
                                </span>
                            </div>
                        );
                    })}
                    {urutAlarm.length > MAKS_ALARM && (
                        <p className="text-sm text-slate-300">dan {urutAlarm.length - MAKS_ALARM} alarm lain. Lihat dashboard.</p>
                    )}
                </section>
            )}

            {/* Denah lebih dari 4 kolom tidak muat di panel samping 384 px: denahnya pindah ke
                bawah video selebar layar, supaya nama ruang tidak bertumpuk. */}
            <div className={`flex-1 flex flex-col ${kolomDenah > 4 ? '' : 'xl:flex-row'} gap-4 min-h-0 min-w-0`}>
                <section aria-label="Kamera" className="flex-1 grid gap-3 content-start" style={{ gridTemplateColumns: `repeat(${kolomVideo}, minmax(0, 1fr))` }}>
                    {kamera.map((cam) => {
                        const k = keadaan(cam);
                        const naik = k.alarm && !k.alarm.simulated;
                        return (
                            <article key={cam.camera_id} aria-label={`${cam.name}: ${k.kata}`} style={{ order: naik ? -1 : 0 }}
                                className={`rounded-xl overflow-hidden border-2 bg-slate-900 ${naik ? (k.alarm.claimed_by ? 'border-amber-400' : 'border-red-600') : 'border-slate-800'}`}>
                                <header className="px-3 py-2 flex items-center justify-between gap-2">
                                    <span className="font-semibold text-lg truncate" title={cam.name}>{cam.name}</span>
                                    <StatusKamera status={k.status} className="text-sm" />
                                </header>
                                <div className="relative aspect-video bg-black flex items-center justify-center text-slate-400">
                                    {k.sisaJeda > 0 ? (
                                        <span className="flex items-center gap-2"><Clock className="w-5 h-5 shrink-0" aria-hidden="true" /> Mode perawatan · {mmss(k.sisaJeda)} lagi</span>
                                    ) : k.aktif ? (
                                        <StreamImg src={`${API_BASE}${cam.stream_url}`} alt={`Video ${cam.name}`} kunci={cam.camera_id} />
                                    ) : (
                                        <span className="px-4 flex items-center gap-2 min-w-0 max-w-full text-center wrap-anywhere">
                                            <VideoOff className="w-5 h-5 shrink-0" aria-hidden="true" />
                                            {tanpaKabar ? `${cam.name}: tanpa kabar` : `${cam.name} tidak terpantau`}
                                        </span>
                                    )}
                                </div>
                            </article>
                        );
                    })}
                </section>

                {diDenah.length > 0 && (
                    <section aria-label="Denah unit" className={`${kolomDenah > 4 ? '' : 'xl:w-96'} shrink-0 min-w-0`}>
                        <h2 className="text-sm font-semibold text-slate-400 mb-2">Denah unit</h2>
                        <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${kolomDenah}, minmax(0, 1fr))` }}>
                            {diDenah.map((cam) => {
                                const k = keadaan(cam);
                                return (
                                    <div key={cam.camera_id} style={{ gridRow: cam.denah_baris, gridColumn: cam.denah_kolom }}
                                        className={`min-h-20 min-w-0 rounded-lg border-2 p-2 flex flex-col justify-between ${WARNA_RUANG[k.warna]}`}>
                                        <span className="font-semibold leading-tight wrap-anywhere">{cam.name}</span>
                                        <span className="text-xs leading-tight wrap-anywhere">{k.kata}</span>
                                    </div>
                                );
                            })}
                        </div>
                        {kamera.length > diDenah.length && (
                            <p className="text-xs text-slate-500 mt-2">
                                Belum di denah: {kamera.filter((c) => !(c.denah_baris && c.denah_kolom)).map((c) => c.name).join(', ')}.
                                Atur letaknya di Daftar Kamera.
                            </p>
                        )}
                    </section>
                )}
            </div>
        </div>
    );
}
