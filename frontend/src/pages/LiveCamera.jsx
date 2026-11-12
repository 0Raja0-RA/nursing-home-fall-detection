import { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, RefreshCw, FlaskConical, TestTube } from 'lucide-react';

import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';
import { usePengaturan } from '../hooks/usePengaturan';
import StatusKamera from '../components/StatusKamera';
import { bacaStatus, mmss } from '../statusKamera';
import { msDari, useJam } from '../waktu';

// Halaman ini menampilkan satu kamera untuk diuji dari dekat. Kameranya dipilih
// lewat dropdown di kanan atas. Status, postur, dan hitungan durasinya datang dari
// backend (state machine yang sama dengan deteksi sungguhan), bukan tiruan di
// browser. Alarm jatuh ditampilkan oleh AlertBanner global di semua halaman.
//
// Di atas video hanya ada satu bacaan status. Keluaran mentah model, yang berguna
// saat menguji tetapi membingungkan bila bertabrakan dengan status, ada di panel
// di bawah video.

const SKRIP_UJI = [
    'Berdiri di tengah ruang dengan seluruh tubuh terlihat. Harapan: Terpantau.',
    'Berbaring di lantai dekat kamera lebih lama dari ambang. Harapan: Berbaring, lalu Kemungkinan jatuh.',
    'Ulangi di tengah ruang dan di titik terjauh dari kamera.',
    'Uji negatif: duduk di kursi, berlutut, lalu membungkuk mengambil barang. Harapan: tidak sampai alarm.',
    'Bila orang sering tidak terbaca, ubah posisi atau sudut kamera sampai seluruh tubuh masuk bingkai.',
];

