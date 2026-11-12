import { Circle, Diamond, EyeOff, FlaskConical, TriangleAlert, VideoOff } from 'lucide-react';

// Tiap status punya bentuk, warna, dan kata, supaya tidak hanya mengandalkan warna.
// Merah untuk alarm, amber untuk hitungan, biru untuk latihan, abu-abu untuk yang tenang
// dan yang teknis. Hijau sengaja tidak dipakai untuk keadaan normal.
const GAYA = {
    terpantau: { ikon: Circle, kelas: 'font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
    kosong: { ikon: EyeOff, kelas: 'font-medium bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' },
    berbaring: { ikon: Diamond, kelas: 'font-semibold bg-amber-400 text-slate-950' },
    jatuh: { ikon: TriangleAlert, kelas: 'font-semibold bg-red-600 text-white' },
    latihan: { ikon: FlaskConical, kelas: 'font-semibold bg-blue-600 text-white' },
    terputus: { ikon: VideoOff, kelas: 'font-medium border border-dashed border-slate-400 text-slate-600 dark:border-slate-500 dark:text-slate-300' },
};

/** Lencana status satu kamera. `status` berasal dari bacaStatus() di statusKamera.js. */
export default function StatusKamera({ status, className = '' }) {
    const gaya = GAYA[status.kode] || GAYA.terpantau;
    const Ikon = gaya.ikon;
    return (
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs tabular-nums whitespace-nowrap ${gaya.kelas} ${className}`}>
            <Ikon className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
            {status.label}
        </span>
    );
}
