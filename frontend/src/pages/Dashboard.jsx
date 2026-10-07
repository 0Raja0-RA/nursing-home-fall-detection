import { useWebSocket } from '../hooks/useWebSocket';
import CameraFeedCard from '../components/CameraFeedCard';
import AlertBanner from '../components/AlertBanner';

export default function Dashboard() {
    const { cameraData, alerts, acknowledgeAlert } = useWebSocket('ws://localhost:8000/ws');

    // Sinkronisasi ID dengan backend (cam-01)
    const cameras = [
        { id: 'cam-01', name: 'Kamera Utama (Laptop)', status: cameraData['cam-01']?.fall_state || 'monitoring', url: 'http://localhost:8000/api/cameras/cam-01/stream' },
        { id: 'cam-02', name: 'Kamar 02', status: cameraData['cam-02']?.fall_state || 'monitoring', url: '' },
        { id: 'cam-03', name: 'Ruang Makan', status: cameraData['cam-03']?.fall_state || 'monitoring', url: '' },
        { id: 'cam-04', name: 'Lorong Timur', status: cameraData['cam-04']?.fall_state || 'monitoring', url: '' },
    ];

    return (
        <div className="min-h-screen bg-slate-950 text-slate-300 p-6">
            <AlertBanner alerts={alerts} onAcknowledge={acknowledgeAlert} />

            <header className="mb-8">
                <h1 className="text-2xl font-bold text-slate-100">Live Monitoring Panti Jompo</h1>
                <p className="text-slate-400">Sistem Deteksi Jatuh Real-time</p>
            </header>

            {/* Grid 2x2 untuk kamera */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {cameras.map(cam => (
                    <CameraFeedCard
                        key={cam.id}
                        id={cam.id}
                        name={cam.name}
                        status={cam.status}
                        streamUrl={cam.url}
                    />
                ))}
            </div>
        </div>
    );
}