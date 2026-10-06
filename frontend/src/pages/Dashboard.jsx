import { useWebSocket } from '../hooks/useWebSocket';
import CameraFeedCard from '../components/CameraFeedCard';
import AlertBanner from '../components/AlertBanner';

export default function Dashboard() {
    const { cameraData, alerts, acknowledgeAlert } = useWebSocket('ws://localhost:8000/ws');

    // Mock data untuk kamera jika belum ada data dari backend
    const cameras = [
        { id: 'cam1', name: 'Kamar 01', status: cameraData['cam1']?.status || 'normal', url: '/mock-stream-1.jpg' },
        { id: 'cam2', name: 'Kamar 02', status: cameraData['cam2']?.status || 'lying_on_ground', url: '/mock-stream-2.jpg' },
        { id: 'cam3', name: 'Ruang Makan', status: cameraData['cam3']?.status || 'normal', url: '/mock-stream-3.jpg' },
        { id: 'cam4', name: 'Lorong Timur', status: cameraData['cam4']?.status || 'transitional', url: '/mock-stream-4.jpg' },
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