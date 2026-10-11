import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Video } from 'lucide-react';
import { API_BASE } from '../config';
import { useLive } from '../context/LiveContext';

// Label dan warna pil status, mengikuti state machine di backend.
const STATUS = {
    monitoring: { label: 'Normal', kelas: 'bg-emerald-500/10 text-emerald-500' },
    possible_fall: { label: 'Waspada', kelas: 'bg-amber-500/10 text-amber-500 animate-pulse' },
    confirmed_fall: { label: 'JATUH TERDETEKSI', kelas: 'bg-red-500/10 text-red-500 animate-pulse' },
    unknown: { label: 'Terputus', kelas: 'bg-slate-500/10 text-slate-400' },
};

/**
 * Gambar MJPEG dari backend, yang melepas koneksinya saat dilepas dari DOM.
 *
 * MJPEG adalah respons HTTP yang tidak pernah selesai. Kalau elemen <img>-nya
 * dibuang tanpa mengosongkan src lebih dulu, browser menahan koneksi itu tetap
 * terbuka. Dengan beberapa kamera dan beberapa kali berpindah halaman, batas ~6
 * koneksi per host milik Chrome habis -- fetch berikutnya menggantung dan seluruh
 * dashboard terlihat membeku, padahal backend baik-baik saja.
 */
function StreamImg({ src, alt }) {
    const ref = useRef(null);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        // src dipasang di sini, bukan lewat atribut JSX. React.StrictMode menjalankan
        // efek dua kali di mode dev (pasang -> bersihkan -> pasang lagi); kalau src
        // ditulis di JSX, pembersihan pertama membatalkan permintaan dan React tidak
        // pernah memasangnya kembali karena prop-nya dianggap tidak berubah. Akibatnya
        // gambar kosong selamanya dengan net::ERR_ABORTED.
        el.src = src;
        return () => { el.src = ''; };
    }, [src]);
    return <img ref={ref} alt={alt} className="absolute inset-0 w-full h-full object-contain" />;
}

