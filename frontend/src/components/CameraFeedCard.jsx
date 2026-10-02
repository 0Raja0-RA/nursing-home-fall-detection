import { Activity, UserCheck, AlertOctagon } from 'lucide-react';

const statusConfig = {
    normal: { color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500', icon: UserCheck, label: 'Normal' },
    transitional: { color: 'bg-amber-500/20 text-amber-400 border-amber-500', icon: Activity, label: 'Transisi (Waspada)' },
    lying_on_ground: { color: 'bg-red-500/20 text-red-400 border-red-500 animate-pulse', icon: AlertOctagon, label: 'Terjatuh' }
};

export default function CameraFeedCard({ id, name, status = 'normal', streamUrl }) {
    const config = statusConfig[status] || statusConfig.normal;
    const Icon = config.icon;

    return (
        <div className={`relative bg-slate-800 rounded-xl overflow-hidden border ${status === 'lying_on_ground' ? 'border-red-500 shadow-[0_0_15px_rgba(239,68,68,0.3)]' : 'border-slate-700'}`}>
            {/* Container Video Placeholder */}
            <div className="aspect-video bg-slate-900 relative">
                <img src={streamUrl} alt={`Kamera ${name}`} className="w-full h-full object-cover opacity-80" />

                {/* Simulasi Bounding Box YOLO jika terdeteksi jatuh */}
                {status === 'lying_on_ground' && (
                    <div className="absolute top-[40%] left-[30%] w-[40%] h-[30%] border-2 border-red-500 bg-red-500/10" />
                )}
            </div>

            {/* Header & Status Badge */}
            <div className="absolute top-0 left-0 right-0 p-3 flex justify-between items-start bg-gradient-to-b from-black/80 to-transparent">
                <h3 className="text-slate-200 font-semibold drop-shadow-md">{name}</h3>
                <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium backdrop-blur-sm ${config.color}`}>
                    <Icon className="w-3.5 h-3.5" />
                    {config.label}
                </div>
            </div>
        </div>
    );
}