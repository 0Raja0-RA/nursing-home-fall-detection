import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Clock, Eye, EyeOff, FlaskConical, Monitor, Send, Video, VideoOff, Volume2, VolumeX, X } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { usePengunjung } from '../context/auth';
import { useLive } from '../context/LiveContext';
import { aktifkanSuara, bunyikan, useStatusSuara } from '../hooks/useAlarmSound';
import { usePengaturan } from '../hooks/usePengaturan';
import StatusKamera from '../components/StatusKamera';
import StreamImg from '../components/StreamImg';
import { bacaStatus, jamDari, mmss } from '../statusKamera';
import { msDari, useJam } from '../waktu';

const CHIP = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs whitespace-nowrap';
const CHIP_TENANG = `${CHIP} bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300`;
const PILIHAN_JEDA = [15, 30, 60];

// Rasio video tiap kamera, disimpan di luar komponen supaya kartu langsung berukuran
// benar saat halaman ini dibuka lagi. Tanpa itu kartu melompat begitu video termuat,
// dan "Lihat kamera" bisa berhenti di posisi yang sudah bergeser.
const rasioTersimpan = {};

function bacaDetailAI() {
    try { return localStorage.getItem('detailAI') === '1'; } catch { return false; }
}

export default function SimulationDashboard() {
    const [cameras, setCameras] = useState([]);
    const [panelLatihan, setPanelLatihan] = useState(false);
    const [kameraLatihanId, setKameraLatihanId] = useState('');
    const [memulai, setMemulai] = useState(false);
    const [galat, setGalat] = useState('');
    // Nama kelas dan keyakinan model berguna untuk tim, bukan untuk perawat,
    // jadi disembunyikan kecuali dinyalakan.
    const [detailAI, setDetailAI] = useState(bacaDetailAI);
    // Rasio lebar/tinggi video per kamera. Tile mengikutinya supaya tidak ada pita
    // hitam di atas-bawah atau kiri-kanan, termasuk untuk kamera HP yang tegak.
    const [rasio, setRasio] = useState(() => ({ ...rasioTersimpan }));
    // Pilihan "kirim latihan ke Telegram" yang baru diubah di halaman ini; selama
    // belum diubah, nilai dari pengaturan backend yang dipakai.
    const [kirimLatihan, setKirimLatihan] = useState(null);
    // Kamera yang pilihan Mode perawatannya sedang terbuka, dan yang permintaannya sedang dikirim.
    const [menuJeda, setMenuJeda] = useState('');
    const [mengubahJeda, setMengubahJeda] = useState('');

    const { cameraData, alerts } = useLive();
    // Pengunjung pameran hanya menonton: tanpa Mode latihan dan tanpa kontrol suara.
    const pengunjung = usePengunjung();
    const suara = useStatusSuara();
    const pengaturan = usePengaturan();
    const lokasi = useLocation();
    const fokusSelesai = useRef(null);

    // Daftar kamera diambil dari backend, jadi kamera yang didaftarkan di halaman
    // "Daftar Kamera" langsung muncul di sini tanpa menyunting kode.
    const ambilDaftar = useCallback(async () => {
        try {
            const r = await api('/api/cameras/');
            if (r.ok) setCameras(await r.json());
        } catch { /* backend belum jalan; grid tampil kosong dengan petunjuk */ }
    }, []);

    const catatRasio = useCallback((id, w, h) => {
        rasioTersimpan[id] = w / h;
        setRasio((r) => (r[id] === w / h ? r : { ...r, [id]: w / h }));
    }, []);

    useEffect(() => {
        // Berlangganan ke sistem luar (backend). setState-nya terjadi di callback async
        // setelah fetch selesai, bukan sinkron -- linter tidak bisa menelusuri ke sana.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambilDaftar();
        const t = setInterval(ambilDaftar, 5000);
        return () => clearInterval(t);
    }, [ambilDaftar]);

    // Pilihan awal Mode latihan: kamera pertama yang benar-benar mengalir.
    useEffect(() => {
        if (!kameraLatihanId && cameras.length) {
            // Menyelaraskan pilihan dengan daftar yang baru tiba dari backend.
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setKameraLatihanId((cameras.find((c) => c.is_active) || cameras[0]).camera_id);
        }
    }, [cameras, kameraLatihanId]);

    // "Lihat kamera" di banner membawa id kamera. Gulir ke kartunya begitu daftar kamera ada.
    useEffect(() => {
        const id = lokasi.state?.fokus;
        if (!id || fokusSelesai.current === lokasi.key || !cameras.length) return undefined;
        const el = document.getElementById(`kamera-${id}`);
        if (!el) return undefined;
        fokusSelesai.current = lokasi.key;
        const halus = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        // Berhenti tepat di bawah banner alarm yang menempel di atas layar (di HP
        // ditambah bilah atas), supaya kartu kameranya tidak tertutup banner itu.
        const tujuan = () => {
            const bawahBanner = document.getElementById('banner-alarm')?.getBoundingClientRect().bottom ?? 0;
            return el.getBoundingClientRect().top + window.scrollY - bawahBanner - 12;
        };
        window.scrollTo({ top: tujuan(), behavior: halus ? 'smooth' : 'auto' });

        // Video yang baru termuat bisa mengubah tinggi kartu di atasnya. Selama pengguna
        // belum menggulir sendiri, posisinya disamakan lagi sampai tata letaknya tenang.
        let disentuh = false;
        const sentuh = () => { disentuh = true; };
        const tanda = ['wheel', 'touchstart', 'keydown'];
        tanda.forEach((n) => window.addEventListener(n, sentuh, { passive: true }));
        const timer = [700, 1500, 3000].map((ms) => setTimeout(() => {
            if (!disentuh && Math.abs(tujuan() - window.scrollY) > 8) window.scrollTo({ top: tujuan(), behavior: 'auto' });
        }, ms));
        return () => {
            timer.forEach(clearTimeout);
            tanda.forEach((n) => window.removeEventListener(n, sentuh));
        };
    }, [lokasi.key, lokasi.state, cameras.length]);

    const ubahDetailAI = (nyala) => {
        setDetailAI(nyala);
        try { localStorage.setItem('detailAI', nyala ? '1' : '0'); } catch { /* tanpa penyimpanan */ }
    };

    const tesSuara = async () => {
        if (await aktifkanSuara()) bunyikan();
    };

    const latihanKeTelegram = kirimLatihan ?? Boolean(pengaturan?.telegram?.send_drills);
    const ubahKirimLatihan = async (nyala) => {
        setKirimLatihan(nyala);
        try {
            const r = await api('/api/settings/telegram', { method: 'PUT', json: { send_drills: nyala } });
            if (!r.ok) throw new Error(await bacaGalat(r));
        } catch (err) {
            setKirimLatihan(!nyala);
            setGalat(err instanceof TypeError ? PESAN_TERPUTUS : `Pilihan Telegram gagal disimpan: ${err.message}`);
        }
    };

    /**
     * Minta backend menganggap satu kamera melaporkan postur pemicu.
     *
     * Yang disimulasikan hanya keluaran detektor. State machine tetap menghitung
     * durasinya sendiri, debounce tetap berlaku, cooldown tetap dihormati, dan
     * alertnya melewati jalur yang sama dengan deteksi sungguhan -- termasuk foto
     * frame kamera saat itu juga dan penanda SIMULASI di riwayat dan Telegram.
     */
    const mulaiLatihan = async () => {
        if (!kameraLatihanId || memulai) return;
        setMemulai(true);
        setGalat('');
        try {
            const r = await api(`/api/cameras/${kameraLatihanId}/simulate-fall`, { method: 'POST' });
            if (r.ok) {
                setPanelLatihan(false);
            } else {
                setGalat(await bacaGalat(r));
            }
        } catch {
            setGalat(PESAN_TERPUTUS);
        } finally {
            setMemulai(false);
        }
    };

    /**
     * Mode perawatan: mulai (atau perpanjang) dengan menit, hentikan dengan menit null.
     * Jawabannya langsung dipakai, supaya kartu berubah tanpa menunggu polling.
     */
    const ubahJeda = async (cam, menit) => {
        setMengubahJeda(cam.camera_id);
        setGalat('');
        try {
            const r = await api(`/api/cameras/${cam.camera_id}/jeda`,
                menit ? { method: 'POST', json: { menit } } : { method: 'DELETE' });
            if (!r.ok) {
                setGalat(await bacaGalat(r));
                return;
            }
            const data = await r.json();
            setCameras((prev) => prev.map((c) => (c.camera_id === data.camera_id ? { ...c, ...data } : c)));
            setMenuJeda('');
        } catch {
            setGalat(PESAN_TERPUTUS);
        } finally {
            setMengubahJeda('');
        }
    };

    // Status WebSocket lebih baru daripada polling, termasuk saat jeda baru saja habis.
    const jedaSampai = (cam) => {
        const live = cameraData?.[cam.camera_id];
        return msDari(live ? live.dijeda_sampai : cam.dijeda_sampai);
    };
    const jedaOleh = (cam) => cameraData?.[cam.camera_id]?.dijeda_oleh || cam.dijeda_oleh;
    // Hitung mundur per detik hanya selama ada kamera yang dijeda atau video aslinya dibuka.
    const sekarang = useJam(cameras.some((c) => Number.isFinite(jedaSampai(c)) || c.asli_sampai) ? 1000 : 30000);
    const sisaAsli = (cam) => {
        const ms = msDari(cam.asli_sampai);
        return Number.isFinite(ms) ? Math.max(0, (ms - sekarang) / 1000) : 0;
    };

    /** Video asli kamera berprivasi, 15 detik, hanya saat ada alarm di ruang itu. Tercatat di backend. */
    const bukaAsli = async (cam) => {
        setGalat('');
        try {
            const r = await api(`/api/cameras/${cam.camera_id}/buka-asli`, { method: 'POST' });
            if (!r.ok) {
                setGalat(await bacaGalat(r));
                return;
            }
            const data = await r.json();
            setCameras((prev) => prev.map((c) => (c.camera_id === data.camera_id ? { ...c, ...data } : c)));
        } catch {
            setGalat(PESAN_TERPUTUS);
        }
    };
    const sisaJeda = (cam) => {
        const ms = jedaSampai(cam);
        return Number.isFinite(ms) ? Math.max(0, (ms - sekarang) / 1000) : 0;
    };

    const kameraLatihan = cameras.find((c) => c.camera_id === kameraLatihanId) || cameras[0];
    const jumlahAktif = cameras.filter((c) => c.is_active).length;
    const jumlahTerputus = cameras.length - jumlahAktif;
    const sedangLatihan = cameras.filter((c) => cameraData?.[c.camera_id]?.simulated);
    const jumlahJeda = cameras.filter((c) => c.is_active && sisaJeda(c) > 0).length;

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Pemantauan Kamera</h1>
                    <p className="text-xs md:text-sm text-slate-500">Status setiap kamera, diperbarui langsung.</p>
                </div>
                {!pengunjung && <div className="flex flex-wrap gap-2">
                <Link
                    to="/dinding"
                    target="_blank"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
                >
                    <Monitor className="w-4 h-4" aria-hidden="true" /> Layar dinding
                </Link>
                <button
                    type="button"
                    onClick={() => setPanelLatihan((b) => !b)}
                    aria-expanded={panelLatihan}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors"
                >
                    <FlaskConical className="w-4 h-4" aria-hidden="true" /> Mode latihan
                </button>
                </div>}
            </div>

            {/* Ringkasan: perawat tahu keadaan semua kamera tanpa memindai tiap kartu. */}
            <div className="flex flex-wrap items-center gap-2 mb-6" aria-label="Ringkasan sistem">
                <span className={CHIP_TENANG}>
                    <Video className="w-3.5 h-3.5" aria-hidden="true" />
                    <b className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{jumlahAktif}/{cameras.length}</b> kamera aktif
                </span>
                {jumlahTerputus > 0 && (
                    <span className={`${CHIP} border border-dashed border-slate-400 dark:border-slate-500 text-slate-700 dark:text-slate-200`}>
                        <VideoOff className="w-3.5 h-3.5" aria-hidden="true" />
                        <b className="font-semibold tabular-nums">{jumlahTerputus}</b> terputus
                    </span>
                )}
                {jumlahJeda > 0 && (
                    <span className={`${CHIP} border border-blue-500 bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200`}>
                        <Clock className="w-3.5 h-3.5" aria-hidden="true" />
                        <b className="font-semibold tabular-nums">{jumlahJeda}</b> dalam Mode perawatan
                    </span>
                )}
                <span className={alerts.length ? `${CHIP} bg-red-600 text-white font-semibold` : CHIP_TENANG}>
                    <b className="font-semibold tabular-nums">{alerts.length}</b> alarm
                </span>
                {!pengunjung && <span className={CHIP_TENANG}>
                    {suara === 'aktif'
                        ? <><Volume2 className="w-3.5 h-3.5" aria-hidden="true" /> Suara aktif</>
                        : <><VolumeX className="w-3.5 h-3.5" aria-hidden="true" /> Suara belum aktif</>}
                    <button
                        type="button"
                        onClick={tesSuara}
                        className="ml-1 font-semibold text-slate-800 dark:text-slate-100 underline underline-offset-2"
                    >
                        Tes suara
                    </button>
                </span>}
                {pengaturan && !pengunjung && (
                    <span className={CHIP_TENANG}>
                        <Send className="w-3.5 h-3.5" aria-hidden="true" />
                        {pengaturan.telegram_configured ? 'Telegram aktif' : 'Telegram belum dikonfigurasi'}
                    </span>
                )}
                <label className={`${CHIP_TENANG} cursor-pointer md:ml-auto`}>
                    <input
                        type="checkbox"
                        checked={detailAI}
                        onChange={(e) => ubahDetailAI(e.target.checked)}
                        className="accent-slate-600"
                    />
                    Tampilkan detail AI
                </label>
            </div>

            {sedangLatihan.length > 0 && (
                <div role="status" className="mb-6 px-4 py-2.5 rounded-xl bg-blue-600 text-white text-sm flex items-center gap-2">
                    <FlaskConical className="w-4 h-4 shrink-0" aria-hidden="true" />
                    Latihan berjalan di {sedangLatihan.map((c) => c.name).join(', ')}. Bukan kejadian sungguhan.
                </div>
            )}

            {panelLatihan && !pengunjung && (
                <div className="mb-6 rounded-2xl border border-blue-500/30 bg-blue-50 dark:bg-blue-950/40 p-4">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <h2 className="font-semibold text-sm">Mode latihan</h2>
                            <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 max-w-2xl">
                                Latihan menjalankan alur alarm sungguhan di satu kamera: hitungan, banner,
                                Saya ke sana, dan riwayat. Semuanya bertanda latihan, jadi tidak tertukar
                                dengan kejadian nyata, dan tidak ikut dihitung sebagai alarm benar atau palsu.
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={() => setPanelLatihan(false)}
                            aria-label="Tutup Mode latihan"
                            className="p-1.5 rounded-lg text-slate-500 hover:bg-blue-100 dark:hover:bg-blue-900/40"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                    <div className="mt-3 flex flex-col sm:flex-row sm:items-end gap-3">
                        <label className="text-xs font-medium flex flex-col gap-1">
                            Kamera untuk latihan
                            <select
                                value={kameraLatihanId}
                                onChange={(e) => setKameraLatihanId(e.target.value)}
                                className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 px-3 py-2 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            >
                                {cameras.length === 0 && <option value="">Belum ada kamera</option>}
                                {cameras.map((c) => (
                                    <option key={c.camera_id} value={c.camera_id}>
                                        {c.name}{c.is_active ? '' : ' (terputus)'}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <button
                            type="button"
                            onClick={mulaiLatihan}
                            disabled={memulai || !kameraLatihan?.is_active}
                            className="min-h-11 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 rounded-xl text-sm font-medium"
                        >
                            {memulai ? 'Memulai…' : 'Mulai latihan'}
                        </button>
                    </div>
                    {pengaturan?.telegram_configured && (
                        <label className="mt-3 flex items-start gap-2 text-xs cursor-pointer">
                            <input
                                type="checkbox"
                                checked={latihanKeTelegram}
                                onChange={(e) => ubahKirimLatihan(e.target.checked)}
                                className="mt-0.5 accent-blue-600"
                            />
                            <span>
                                Kirim juga ke grup Telegram, bertanda LATIHAN. Bawaannya mati, supaya grup tidak
                                terbiasa mengabaikan pesan alarm.
                            </span>
                        </label>
                    )}
                </div>
            )}

            {galat && (
                <div className="mb-6 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400 text-sm">
                    {galat}
                </div>
            )}

            {/* Grid kamera. Kamera yang alarm naik ke depan lewat CSS order, bukan
                menyusun ulang DOM, supaya aliran MJPEG-nya tidak terputus. */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full items-start">
                {cameras.length === 0 && (
                    <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center text-sm text-slate-500 shadow-sm">
                        Belum ada kamera yang terdaftar. Tambahkan di halaman <strong>Daftar Kamera</strong>,
                        dan kamera itu akan langsung muncul di sini.
                    </div>
                )}

                {cameras.map((cam) => {
                    // Status langsung dari WebSocket kalau ada, kalau tidak dari hasil polling.
                    const live = cameraData?.[cam.camera_id];
                    const aktif = cam.is_active && (live?.is_active ?? true);
                    const state = !aktif ? 'unknown' : (live?.fall_state || cam.fall_state || 'monitoring');
                    const posture = live ? live.current_posture : cam.current_posture;
                    const conf = live?.confidence ?? cam.confidence ?? 0;
                    const durasi = live?.fall_duration ?? cam.fall_duration ?? 0;
                    const latihan = Boolean(live?.simulated)
                        || alerts.some((a) => a.camera_id === cam.camera_id && a.simulated);
                    const sisa = sisaJeda(cam);
                    const dijeda = aktif && sisa > 0;
                    const privasi = cam.privasi || 'utuh';
                    const detikAsli = privasi !== 'utuh' ? sisaAsli(cam) : 0;
                    const bolehBukaAsli = !pengunjung && privasi !== 'utuh' && !detikAsli
                        && alerts.some((a) => a.camera_id === cam.camera_id);
                    const status = bacaStatus({
                        aktif, state, adaOrang: Boolean(posture), durasi,
                        ambang: pengaturan?.fall_duration_threshold, latihan, sisaJeda: sisa,
                    });

                    const jatuh = state === 'confirmed_fall';
                    const berbaring = state === 'possible_fall';
                    let bingkai = 'border-slate-200 dark:border-slate-800';
                    if (!aktif) bingkai = 'border-dashed border-slate-400 dark:border-slate-600';
                    else if (jatuh) bingkai = latihan ? 'border-2 border-blue-600' : 'border-2 border-red-600';
                    else if (berbaring) bingkai = latihan ? 'border-blue-500' : 'border-amber-400';
                    else if (dijeda) bingkai = 'border-blue-300 dark:border-blue-800';

                    return (
                        <section
                            key={cam.camera_id}
                            id={`kamera-${cam.camera_id}`}
                            aria-label={`${cam.name}: ${status.label}`}
                            style={{ order: jatuh ? -2 : berbaring ? -1 : 0 }}
                            className={`relative scroll-mt-24 bg-white dark:bg-slate-900 rounded-2xl border overflow-hidden shadow-sm ${jatuh ? 'lg:col-span-2' : ''} ${bingkai}`}
                        >
                            {/* Hanya tepinya yang berdenyut, tidak lebih cepat dari sekali per detik,
                                dan diam bila pengguna meminta gerak dikurangi. */}
                            {jatuh && !latihan && (
                                <span aria-hidden="true" className="pointer-events-none absolute inset-0 z-10 rounded-2xl ring-4 ring-red-500/50 motion-safe:animate-pulse" />
                            )}

                            <header className="p-3 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center gap-3">
                                <span className="font-semibold text-sm flex items-center gap-2 min-w-0">
                                    <Video className="w-4 h-4 shrink-0 text-slate-400" aria-hidden="true" />
                                    <span className="truncate">{cam.name}</span>
                                </span>
                                <span className="flex items-center gap-2 shrink-0">
                                    <StatusKamera status={status} />
                                    {!pengunjung && aktif && !dijeda && (
                                        <button
                                            type="button"
                                            onClick={() => setMenuJeda((m) => (m === cam.camera_id ? '' : cam.camera_id))}
                                            aria-expanded={menuJeda === cam.camera_id}
                                            aria-label={`Mode perawatan untuk ${cam.name}`}
                                            title="Mode perawatan"
                                            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-200/70 dark:hover:bg-slate-800"
                                        >
                                            <Clock className="w-4 h-4" aria-hidden="true" />
                                            <span className="hidden sm:inline">Jeda</span>
                                        </button>
                                    )}
                                </span>
                            </header>

                            {menuJeda === cam.camera_id && !dijeda && (
                                <div className="p-3 border-b border-blue-200 dark:border-blue-900 bg-blue-50 dark:bg-blue-950/40 space-y-2">
                                    <p className="text-sm font-semibold">Mode perawatan untuk {cam.name}</p>
                                    <p className="text-xs text-slate-600 dark:text-slate-400">
                                        Deteksi jatuh dan video dijeda, misalnya saat penghuni dimandikan. Selama jeda,
                                        jatuh di ruang ini tidak terdeteksi. Alarm yang sudah muncul tetap harus ditangani.
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {PILIHAN_JEDA.map((menit) => (
                                            <button
                                                key={menit}
                                                type="button"
                                                disabled={mengubahJeda === cam.camera_id}
                                                onClick={() => ubahJeda(cam, menit)}
                                                className="min-h-10 px-3 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-sm font-semibold"
                                            >
                                                {menit} menit
                                            </button>
                                        ))}
                                        <button
                                            type="button"
                                            onClick={() => setMenuJeda('')}
                                            className="min-h-10 px-3 rounded-lg border border-slate-300 dark:border-slate-700 text-sm font-semibold hover:bg-white dark:hover:bg-slate-800"
                                        >
                                            Batal
                                        </button>
                                    </div>
                                </div>
                            )}

                            <div
                                className="bg-slate-950 relative flex items-center justify-center text-slate-300 max-h-[75vh] mx-auto"
                                style={{ aspectRatio: (aktif && rasio[cam.camera_id]) || 16 / 9 }}
                            >
                                {dijeda ? (
                                    <div className="px-6 text-center flex flex-col items-center gap-2">
                                        <Clock className="w-8 h-8 text-blue-300" aria-hidden="true" />
                                        <p className="text-sm font-semibold text-slate-100 tabular-nums">
                                            Mode perawatan · {mmss(sisa)} lagi
                                        </p>
                                        <p className="text-xs text-slate-400 max-w-sm">
                                            Deteksi jatuh dan video dijeda sampai {jamDari(jedaSampai(cam))}
                                            {jedaOleh(cam) ? `, dimulai ${jedaOleh(cam)}` : ''}. Jatuh di ruang ini tidak terdeteksi.
                                        </p>
                                        {!pengunjung && (
                                            <div className="mt-1 flex flex-wrap justify-center gap-2">
                                                <button
                                                    type="button"
                                                    disabled={mengubahJeda === cam.camera_id}
                                                    onClick={() => ubahJeda(cam, null)}
                                                    className="min-h-10 px-3 rounded-lg bg-white text-slate-900 hover:bg-slate-200 disabled:opacity-60 text-sm font-semibold"
                                                >
                                                    Lanjutkan pemantauan
                                                </button>
                                                <button
                                                    type="button"
                                                    disabled={mengubahJeda === cam.camera_id}
                                                    onClick={() => ubahJeda(cam, 15)}
                                                    className="min-h-10 px-3 rounded-lg border border-slate-500 text-slate-100 hover:bg-slate-800 disabled:opacity-60 text-sm font-semibold"
                                                >
                                                    +15 mnt
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ) : aktif ? (
                                    <StreamImg
                                        src={`${API_BASE}${cam.stream_url}${detikAsli ? '?asli=true' : ''}`}
                                        alt={`Video ${cam.name}`}
                                        kunci={cam.camera_id}
                                        onUkuran={catatRasio}
                                    />
                                ) : (
                                    <div className="px-6 text-center flex flex-col items-center gap-2">
                                        <p className="text-sm font-semibold text-slate-100">{cam.name} tidak terpantau</p>
                                        <p className="text-xs text-slate-400">Kamera tidak mengirim gambar. Periksa daya dan jaringannya.</p>
                                        <Link
                                            to="/dashboard/cameras"
                                            className="mt-1 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-800"
                                        >
                                            Buka Daftar Kamera
                                        </Link>
                                    </div>
                                )}

                                {aktif && !dijeda && (privasi !== 'utuh' || bolehBukaAsli) && (
                                    <div className="absolute right-3 top-3 flex flex-col items-end gap-2">
                                        {privasi !== 'utuh' && (
                                            <span className="text-xs text-white bg-black/60 px-2 py-1 rounded inline-flex items-center gap-1.5 tabular-nums">
                                                {detikAsli
                                                    ? <><Eye className="w-3.5 h-3.5" aria-hidden="true" /> Video asli · {Math.ceil(detikAsli)} dtk</>
                                                    : <><EyeOff className="w-3.5 h-3.5" aria-hidden="true" /> {privasi === 'buram' ? 'Video buram' : 'Kerangka saja'}</>}
                                            </span>
                                        )}
                                        {bolehBukaAsli && (
                                            <button
                                                type="button"
                                                onClick={() => bukaAsli(cam)}
                                                className="min-h-9 px-3 rounded-lg bg-white text-slate-900 text-xs font-semibold inline-flex items-center gap-1.5 hover:bg-slate-200"
                                            >
                                                <Eye className="w-3.5 h-3.5" aria-hidden="true" /> Lihat video asli 15 dtk
                                            </button>
                                        )}
                                    </div>
                                )}

                                {aktif && !dijeda && (status.kode === 'kosong' || detailAI) && (
                                    <div className="absolute left-3 bottom-3 flex flex-col items-start gap-1">
                                        {status.kode === 'kosong' && live?.terakhir_terlihat && (
                                            <span className="text-xs text-white bg-black/60 px-2 py-1 rounded">
                                                Orang terakhir terlihat {jamDari(live.terakhir_terlihat)}
                                            </span>
                                        )}
                                        {detailAI && (
                                            <span className="text-xs text-white font-mono bg-black/60 px-2 py-1 rounded">
                                                {posture ? `${posture} · ${(conf * 100).toFixed(0)}%` : 'tidak ada deteksi'}
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        </section>
                    );
                })}
            </div>
        </div>
    );
}
