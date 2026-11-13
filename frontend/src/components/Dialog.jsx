import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Dialog di tengah layar untuk konfirmasi dan formulir pendek. Dipasang = terbuka:
 * `{buka && <Dialog …>}`.
 *
 * Memakai <dialog> bawaan lewat showModal(): tampil di lapisan teratas, isi di
 * belakangnya tidak bisa disentuh, fokus terkunci di dalam sampai ditutup, dan Esc
 * menutupnya. Esc dan klik di luar diteruskan ke onTutup supaya keadaan React tetap
 * sejalan; fokus kembali ke tombol pembukanya saat dialog ditutup.
 */
export default function Dialog({ judul, keterangan, onTutup, children, lebar = 'max-w-lg' }) {
    const ref = useRef(null);
    const idJudul = useId();

    useEffect(() => {
        const d = ref.current;
        if (d && !d.open) {
            d.showModal();
            // showModal() memfokus elemen pertama, yaitu tombol Tutup. Untuk formulir, fokus
            // dipindah ke kolom pertamanya, atau ke elemen bertanda data-fokus-awal.
            d.querySelector('[data-fokus-awal], input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled)')?.focus();
        }
        return () => { if (d?.open) d.close(); };
    }, []);

    return (
        <dialog
            ref={ref}
            aria-labelledby={idJudul}
            onCancel={(e) => { e.preventDefault(); onTutup(); }}
            // Klik di latar (bukan di isi) mengenai elemen dialog itu sendiri.
            onClick={(e) => { if (e.target === ref.current) onTutup(); }}
            // m-auto: preflight Tailwind menolkan margin, padahal margin auto bawaan browser
            // itulah yang menaruh dialog modal di tengah layar.
            className={`m-auto p-0 w-[calc(100vw-2rem)] ${lebar} rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 shadow-xl backdrop:bg-slate-950/60`}
        >
            <div className="p-5 space-y-4">
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <h2 id={idJudul} className="font-semibold text-lg leading-snug">{judul}</h2>
                        {keterangan && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{keterangan}</p>}
                    </div>
                    <button type="button" onClick={onTutup} aria-label="Tutup"
                        className="-m-1 p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0">
                        <X className="w-5 h-5" aria-hidden="true" />
                    </button>
                </div>
                {children}
            </div>
        </dialog>
    );
}
