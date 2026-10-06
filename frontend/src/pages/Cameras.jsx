import { useState } from 'react';
import { Camera, Plus, Trash2, CheckCircle2, Video } from 'lucide-react';

export default function Cameras() {
    const [cameras, setCameras] = useState([
        { id: 'cam1', name: 'Kamar 01 (Jenderal Ilham)', url: 'rtsp://192.168.1.101:554/stream1', status: 'connected' },
        { id: 'cam2', name: 'Kamar 02 (Nyonya Laila)', url: 'rtsp://192.168.1.102:554/stream1', status: 'connected' },
        { id: 'cam3', name: 'Kamar 03 (Kanjeng Ratu Kadek)', url: 'rtsp://192.168.1.102:554/stream1', status: 'connected' },
        { id: 'cam4', name: 'Kamar 04 (Kolonel Raja)', url: 'rtsp://192.168.1.102:554/stream1', status: 'connected' },
    ]);
    const [newName, setNewName] = useState('');
    const [newUrl, setNewUrl] = useState('');

    const handleAddCamera = (e) => {
        e.preventDefault();
        if (!newName || !newUrl) return;
        const newCam = {
            id: `cam${Date.now()}`,
            name: newName,
            url: newUrl,
            status: 'connected'
        };
        setCameras([...cameras, newCam]);
        setNewName('');
        setNewUrl('');
    };

    const handleDelete = (id) => {
        setCameras(cameras.filter(c => c.id !== id));
    };

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="mb-6">
                <h1 className="text-2xl font-bold">Manajemen Kamera CCTV</h1>
                <p className="text-sm text-slate-500">Hubungkan dan kelola stream RTSP atau IP Camera dari setiap kamar lansia.</p>
            </div>

            {/* Form Tambah Kamera */}
            <form onSubmit={handleAddCamera} className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 mb-8 grid grid-cols-1 md:grid-cols-3 gap-4 items-end shadow-sm">
                <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">Nama Lokasi / Kamar</label>
                    <input
                        type="text"
                        placeholder="Contoh: Kamar 01 - Jenderal Ilham"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500"
                    />
                </div>
                <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">URL RTSP Stream</label>
                    <input
                        type="text"
                        placeholder="rtsp://192.168.x.x:554/live"
                        value={newUrl}
                        onChange={(e) => setNewUrl(e.target.value)}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 font-mono"
                    />
                </div>
                <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 transition-colors text-sm shadow-md shadow-blue-600/20">
                    <Plus className="w-4 h-4" /> Tambah Kamera
                </button>
            </form>

            {/* Daftar Kamera Terhubung */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                <div className="p-4 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center gap-2">
                    <Video className="w-4 h-4 text-blue-500" /> Daftar Kamera Aktif
                </div>
                <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {cameras.map((cam) => (
                        <div key={cam.id} className="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
                                    <Camera className="w-5 h-5" />
                                </div>
                                <div>
                                    <h3 className="font-medium text-sm">{cam.name}</h3>
                                    <p className="text-xs text-slate-500 font-mono">{cam.url}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                                    <CheckCircle2 className="w-3.5 h-3.5" /> Terhubung
                                </span>
                                <button onClick={() => handleDelete(cam.id)} className="text-slate-400 hover:text-red-500 transition-colors p-2">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}