export default function LiveCamera() {
    const [cari] = useSearchParams();
    const [rotasi, setRotasi] = useState(0); // derajat tampilan, untuk tombol "Putar Kamera"
    const [diag, setDiag] = useState(null);
    const [errorMsg, setErrorMsg] = useState('');
    const [daftarKamera, setDaftarKamera] = useState([]);
    const [kameraId, setKameraId] = useState('');
    const [memulai, setMemulai] = useState(false);

    const { cameraData } = useLive();
    const pengaturan = usePengaturan();

    // Ambil daftar kamera supaya pengguna bisa memilih yang mana yang diuji.
    useEffect(() => {
        let batal = false;
        const ambil = async () => {
            try {
                const r = await api('/api/cameras/');
                if (!r.ok || batal) return;
                const d = await r.json();
                setDaftarKamera(d);
                // Pilihan awal: kamera pertama yang benar-benar mengalir.
                // Dari tombol Uji di Daftar Kamera; tanpa itu, kamera pertama yang mengalir.
                const diminta = d.find((c) => c.camera_id === cari.get('kamera'));
                setKameraId((k) => k || (diminta || d.find((c) => c.is_active) || d[0])?.camera_id || '');
            } catch { /* backend belum jalan */ }
        };
        ambil();
        const t = setInterval(ambil, 5000);
        return () => { batal = true; clearInterval(t); };
    }, [cari]);

    // MJPEG adalah respons HTTP yang tidak pernah selesai. Kalau elemen <img>-nya
    // dibuang tanpa mengosongkan src lebih dulu, browser menahan koneksi itu tetap
    // terbuka, dan setelah beberapa kali berpindah halaman batas koneksi per host
    // habis sehingga dashboard terlihat membeku.
    const imgRef = useRef(null);
    useEffect(() => {
        const el = imgRef.current;
        if (!el || !kameraId) return;
        // src dipasang di sini, bukan lewat atribut JSX. React.StrictMode menjalankan
        // efek dua kali di mode dev (pasang -> bersihkan -> pasang lagi); kalau src
        // ditulis di JSX, pembersihan pertama membatalkan permintaan dan React tidak
        // pernah memasangnya kembali karena prop-nya dianggap tidak berubah.
        el.src = `${API_BASE}/api/cameras/${kameraId}/stream`;
        return () => { el.src = ''; };
    }, [kameraId]);

    // Memutar tampilan 90 derajat setiap kali ditekan. Ini hanya memutar gambar di layar;
    // rotasi yang dipakai model diatur per kamera di halaman Daftar Kamera.
    const switchCamera = () => setRotasi((prev) => (prev + 90) % 360);

    const live = cameraData?.[kameraId];
    const kamera = daftarKamera.find((c) => c.camera_id === kameraId);
    const aktif = (kamera?.is_active ?? false) && (live?.is_active ?? true);
    const state = !aktif ? 'unknown' : (live?.fall_state || 'monitoring');
    const durasi = live?.fall_duration ?? 0;
    const posture = live?.current_posture;
    const ambang = pengaturan?.fall_duration_threshold;
    const status = bacaStatus({
        aktif, state, adaOrang: Boolean(posture), durasi, ambang, latihan: Boolean(live?.simulated),
    });

    // Minta backend menganggap kamera ini melaporkan postur pemicu. State machine
    // tetap menghitung durasinya sendiri; alarm muncul setelah ambang terlewati.
    const mulaiLatihan = async () => {
        if (!kameraId || memulai) return;
        const setuju = window.confirm(
            `Mulai latihan jatuh di ${kamera?.name || kameraId}? Banner dan riwayat akan bertanda latihan.`,
        );
        if (!setuju) return;
        setMemulai(true);
        setErrorMsg('');
        try {
            const r = await api(`/api/cameras/${kameraId}/simulate-fall`, { method: 'POST' });
            if (!r.ok) setErrorMsg(await bacaGalat(r));
        } catch {
            setErrorMsg(PESAN_TERPUTUS);
        } finally {
            setMemulai(false);
        }
    };

    // Panel diagnostik: semua deteksi frame terakhir, waktu inferensi, dan laju.
    useEffect(() => {
        if (!kameraId) return undefined;
        let batal = false;
        const ambil = async () => {
            try {
                const r = await api(`/api/cameras/${kameraId}/diagnostik`);
                if (r.ok && !batal) setDiag(await r.json());
            } catch { /* panel tetap menampilkan angka terakhir */ }
        };
        ambil();
        const t = setInterval(ambil, 1000);
        return () => { batal = true; clearInterval(t); };
    }, [kameraId]);

    const sekarang = useJam(diag?.uji_sampai ? 1000 : 30000);
    const sisaUji = diag?.uji_sampai ? Math.max(0, (msDari(diag.uji_sampai) - sekarang) / 1000) : 0;

    /** Mode uji: deteksi sungguhan, tetapi alarmnya dicatat sebagai latihan. */
    const ubahUji = async (nyala) => {
        setErrorMsg('');
        try {
            const r = await api(`/api/cameras/${kameraId}/uji`, nyala ? { method: 'POST', json: { menit: 10 } } : { method: 'DELETE' });
            if (!r.ok) setErrorMsg(await bacaGalat(r));
            else setDiag(await r.json());
        } catch {
            setErrorMsg(PESAN_TERPUTUS);
        }
    };

    const kartu = 'rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-3';

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <Link to="/dashboard/cameras" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline mb-1">
                        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" /> Daftar Kamera
                    </Link>
                    <h1 className="text-xl md:text-2xl font-bold">Uji Kamera</h1>
                    <p className="text-xs md:text-sm text-slate-500">Cek posisi kamera dan hasil deteksinya sebelum dipakai memantau.</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <label className="sr-only" htmlFor="pilih-kamera-uji">Kamera yang diuji</label>
                    <select
                        id="pilih-kamera-uji"
                        value={kameraId}
                        onChange={(e) => setKameraId(e.target.value)}
                        className="bg-slate-200 dark:bg-slate-800 hover:opacity-80 px-3 py-2 rounded-xl text-xs md:text-sm font-medium transition-colors focus:outline-none"
                    >
                        {daftarKamera.length === 0 && <option value="">Belum ada kamera</option>}
                        {daftarKamera.map((c) => (
                            <option key={c.camera_id} value={c.camera_id}>
                                {c.name}{c.is_active ? '' : ' (terputus)'}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={switchCamera}
                        className="bg-slate-200 dark:bg-slate-800 hover:opacity-80 px-4 py-2 rounded-xl text-xs md:text-sm font-medium flex items-center gap-2 transition-colors"
                    >
                        <RefreshCw className="w-4 h-4" aria-hidden="true" /> Putar tampilan
                    </button>
                    <button
                        onClick={mulaiLatihan}
                        disabled={memulai || !aktif}
                        className="border border-blue-500/50 text-blue-700 dark:text-blue-300 hover:bg-blue-500/10 disabled:opacity-50 px-4 py-2 rounded-xl text-xs md:text-sm font-medium flex items-center gap-2 transition-colors"
                    >
                        <FlaskConical className="w-4 h-4" aria-hidden="true" /> Latihan jatuh
                    </button>
                    <button
                        onClick={() => ubahUji(!sisaUji)}
                        disabled={!aktif}
                        aria-pressed={Boolean(sisaUji)}
                        className={`px-4 py-2 rounded-xl text-xs md:text-sm font-medium flex items-center gap-2 transition-colors disabled:opacity-50 ${sisaUji
                            ? 'bg-blue-600 text-white' : 'border border-blue-500/50 text-blue-700 dark:text-blue-300 hover:bg-blue-500/10'}`}
                    >
                        <TestTube className="w-4 h-4" aria-hidden="true" />
                        {sisaUji ? `Akhiri Mode uji (${mmss(sisaUji)})` : 'Mode uji 10 menit'}
                    </button>
                </div>
            </div>

            {errorMsg && (
                <div className="mb-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm">
                    {errorMsg}
                </div>
            )}

            <div className="relative bg-slate-950 rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl aspect-video flex items-center justify-center">
                <img
                    ref={imgRef}
                    alt={`Video ${kamera?.name || ''}`}
                    onLoad={() => setErrorMsg('')}
                    onError={() => setErrorMsg('Video tidak dapat dimuat. Pastikan server (run-backend.bat) berjalan dan kameranya terbaca.')}
                    style={{ transform: `rotate(${rotasi}deg)` }}
                    className="w-full h-full object-contain transition-transform"
                />
                <div className="absolute top-4 left-4">
                    <StatusKamera status={status} className="text-sm px-3 py-1 shadow-lg" />
                </div>
            </div>

            {/* Panel uji: keluaran mentah model untuk tim, terpisah dari status di atas video. */}
            <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-3 text-sm">
                <div className={`${kartu} lg:col-span-2`}>
                    <p className="text-xs text-slate-500 mb-1">Deteksi di gambar terakhir</p>
                    {aktif && diag?.deteksi?.length ? (
                        <table className="w-full text-left font-mono text-xs">
                            <thead className="text-slate-500"><tr><th className="font-normal py-1">Postur</th><th className="font-normal">Keyakinan</th><th className="font-normal">Kotak (lebar × tinggi)</th></tr></thead>
                            <tbody>
                                {diag.deteksi.map((d, i) => (
                                    <tr key={i} className="border-t border-slate-200 dark:border-slate-800">
                                        <td className="py-1">{d.postur}</td>
                                        <td>{Math.round(d.keyakinan * 100)}%</td>
                                        <td>{d.kotak.length === 4 ? `${d.kotak[2] - d.kotak[0]} × ${d.kotak[3] - d.kotak[1]} px` : '–'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : <p className="font-mono">{aktif ? 'tidak ada deteksi' : '–'}</p>}
                </div>
                <div className={`${kartu} space-y-1`}>
                    <p><span className="text-xs text-slate-500">Hitungan berbaring</span><br />
                        <span className="tabular-nums">{mmss(durasi)}{ambang ? ` dari ${mmss(ambang)}` : ''}</span></p>
                    <p><span className="text-xs text-slate-500">Waktu inferensi</span><br />
                        <span className="tabular-nums">{diag?.inferensi_ms != null ? `${Math.round(diag.inferensi_ms)} ms per gambar` : '–'}</span></p>
                    <p><span className="text-xs text-slate-500">Gambar per detik</span><br />
                        <span className="tabular-nums">
                            {aktif ? `ditangkap ${Math.round(diag?.fps_tangkap ?? live?.fps ?? 0)} · dianalisis ${Math.round(diag?.fps_analisis ?? 0)}` : 'kamera tidak mengirim gambar'}
                        </span></p>
                </div>
            </div>

            <div className={`${kartu} mt-3 text-sm`}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h2 className="font-semibold">Skrip uji posisi kamera</h2>
                    <span className="text-xs text-slate-500">Bacaan sekarang: <b className="font-semibold">{status.label}</b></span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                    Nyalakan Mode uji dulu: alarm selama uji dicatat sebagai latihan, tidak dihitung, dan tidak dikirim ke
                    Telegram kecuali latihan dinyalakan di Pengaturan. Gunakan relawan yang setuju, bukan penghuni.
                </p>
                <ol className="list-decimal pl-5 mt-2 space-y-1">
                    {SKRIP_UJI.map((l) => <li key={l}>{l}</li>)}
                </ol>
            </div>
        </div>
    );
}
