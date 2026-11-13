import { useEffect, useId, useRef, useState } from 'react';
import { Info, X } from 'lucide-react';

const LEBAR = 320;

/**
 * Lapisan kecil yang menempel di tombol pemicunya, misalnya penjelasan ⓘ di Pengaturan.
 *
 * Memakai Popover API. Tombol pemicu menjadi invoker (popovertarget), jadi browser yang
 * membuka dan menutupnya, termasuk lewat Esc dan klik di luar panel. Panel tampil di lapisan
 * teratas, sehingga tidak terpotong kolom yang menggulir dan tidak menggeser apa pun. Di
 * bawah lebar 640 px panelnya menjadi lembar dari bawah.
 *
 * pemicu: fungsi yang menerima props tombol pemicu (ref, popoverTarget, aria-expanded,
 * aria-controls) lalu mengembalikan tombolnya.
 */
export default function MenuKecil({ pemicu, judul, children }) {
    const idPanel = useId();
    const tombol = useRef(null);
    const panel = useRef(null);
    const [buka, setBuka] = useState(false);

    useEffect(() => {
        const p = panel.current;
        if (!p) return undefined;
        // Posisi dihitung tepat sebelum panel tampil: di bawah tombol, atau di atasnya bila
        // ruang di bawah sempit. Di HP posisinya diatur kelas CSS (lembar dari bawah).
        const letakkan = (e) => {
            if (e.newState !== 'open') return;
            const s = p.style;
            if (!window.matchMedia('(min-width: 640px)').matches || !tombol.current) {
                s.cssText = '';
                return;
            }
            const r = tombol.current.getBoundingClientRect();
            const lebar = Math.min(LEBAR, window.innerWidth - 16);
            const ruangBawah = window.innerHeight - r.bottom - 14;
            const ruangAtas = r.top - 14;
            s.width = `${lebar}px`;
            s.left = `${Math.min(Math.max(8, r.left), window.innerWidth - 8 - lebar)}px`;
            if (ruangBawah >= 200 || ruangBawah >= ruangAtas) {
                s.top = `${r.bottom + 6}px`;
                s.bottom = 'auto';
                s.maxHeight = `${ruangBawah}px`;
            } else {
                s.top = 'auto';
                s.bottom = `${window.innerHeight - r.top + 6}px`;
                s.maxHeight = `${ruangAtas}px`;
            }
        };
        const ganti = (e) => setBuka(e.newState === 'open');
        p.addEventListener('beforetoggle', letakkan);
        p.addEventListener('toggle', ganti);
        return () => {
            p.removeEventListener('beforetoggle', letakkan);
            p.removeEventListener('toggle', ganti);
        };
    }, []);

    // Posisinya dihitung sekali dari letak tombol, jadi panel ditutup bila halaman atau kolom
    // di belakangnya digulir, atau ukuran jendela berubah.
    useEffect(() => {
        if (!buka) return undefined;
        const tutup = (e) => {
            const p = panel.current;
            if (!p || (e.target instanceof Node && p.contains(e.target))) return;
            if (p.matches(':popover-open')) p.hidePopover();
        };
        window.addEventListener('scroll', tutup, true);
        window.addEventListener('resize', tutup);
        return () => {
            window.removeEventListener('scroll', tutup, true);
            window.removeEventListener('resize', tutup);
        };
    }, [buka]);

    return (
        <>
            {pemicu({ ref: tombol, popoverTarget: idPanel, 'aria-expanded': buka, 'aria-controls': idPanel })}
            <div
                ref={panel}
                id={idPanel}
                popover="auto"
                className="m-0 p-0 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 shadow-xl max-sm:inset-x-0 max-sm:top-auto max-sm:bottom-0 max-sm:w-full max-sm:max-w-none max-sm:max-h-[80dvh] max-sm:rounded-b-none max-sm:backdrop:bg-slate-950/40"
            >
                <div className="flex items-start justify-between gap-2 pl-4 pr-2 pt-2">
                    <p className="font-semibold text-sm pt-1.5">{judul}</p>
                    <button type="button" popoverTarget={idPanel} popoverTargetAction="hide" aria-label="Tutup"
                        className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
                        <X className="w-4 h-4" aria-hidden="true" />
                    </button>
                </div>
                <div className="px-4 pb-4 pt-1">{children}</div>
            </div>
        </>
    );
}

/** Ikon ⓘ yang membuka penjelasan lengkap sebuah pengaturan. */
export function Penjelasan({ judul, children }) {
    return (
        <MenuKecil judul={judul} pemicu={(p) => (
            <button type="button" {...p} aria-label={`Penjelasan: ${judul}`}
                className="inline-flex items-center justify-center w-6 h-6 shrink-0 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:text-slate-500 dark:hover:text-slate-200 dark:hover:bg-slate-800">
                <Info className="w-4 h-4" aria-hidden="true" />
            </button>
        )}>
            <div className="space-y-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{children}</div>
        </MenuKecil>
    );
}
