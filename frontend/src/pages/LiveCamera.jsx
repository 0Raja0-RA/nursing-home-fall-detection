import { useState, useEffect, useRef } from 'react';
import { RefreshCw, AlertTriangle, Video } from 'lucide-react';

import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';

// Halaman ini menampilkan satu kamera untuk diuji dari dekat. Kameranya dipilih
// lewat dropdown di kanan atas. Status, postur, dan hitungan durasinya datang dari
// backend (state machine yang sama dengan deteksi sungguhan), bukan tiruan di
// browser -- dulu halaman ini punya hitung mundur palsu yang tidak tersambung ke
// sistem. Alarm jatuh ditampilkan oleh AlertBanner global di semua halaman.

const STATUS = {
    monitoring: { label: 'NORMAL', kelas: 'bg-emerald-500/80 text-white' },
    possible_fall: { label: 'WASPADA', kelas: 'bg-amber-500/90 text-white animate-pulse' },
    confirmed_fall: { label: 'JATUH TERDETEKSI', kelas: 'bg-red-600/90 text-white animate-pulse' },
    unknown: { label: 'TERPUTUS', kelas: 'bg-slate-600/90 text-white' },
};

export default function LiveCamera() {
    const [rotasi, setRotasi] = useState(0); // derajat tampilan, untuk tombol "Putar Kamera"
    const [errorMsg, setErrorMsg] = useState('');
    const [daftarKamera, setDaftarKamera] = useState([]);
    const [kameraId, setKameraId] = useState('');
    const [memulai, setMemulai] = useState(false);

    const { cameraData } = useLive();

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

    // Minta backend menganggap kamera ini melaporkan postur pemicu. State machine
    // tetap menghitung durasinya sendiri; alarm muncul setelah ambang terlewati.
    const simulateFall = async () => {
        if (!kameraId || memulai) return;
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

    const live = cameraData?.[kameraId];
    const kamera = daftarKamera.find((c) => c.camera_id === kameraId);
    const aktif = kamera?.is_active ?? false;
    const state = !aktif ? 'unknown' : (live?.fall_state || 'monitoring');
    const info = STATUS[state] || STATUS.monitoring;
    const durasi = live?.fall_duration ?? 0;
    const menghitung = state === 'possible_fall' || state === 'confirmed_fall';
    const posture = live?.current_posture;
    const conf = live?.confidence ?? 0;

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Testing Kamera Perangkat (HP/Laptop)</h1>
                    <p className="text-xs md:text-sm text-slate-500">Uji coba langsung deteksi postur menggunakan kamera perangkat keras secara real-time.</p>
                </div>
                <div className="flex items-center gap-3">
                    <select
                        value={kameraId}
                        onChange={(e) => setKameraId(e.target.value)}
                        title="Pilih kamera yang ingin diuji"
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
                        <RefreshCw className="w-4 h-4" /> Putar Kamera
                    </button>
                    <button
                        onClick={simulateFall}
                        disabled={memulai || !aktif}
                        className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl text-xs md:text-sm font-medium flex items-center gap-2 transition-colors shadow-lg shadow-red-600/25"
                    >
                        <AlertTriangle className="w-4 h-4" /> Simulasi Deteksi Jatuh
                    </button>
                </div>
            </div>

            {errorMsg && (
                <div className="mb-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm">
                    {errorMsg}
                </div>
            )}

            {/* Tampilan Stream Kamera Utama */}
            <div className="relative bg-slate-950 rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl aspect-video flex items-center justify-center">
                <img
                    ref={imgRef}
                    alt="Video dari backend"
                    onLoad={() => setErrorMsg('')}
                    onError={() => setErrorMsg('Video backend tidak dapat dimuat. Pastikan run-backend.bat sedang berjalan dan kameranya terbaca.')}
                    style={{ transform: `rotate(${rotasi}deg)` }}
                    className="w-full h-full object-contain transition-transform"
                />

                {/* Status dari backend */}
                <div className="absolute top-4 left-4 flex items-center gap-2">
                    <span className={`px-3 py-1.5 rounded-full text-xs font-bold tracking-wide uppercase backdrop-blur-md shadow-lg ${info.kelas}`}>
                        {menghitung ? `${info.label} — ${durasi.toFixed(1)}s` : `Status: ${info.label}`}
                    </span>
                </div>

                <div className="absolute bottom-4 left-4 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-xl text-xs text-white font-mono">
                    {aktif
                        ? (posture ? `YOLO: ${posture} ${(conf * 100).toFixed(0)}%` : 'YOLO: tidak ada deteksi')
                        : 'Kamera terputus'}
                </div>

                <div className="absolute bottom-4 right-4 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-xl text-xs text-white font-mono flex items-center gap-2">
                    <Video className={`w-3.5 h-3.5 ${aktif ? 'text-emerald-400' : 'text-slate-400'}`} />
                    {aktif ? 'Stream MJPEG dari backend' : 'Tidak ada stream'}
                </div>
            </div>
        </div>
    );
}
