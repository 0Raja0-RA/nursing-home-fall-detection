import { AlertTriangle, X } from 'lucide-react';

export default function AlertBanner({ alerts, onAcknowledge }) {
    if (!alerts || alerts.length === 0) return null;

    return (
        <div className="fixed top-4 right-4 z-50 flex flex-col gap-3 w-96">
            {alerts.map((alert) => (
                <div key={alert.id} className="bg-red-950 border border-red-500 p-4 rounded-lg shadow-2xl flex items-start gap-4 animate-in slide-in-from-top-5">
                    <AlertTriangle className="text-red-500 animate-pulse w-6 h-6 flex-shrink-0" />
                    <div className="flex-1">
                        <h3 className="text-red-500 font-bold text-lg">DARURAT: Lansia Terjatuh!</h3>
                        <p className="text-red-200 text-sm">{alert.location} - Deteksi dikonfirmasi.</p>
                        <button
                            onClick={() => onAcknowledge(alert.id)}
                            className="mt-3 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
                        >
                            Acknowledge (Tandai Aman)
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
}