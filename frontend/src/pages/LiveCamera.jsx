import { useState, useEffect, useRef } from 'react';
import { Camera, RefreshCw, AlertTriangle, Video, CheckCircle2 } from 'lucide-react';

import { API_BASE } from '../config';

// Halaman ini menampilkan satu kamera untuk diuji dari dekat. Kameranya dipilih
// sendiri lewat dropdown di kanan atas, bukan dikunci ke cam-01 seperti sebelumnya
// -- dulu halaman ini selalu menampilkan kamera pertama (biasanya webcam laptop)
// walaupun kamera HP sudah terdaftar.

export default function LiveCamera({ addHistoryItem }) {
    const [rotasi, setRotasi] = useState(0); // derajat tampilan, untuk tombol "Putar Kamera"
    const [errorMsg, setErrorMsg] = useState('');
    const [daftarKamera, setDaftarKamera] = useState([]);
    const [kameraId, setKameraId] = useState('');

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
        // pernah memasangnya kembali karena prop-nya dianggap tidak berubah. Akibatnya
        // gambar kosong selamanya dengan net::ERR_ABORTED.
        el.src = `${API_BASE}/api/cameras/${kameraId}/stream`;
        return () => { el.src = ''; };
    }, [kameraId]);

    // Status deteksi model simulasi
    const [detectionStatus, setDetectionStatus] = useState('normal'); // 'normal', 'lying'
    const [countdown, setCountdown] = useState(10);
    const [activeAlert, setActiveAlert] = useState(false);
    const [note, setNote] = useState('');

    // Memutar tampilan 90 derajat setiap kali ditekan. Ini hanya memutar gambar di layar;
    // rotasi yang dipakai model diatur lewat CAMERA_ROTATE di run-backend.bat.
    const switchCamera = () => setRotasi(prev => (prev + 90) % 360);

    // State Machine Timer Hitung Mundur Simulasi Jatuh
    useEffect(() => {
        let timer;
        if (detectionStatus === 'lying' && countdown > 0) {
            timer = setInterval(() => setCountdown(c => c - 1), 1000);
        } else if (detectionStatus === 'lying' && countdown === 0) {
            setActiveAlert(true);
        }
        return () => clearInterval(timer);
    }, [detectionStatus, countdown]);

    const simulateFall = () => {
        setDetectionStatus('lying');
        setCountdown(10);
    };

    const handleResolve = () => {
        setActiveAlert(false);
        setDetectionStatus('normal');
        setCountdown(10);

        addHistoryItem({
            id: Date.now(),
            location: 'Kamera HP (Testing Dosen)',
            time: new Date().toLocaleString(),
            status: 'confirmed',
            note: note || 'Insiden jatuh dikonfirmasi via pengujian kamera HP.'
        });
        setNote('');
    };

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
                        disabled={detectionStatus === 'lying'}
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

            {/* Banner Darurat Interaktif */}
            {activeAlert && (
                <div className="mb-6 bg-red-500/10 border-2 border-red-500 p-5 rounded-2xl animate-pulse flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                        <h2 className="text-red-600 dark:text-red-400 font-bold text-lg">⚠️ DARURAT TERKONFIRMASI: Lansia Jatuh!</h2>
                        <p className="text-sm text-slate-600 dark:text-slate-300">Batas waktu terlampaui. Sistem mencatat insiden.</p>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
                        <input
                            type="text"
                            placeholder="Catatan kondisi (opsional)..."
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl px-3 py-2 text-sm"
                        />
                        <button
                            onClick={handleResolve}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap"
                        >
                            Tandai Selesai
                        </button>
                    </div>
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

                {/* Status Overlay */}
                <div className="absolute top-4 left-4 flex items-center gap-2">
                    <span className={`px-3 py-1.5 rounded-full text-xs font-bold tracking-wide uppercase backdrop-blur-md shadow-lg ${detectionStatus === 'normal' ? 'bg-emerald-500/80 text-white' : 'bg-red-600/90 text-white animate-pulse'
                        }`}>
                        {detectionStatus === 'normal' ? 'Status: NORMAL (0)' : `STATUS: LYING ON GROUND (1) - ${countdown}s`}
                    </span>
                </div>

                {detectionStatus === 'lying' && (
                    <div className="absolute inset-12 border-4 border-dashed border-red-500 bg-red-500/10 rounded-2xl flex items-center justify-center pointer-events-none animate-pulse">
                        <div className="bg-red-950/80 text-red-200 px-4 py-2 rounded-xl font-mono text-sm border border-red-500">
                            YOLO11 Detection: [Class: lying_on_ground | Conf: 0.96]
                        </div>
                    </div>
                )}

                <div className="absolute bottom-4 right-4 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-xl text-xs text-white font-mono flex items-center gap-2">
                    <Video className="w-3.5 h-3.5 text-emerald-400" /> Live WebRTC Stream Active
                </div>
            </div>
        </div>
    );
}