export default function SimulationDashboard() {
    const [cameras, setCameras] = useState([]);
    const [kameraSimulasiId, setKameraSimulasiId] = useState('');
    const [memulaiSimulasi, setMemulaiSimulasi] = useState(false);
    const [galat, setGalat] = useState('');

    // Alarm jatuh ditampilkan oleh AlertBanner global; halaman ini hanya butuh
    // status per kamera.
    const { cameraData } = useLive();

    // Daftar kamera diambil dari backend, jadi kamera yang didaftarkan di halaman
    // "Kelola Kamera" langsung muncul di sini tanpa menyunting kode.
    const ambilDaftar = useCallback(async () => {
        try {
            const r = await fetch(`${API_BASE}/api/cameras/`);
            if (r.ok) setCameras(await r.json());
        } catch { /* backend belum jalan; grid tampil kosong dengan petunjuk */ }
    }, []);

    useEffect(() => {
        // Berlangganan ke sistem luar (backend). setState-nya terjadi di callback async
        // setelah fetch selesai, bukan sinkron -- linter tidak bisa menelusuri ke sana.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambilDaftar();
        const t = setInterval(ambilDaftar, 5000);
        return () => clearInterval(t);
    }, [ambilDaftar]);

    // Pilihan awal: kamera pertama yang benar-benar mengalir.
    useEffect(() => {
        if (!kameraSimulasiId && cameras.length) {
            // Menyelaraskan pilihan dengan daftar yang baru tiba dari backend.
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setKameraSimulasiId((cameras.find((c) => c.is_active) || cameras[0]).camera_id);
        }
    }, [cameras, kameraSimulasiId]);

    /**
     * Minta backend menganggap satu kamera melaporkan postur pemicu.
     *
     * Yang disimulasikan hanya keluaran detektor. State machine tetap menghitung
     * durasinya sendiri, debounce tetap berlaku, cooldown tetap dihormati, dan
     * alertnya melewati jalur yang sama dengan deteksi sungguhan -- termasuk foto
     * frame kamera saat itu juga. Hitungan mundur di kartu pun jadi angka asli
     * dari state machine, bukan tiruan di browser.
     */
    const triggerFallSimulation = async () => {
        if (!kameraSimulasiId || memulaiSimulasi) return;
        setMemulaiSimulasi(true);
        setGalat('');
        try {
            const r = await fetch(
                `${API_BASE}/api/cameras/${kameraSimulasiId}/simulate-fall`,
                { method: 'POST' },
            );
            if (!r.ok) {
                const b = await r.json().catch(() => ({}));
                setGalat(typeof b.detail === 'string' ? b.detail : `Backend menjawab ${r.status}`);
            }
        } catch {
            setGalat(`Tidak bisa menghubungi backend di ${API_BASE}.`);
        } finally {
            setMemulaiSimulasi(false);
        }
    };

    const kameraSimulasi = cameras.find((c) => c.camera_id === kameraSimulasiId) || cameras[0];

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Simulasi Live Monitoring CCTV</h1>
                    <p className="text-xs md:text-sm text-slate-500">Uji coba deteksi model YOLO11</p>
                </div>
                <div className="flex items-center gap-3">
                    <select
                        value={kameraSimulasiId}
                        onChange={(e) => setKameraSimulasiId(e.target.value)}
                        title="Kamera yang akan disimulasikan"
                        className="bg-slate-200 dark:bg-slate-800 px-3 py-2 rounded-xl text-xs md:text-sm font-medium focus:outline-none"
                    >
                        {cameras.length === 0 && <option value="">Belum ada kamera</option>}
                        {cameras.map((c) => (
                            <option key={c.camera_id} value={c.camera_id}>
                                {c.name}{c.is_active ? '' : ' (terputus)'}
                            </option>
                        ))}
                    </select>
                    <button
                        onClick={triggerFallSimulation}
                        disabled={memulaiSimulasi || !kameraSimulasi?.is_active}
                        className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl font-medium text-xs md:text-sm transition-colors flex items-center gap-2 shadow-md"
                    >
                        <AlertTriangle className="w-4 h-4" /> Trigger Simulasi Orang Jatuh
                    </button>
                </div>
            </div>

            {galat && (
                <div className="mb-6 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-500 text-sm">
                    {galat}
                </div>
            )}

            {/* Grid CCTV — satu kartu per kamera yang terdaftar di halaman Kelola Kamera */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full">
                {cameras.length === 0 && (
                    <div className="lg:col-span-2 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center text-sm text-slate-500 shadow-sm">
                        Belum ada kamera yang terdaftar. Tambahkan di halaman <strong>Kelola Kamera</strong>,
                        dan kamera itu akan langsung muncul di sini.
                    </div>
                )}

                {cameras.map((cam) => {
                    // Status langsung dari WebSocket kalau ada, kalau tidak dari hasil polling.
                    const live = cameraData?.[cam.camera_id];
                    const state = !cam.is_active ? 'unknown' : (live?.fall_state || cam.fall_state || 'monitoring');
                    const info = STATUS[state] || STATUS.monitoring;
                    const posture = live?.current_posture ?? cam.current_posture;
                    const conf = live?.confidence ?? cam.confidence ?? 0;

                    // Overlay simulasi hanya menempel di kamera pertama, seperti sebelumnya.
                    const durasi = live?.fall_duration ?? cam.fall_duration ?? 0;
                    const menghitung = state === 'possible_fall' || state === 'confirmed_fall';
                    const bahaya = menghitung;

                    return (
                        <div
                            key={cam.camera_id}
                            className={`bg-white dark:bg-slate-900 rounded-2xl border overflow-hidden shadow-sm transition-all ${
                                bahaya ? 'border-red-500 ring-2 ring-red-500/20' : 'border-slate-200 dark:border-slate-800'
                            }`}
                        >
                            <div className="p-3 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
                                <span className="font-semibold text-sm flex items-center gap-2">
                                    <Video className={`w-4 h-4 ${cam.is_active ? 'text-emerald-500' : 'text-slate-500'}`} />
                                    {cam.name}
                                </span>
                                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${info.kelas}`}>
                                    {menghitung ? `${info.label} (${durasi.toFixed(1)}s)` : info.label}
                                </span>
                            </div>

                            <div className="aspect-video bg-slate-950 relative flex items-center justify-center text-slate-400">
                                {cam.is_active ? (
                                    <StreamImg src={`${API_BASE}${cam.stream_url}`} alt={`Stream ${cam.name}`} />
                                ) : (
                                    <p className="text-sm px-4 text-center">
                                        Kamera terputus — periksa alamatnya di halaman Kelola Kamera.
                                    </p>
                                )}

                                {menghitung && (
                                    <div className="absolute inset-0 bg-red-950/40 flex flex-col items-center justify-center">
                                        <div className="border-2 border-red-500 bg-red-500/20 p-6 rounded-xl text-center animate-pulse">
                                            <p className="text-red-400 font-bold text-lg">⚠️ STATE: {state.toUpperCase()}</p>
                                            <p className="text-white text-2xl font-mono mt-1">Timer Alarm: {durasi.toFixed(1)} Detik</p>
                                        </div>
                                    </div>
                                )}

                                {cam.is_active && (
                                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent flex items-end p-4">
                                        <span className="text-xs text-white font-mono bg-black/40 px-2 py-1 rounded">
                                            {posture
                                                ? `YOLO: ${posture} ${(conf * 100).toFixed(0)}%`
                                                : 'YOLO: tidak ada deteksi'}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
