import { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, Video, BellRing } from 'lucide-react';

export default function SimulationDashboard({ addHistoryItem }) {
    const [simulationState, setSimulationState] = useState('normal'); // 'normal', 'falling', 'alerted'
    const [countdown, setCountdown] = useState(10);
    const [note, setNote] = useState('');
    const [activeAlert, setActiveAlert] = useState(false);

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

    const handleResolveAlert = (statusType) => {
        setActiveAlert(false);
        setSimulationState('normal');
        setCountdown(10);

        // Masukkan ke history
        addHistoryItem({
            id: Date.now(),
            location: 'Kamar 02',
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
                    disabled={simulationState !== 'normal'}
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
                            <h2 className="text-red-600 dark:text-red-400 font-bold text-lg">DARURAT TERKONFIRMASI: Kamar 02</h2>
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

            {/* Grid CCTV */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 w-full">
                {/* Kamera 1: Normal */}
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                    <div className="p-3 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
                        <span className="font-semibold text-sm flex items-center gap-2"><Video className="w-4 h-4 text-emerald-500" /> Kamar 01 (Normal)</span>
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500">Normal</span>
                    </div>
                    <div className="aspect-video bg-slate-950 relative flex items-center justify-center text-slate-600">
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end p-4">
                            <span className="text-xs text-white font-mono bg-black/40 px-2 py-1 rounded">YOLO Confidence: 94% (Person)</span>
                        </div>
                        <p className="text-sm">Live Stream Kamera Aktif</p>
                    </div>
                </div>

                {/* Kamera 2: Simulasi Jatuh */}
                <div className={`bg-white dark:bg-slate-900 rounded-2xl border overflow-hidden shadow-sm transition-all ${simulationState !== 'normal' ? 'border-red-500 ring-2 ring-red-500/20' : 'border-slate-200 dark:border-slate-800'}`}>
                    <div className="p-3 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
                        <span className="font-semibold text-sm flex items-center gap-2"><Video className="w-4 h-4 text-emerald-500" /> Kamar 02 (Simulasi Jatuh)</span>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${simulationState === 'normal' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500 animate-pulse'}`}>
                            {simulationState === 'normal' ? 'Normal' : `JATUH TERDETEKSI (${countdown}s)`}
                        </span>
                    </div>
                    <div className="aspect-video bg-slate-950 relative flex flex-col items-center justify-center text-slate-400 p-4">
                        {simulationState !== 'normal' && (
                            <div className="absolute inset-0 bg-red-950/30 flex flex-col items-center justify-center">
                                <div className="border-2 border-red-500 bg-red-500/20 p-6 rounded-xl text-center animate-pulse">
                                    <p className="text-red-400 font-bold text-lg">⚠️ STATE: LYING_ON_GROUND</p>
                                    <p className="text-white text-2xl font-mono mt-1">Timer Alarm: {countdown} Detik</p>
                                </div>
                            </div>
                        )}
                        <p className="text-sm">Kamera Pengawas Sudut Kamar 02</p>
                    </div>
                </div>
            </div>
        </div>
    );
}