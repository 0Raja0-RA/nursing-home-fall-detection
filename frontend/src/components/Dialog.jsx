import { useId, useLayoutEffect, useRef } from 'react';
import { X } from 'lucide-react';

/**
 * Dialog di tengah layar untuk konfirmasi dan formulir pendek, atau dengan `laci` sebagai
 * laci samping dari kanan (di HP layar penuh) untuk isi yang lebih panjang. Dipasang =
 * terbuka: `{buka && <Dialog …>}`.
 *
 * Memakai <dialog> bawaan lewat showModal(): tampil di lapisan teratas, isi di
 * belakangnya tidak bisa disentuh, fokus terkunci di dalam sampai ditutup, dan Esc
 * menutupnya. Esc dan klik di luar diteruskan ke onTutup supaya keadaan React tetap
 * sejalan; fokus kembali ke tombol pembukanya saat dialog ditutup.
 *
 * Karena halaman di belakangnya tidak bisa disentuh, toast juga tertutup selama dialog
 * terbuka. Kabar dari tindakan di dalam dialog ditulis di dalam dialog itu sendiri.
 */
export default function Dialog({ judul, keterangan, onTutup, children, lebar = 'max-w-lg', laci = false, fokusKolom = true }) {
    const ref = useRef(null);
    const idJudul = useId();

    // useLayoutEffect, bukan useEffect: pembersihannya berjalan sebelum React melepas
    // <dialog> dari halaman, jadi close() masih sempat mengembalikan fokus ke pembukanya.
    useLayoutEffect(() => {
        const d = ref.current;
        if (!d || d.open) return undefined;
        const asal = document.activeElement;
        d.showModal();
        // showModal() memfokus elemen pertama, yaitu tombol Tutup. Untuk formulir, fokus
        // dipindah ke kolom pertamanya, atau ke elemen bertanda data-fokus-awal.
        const awal = d.querySelector('[data-fokus-awal]')
            || (fokusKolom ? d.querySelector('input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled)') : null);
        awal?.focus();
        return () => {
            if (d.open) d.close();
            // Cadangan bila browser tidak mengembalikan fokus sendiri.
            if (asal instanceof HTMLElement && asal.isConnected && (!document.activeElement || document.activeElement === document.body)) asal.focus();
        };
    }, [fokusKolom]);

    const bentuk = laci
        // Menempel di kanan setinggi layar. Bergeser masuk sedikit saat dibuka, kecuali
        // pengguna meminta gerak dikurangi.
        ? 'fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-full max-w-none sm:max-w-lg rounded-none sm:rounded-l-2xl border-y-0 border-r-0 max-sm:border-l-0 transition-[translate,opacity] duration-200 ease-out starting:open:translate-x-8 starting:open:opacity-0 motion-reduce:transition-none'
        // m-auto: preflight Tailwind menolkan margin, padahal margin auto bawaan browser
        // itulah yang menaruh dialog modal di tengah layar.
        : `m-auto w-[calc(100vw-2rem)] ${lebar} rounded-2xl`;

    const kepala = (
        <div className={laci
            ? 'sticky top-0 z-10 flex items-start justify-between gap-3 px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900'
            : 'flex items-start justify-between gap-3'}>
            <div className="min-w-0">
                <h2 id={idJudul} className="font-semibold text-lg leading-snug">{judul}</h2>
                {keterangan && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{keterangan}</p>}
            </div>
            <button type="button" onClick={onTutup} aria-label="Tutup"
                className="-m-1 p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0">
                <X className="w-5 h-5" aria-hidden="true" />
            </button>
        </div>
    );

    return (
        <dialog
            ref={ref}
            aria-labelledby={idJudul}
            onCancel={(e) => { e.preventDefault(); onTutup(); }}
            // Klik di latar (bukan di isi) mengenai elemen dialog itu sendiri.
            onClick={(e) => { if (e.target === ref.current) onTutup(); }}
            className={`p-0 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 shadow-xl backdrop:bg-slate-950/60 ${bentuk}`}
        >
            {laci ? (
                <div className="min-h-full flex flex-col">
                    {kepala}
                    <div className="flex-1 p-4 space-y-5">{children}</div>
                </div>
            ) : (
                <div className="p-5 space-y-4">
                    {kepala}
                    {children}
                </div>
            )}
        </dialog>
    );
}
