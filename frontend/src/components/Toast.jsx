import { useCallback, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, X } from 'lucide-react';
import { KonteksToast } from '../context/toast';

const LAMA_MS = 4000;
const MAKS = 4;

/**
 * Penyedia toast untuk seluruh dashboard. Wilayah pesannya selalu ada di DOM sejak
 * awal, supaya pesan pertama pun terbaca pembaca layar (WCAG 4.1.3). Pesan biasa
 * memakai role="status"; galat memakai role="alert" dan menunggu ditutup.
 */
export default function ToastProvider({ children }) {
    const [daftar, setDaftar] = useState([]);       // { id, tipe: 'ok' | 'galat', teks }
    const nomor = useRef(0);

    const tutup = useCallback((id) => setDaftar((d) => d.filter((t) => t.id !== id)), []);
    const kabari = useCallback((teks, tipe = 'ok') => {
        const id = ++nomor.current;
        setDaftar((d) => [...d.slice(-(MAKS - 1)), { id, tipe, teks }]);
        if (tipe !== 'galat') setTimeout(() => tutup(id), LAMA_MS);
    }, [tutup]);

    // Galat tidak berlatar merah penuh: merah penuh hanya untuk alarm yang belum direspons
    // (prinsip 3). Warnanya dibawa tepi kiri dan ikon.
    const butir = (t) => {
        const galat = t.tipe === 'galat';
        return (
            <div key={t.id} className={`pointer-events-auto flex items-start gap-2.5 rounded-xl px-3.5 py-3 text-sm shadow-lg border ${galat
                ? 'bg-white border-slate-200 border-l-4 border-l-red-600 text-slate-900 dark:bg-slate-800 dark:border-slate-700 dark:border-l-red-500 dark:text-slate-100'
                : 'bg-slate-900 border-slate-800 text-white dark:bg-slate-100 dark:border-slate-200 dark:text-slate-900'}`}>
                {galat
                    ? <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-600 dark:text-red-400" aria-hidden="true" />
                    : <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400 dark:text-emerald-700" aria-hidden="true" />}
                <span className="flex-1 min-w-0 break-words">{t.teks}</span>
                <button type="button" onClick={() => tutup(t.id)} aria-label="Tutup pesan"
                    className={`-m-1 p-1 rounded-md opacity-80 hover:opacity-100 ${galat
                        ? 'hover:bg-slate-100 dark:hover:bg-slate-700'
                        : 'hover:bg-white/10 dark:hover:bg-black/10'}`}>
                    <X className="w-4 h-4" aria-hidden="true" />
                </button>
            </div>
        );
    };

    return (
        <KonteksToast.Provider value={kabari}>
            {children}
            <div className="fixed bottom-4 right-4 z-[500] w-[min(24rem,calc(100vw-2rem))] flex flex-col items-stretch gap-2 pointer-events-none">
                <div role="status" aria-live="polite" className="flex flex-col gap-2">
                    {daftar.filter((t) => t.tipe !== 'galat').map(butir)}
                </div>
                <div role="alert" className="flex flex-col gap-2">
                    {daftar.filter((t) => t.tipe === 'galat').map(butir)}
                </div>
            </div>
        </KonteksToast.Provider>
    );
}
