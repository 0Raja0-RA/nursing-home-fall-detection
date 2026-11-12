import { useEffect, useState } from 'react';

/**
 * Suara alarm untuk seluruh dashboard.
 *
 * Browser menolak memutar suara sebelum ada interaksi di halaman. Dulu kegagalan
 * itu diam-diam: alarm tampil tanpa bunyi dan tidak ada yang tahu. Sekarang
 * statusnya dibaca dan ditampilkan, dan interaksi pertama di mana pun langsung
 * mengaktifkannya.
 */
let ctx = null;
const pendengar = new Set();

function umumkan() {
    const s = statusSuara();
    pendengar.forEach((f) => f(s));
}

/** 'aktif', 'belum' (belum ada interaksi atau diblokir), atau 'tidak-didukung'. */
export function statusSuara() {
    if (typeof window === 'undefined' || !(window.AudioContext || window.webkitAudioContext)) {
        return 'tidak-didukung';
    }
    return ctx?.state === 'running' ? 'aktif' : 'belum';
}

/** Panggil dari interaksi pengguna (klik atau tombol keyboard). */
export function aktifkanSuara() {
    try {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return Promise.resolve(false);
            ctx = new AC();
            ctx.onstatechange = umumkan;
        }
        return ctx.resume().then(
            () => { umumkan(); return statusSuara() === 'aktif'; },
            () => { umumkan(); return false; },
        );
    } catch {
        return Promise.resolve(false);
    }
}

/**
 * Bunyikan pola alarm sekali. Latihan memakai nada yang lebih rendah dan lebih
 * pendek supaya tidak tertukar dengan kejadian sungguhan.
 *
 * Returns: false kalau suara belum aktif.
 */
export function bunyikan(latihan = false) {
    if (statusSuara() !== 'aktif') return false;
    const jeda = latihan ? [0, 0.5] : [0, 0.35, 0.7];
    jeda.forEach((t) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = latihan ? 'sine' : 'square';
        osc.frequency.value = latihan ? 520 : 880;
        gain.gain.value = latihan ? 0.2 : 0.15;
        osc.connect(gain).connect(ctx.destination);
        osc.start(ctx.currentTime + t);
        osc.stop(ctx.currentTime + t + (latihan ? 0.3 : 0.2));
    });
    return true;
}

/** Status suara yang ikut berubah. Interaksi pertama di halaman membuka suaranya. */
export function useStatusSuara() {
    const [status, setStatus] = useState(statusSuara);
    useEffect(() => {
        pendengar.add(setStatus);
        const buka = () => { aktifkanSuara(); };
        document.addEventListener('pointerdown', buka);
        document.addEventListener('keydown', buka);
        return () => {
            pendengar.delete(setStatus);
            document.removeEventListener('pointerdown', buka);
            document.removeEventListener('keydown', buka);
        };
    }, []);
    return status;
}
