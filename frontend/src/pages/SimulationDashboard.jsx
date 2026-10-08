import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, BellRing, Video } from 'lucide-react';
import { API_BASE } from '../config';
import { useWebSocket } from '../hooks/useWebSocket';
import { WS_URL } from '../config';

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
        return () => { if (el) el.src = ''; };
    }, []);
    return <img ref={ref} src={src} alt={alt} className="absolute inset-0 w-full h-full object-contain" />;
}

export default function SimulationDashboard({ addHistoryItem }) {
    const [simulationState, setSimulationState] = useState('normal'); // 'normal', 'falling', 'alerted'
    const [countdown, setCountdown] = useState(10);
    const [note, setNote] = useState('');
    const [activeAlert, setActiveAlert] = useState(false);
    const [cameras, setCameras] = useState([]);

    const { cameraData } = useWebSocket(WS_URL);

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

    // Simulasi hitung mundur state machine saat tombol jatuh ditekan
    useEffect(() => {
        let timer;
        if (simulationState === 'falling' && countdown > 0) {
            timer = setInterval(() => setCountdown(c => c - 1), 1000);
        } else if (simulationState === 'falling' && countdown === 0) {
            setSimulationState('alerted');
            setActiveAlert(true);
        }
        return () => clearInterval(timer);
    }, [simulationState, countdown]);

    const triggerFallSimulation = () => {
        setSimulationState('falling');
        setCountdown(10);
    };

    // Kamera yang dipakai untuk overlay simulasi: yang pertama di daftar.
    const kameraSimulasi = cameras[0];

    const handleResolveAlert = (statusType) => {
        setActiveAlert(false);
        setSimulationState('normal');
        setCountdown(10);

        addHistoryItem({
            id: Date.now(),
            location: kameraSimulasi?.name || 'Kamera simulasi',
            time: new Date().toLocaleString(),
            status: statusType,
            note: note || 'Dikonfirmasi oleh caregiver via dashboard.'
        });
        setNote('');
    };

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0 overflow-x-hidden">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Simulasi Live Monitoring CCTV</h1>
                    <p className="text-xs md:text-sm text-slate-500">Uji coba deteksi model YOLO11</p>
                </div>
                <button
                    onClick={triggerFallSimulation}
                    disabled={simulationState !== 'normal' || !kameraSimulasi}
                    className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-xl font-medium text-xs md:text-sm transition-colors flex items-center gap-2 shadow-md"
                >
                    <AlertTriangle className="w-4 h-4" /> Trigger Simulasi Orang Jatuh
                </button>
            </div>

            {/* Banner Alert Darurat Aktif */}
            {activeAlert && (
                <div className="mb-6 bg-red-500/10 border-2 border-red-500 p-5 rounded-2xl animate-pulse flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div className="flex items-center gap-3">
                        <BellRing className="w-8 h-8 text-red-500 animate-bounce" />
                        <div>
                            <h2 className="text-red-600 dark:text-red-400 font-bold text-lg">
                                DARURAT TERKONFIRMASI: {kameraSimulasi?.name || 'Kamera simulasi'}
                            </h2>
                            <p className="text-sm text-slate-600 dark:text-slate-300">Durasi jatuh melewati ambang batas. Sistem otomatis mengirim peringatan.</p>
                        </div>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2 w-full md:w-auto">
                        <input
                            type="text"
                            placeholder="Catatan kondisi lansia..."
                            value={note}
                            onChange={(e) => setNote(e.target.value)}
                            className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm"
                        />
                        <button
                            onClick={() => handleResolveAlert('confirmed')}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap"
                        >
                            Tandai Ditangani & Selesai
                        </button>
                    </div>
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

                {cameras.map((cam, i) => {
                    // Status langsung dari WebSocket kalau ada, kalau tidak dari hasil polling.
                    const live = cameraData?.[cam.camera_id];
                    const state = !cam.is_active ? 'unknown' : (live?.fall_state || cam.fall_state || 'monitoring');
                    const info = STATUS[state] || STATUS.monitoring;
                    const posture = live?.current_posture ?? cam.current_posture;
                    const conf = live?.confidence ?? cam.confidence ?? 0;

                    // Overlay simulasi hanya menempel di kamera pertama, seperti sebelumnya.
                    const disimulasikan = i === 0 && simulationState !== 'normal';
                    const bahaya = disimulasikan || state === 'confirmed_fall';

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
                                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                    disimulasikan ? 'bg-red-500/10 text-red-500 animate-pulse' : info.kelas
                                }`}>
                                    {disimulasikan ? `JATUH TERDETEKSI (${countdown}s)` : info.label}
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

                                {disimulasikan && (
                                    <div className="absolute inset-0 bg-red-950/40 flex flex-col items-center justify-center">
                                        <div className="border-2 border-red-500 bg-red-500/20 p-6 rounded-xl text-center animate-pulse">
                                            <p className="text-red-400 font-bold text-lg">⚠️ STATE: LYING_ON_GROUND</p>
                                            <p className="text-white text-2xl font-mono mt-1">Timer Alarm: {countdown} Detik</p>
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
