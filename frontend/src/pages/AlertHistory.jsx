import { useState, useEffect } from 'react';
import { Clock, MapPin, AlertTriangle } from 'lucide-react';

export default function AlertHistory() {
    const [history, setHistory] = useState([]);

    // Simulasi fetch data dari backend REST API
    useEffect(() => {
        const mockHistory = [
            { id: 1, location: 'Kamar 02', time: '2026-10-02 14:30:00', status: 'resolved', note: 'False alarm, lansia mengambil barang.' },
            { id: 2, location: 'Kamar 05', time: '2026-10-01 02:15:22', status: 'confirmed', note: 'Jatuh dari tempat tidur. Tim medis sudah menangani.' },
            { id: 3, location: 'Lorong Timur', time: '2026-09-29 18:45:10', status: 'confirmed', note: 'Terpeleset air.' },
        ];
        setHistory(mockHistory);
    }, []);

    return (
        <div className="min-h-screen bg-slate-950 p-6 text-slate-300">
            <h1 className="text-2xl font-bold text-slate-100 mb-6">Riwayat Insiden</h1>

            <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 text-sm uppercase tracking-wider">
                                <th className="p-4 font-medium">Waktu Kejadian</th>
                                <th className="p-4 font-medium">Lokasi Kamera</th>
                                <th className="p-4 font-medium">Status Validasi</th>
                                <th className="p-4 font-medium">Catatan Caregiver</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                            {history.map((item) => (
                                <tr key={item.id} className="hover:bg-slate-800/50 transition-colors">
                                    <td className="p-4 flex items-center gap-2">
                                        <Clock className="w-4 h-4 text-slate-500" />
                                        {item.time}
                                    </td>
                                    <td className="p-4">
                                        <div className="flex items-center gap-2">
                                            <MapPin className="w-4 h-4 text-slate-500" />
                                            {item.location}
                                        </div>
                                    </td>
                                    <td className="p-4">
                                        {item.status === 'confirmed' ? (
                                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                                                <AlertTriangle className="w-3.5 h-3.5" /> Konfirmasi Jatuh
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
                                                Aman / False Alarm
                                            </span>
                                        )}
                                    </td>
                                    <td className="p-4 text-sm text-slate-400">{item.note}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}