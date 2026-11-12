import { useState, useEffect, useRef } from 'react';
import { RefreshCw, FlaskConical } from 'lucide-react';

import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';
import { usePengaturan } from '../hooks/usePengaturan';
import StatusKamera from '../components/StatusKamera';
import { bacaStatus, mmss } from '../statusKamera';

// Halaman ini menampilkan satu kamera untuk diuji dari dekat. Kameranya dipilih
// lewat dropdown di kanan atas. Status, postur, dan hitungan durasinya datang dari
// backend (state machine yang sama dengan deteksi sungguhan), bukan tiruan di
// browser. Alarm jatuh ditampilkan oleh AlertBanner global di semua halaman.
//
// Di atas video hanya ada satu bacaan status. Keluaran mentah model, yang berguna
// saat menguji tetapi membingungkan bila bertabrakan dengan status, ada di panel
// di bawah video.

export default function LiveCamera() {
    const [rotasi, setRotasi] = useState(0); // derajat tampilan, untuk tombol "Putar Kamera"
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
                const r = await fetch(`${API_BASE}/api/cameras/`);
                if (!r.ok || batal) return;
                const d = await r.json();
                setDaftarKamera(d);
                // Pilihan awal: kamera pertama yang benar-benar mengalir.
                setKameraId((k) => k || (d.find((c) => c.is_active) || d[0])?.camera_id || '');
            } catch { /* backend belum jalan */ }
        };
        ambil();
        const t = setInterval(ambil, 5000);
        return () => { batal = true; clearInterval(t); };
    }, []);

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
    // rotasi yang dipakai model diatur per kamera di halaman Kelola Kamera.
    const switchCamera = () => setRotasi((prev) => (prev + 90) % 360);

    const live = cameraData?.[kameraId];
    const kamera = daftarKamera.find((c) => c.camera_id === kameraId);
    const aktif = (kamera?.is_active ?? false) && (live?.is_active ?? true);
    const state = !aktif ? 'unknown' : (live?.fall_state || 'monitoring');
    const durasi = live?.fall_duration ?? 0;
    const posture = live?.current_posture;
    const conf = live?.confidence ?? 0;
    const ambang = pengaturan?.fall_duration_threshold;
    const status = bacaStatus({
        aktif, state, adaOrang: Boolean(posture), durasi, ambang, latihan: Boolean(live?.simulated),
    });

    // Minta backend menganggap kamera ini melaporkan postur pemicu. State machine
    // tetap menghitung durasinya sendiri; alarm muncul setelah ambang terlewati.
    const mulaiLatihan = async () => {
        if (!kameraId || memulai) return;
        const setuju = window.confirm(
            `Mulai latihan jatuh di ${kamera?.name || kameraId}? Banner, riwayat, dan pesan Telegram akan bertanda SIMULASI.`,
        );
        if (!setuju) return;
        setMemulai(true);
        setErrorMsg('');
        try {
            const r = await fetch(`${API_BASE}/api/cameras/${kameraId}/simulate-fall`, { method: 'POST' });
            if (!r.ok) {
                const b = await r.json().catch(() => ({}));
                setErrorMsg(typeof b.detail === 'string' ? b.detail : `Backend menjawab ${r.status}`);
            }
        } catch {
            setErrorMsg(`Tidak bisa menghubungi backend di ${API_BASE}.`);
        } finally {
            setMemulai(false);
        }
    };

    const kartu = 'rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-3';

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Testing Kamera HP</h1>
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
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                <div className={kartu}>
                    <p className="text-xs text-slate-500">Keluaran model</p>
                    <p className="font-mono mt-0.5">
                        {aktif ? (posture ? `${posture} · ${(conf * 100).toFixed(0)}%` : 'tidak ada deteksi') : '–'}
                    </p>
                </div>
                <div className={kartu}>
                    <p className="text-xs text-slate-500">Hitungan berbaring</p>
                    <p className="mt-0.5 tabular-nums">{mmss(durasi)}{ambang ? ` dari ${mmss(ambang)}` : ''}</p>
                </div>
                <div className={kartu}>
                    <p className="text-xs text-slate-500">Video</p>
                    <p className="mt-0.5 tabular-nums">
                        {aktif ? `Dari server · ${Math.round(live?.fps ?? 0)} fps` : 'Kamera tidak mengirim gambar'}
                    </p>
                </div>
            </div>
        </div>
    );
}
