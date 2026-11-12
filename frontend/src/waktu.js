/**
 * waktu.js
 * ========
 * Waktu dalam bentuk yang dibaca perawat: "2 mnt lalu · 12 Nov, 14.32".
 *
 * Backend menyimpan waktu UTC tanpa penanda zona, jadi penandanya ditambahkan
 * sebelum dibaca browser. Tanpa itu, jam di layar mundur 7 jam di WIB.
 */
import { useEffect, useState } from 'react';
import { jamDari } from './statusKamera';

const BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

/** Milidetik epoch dari teks waktu backend; NaN kalau kosong atau rusak. */
export function msDari(iso) {
    if (!iso) return NaN;
    return new Date(/Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

/** "12 Nov, 14.32" */
export function tanggalJam(ms) {
    if (!Number.isFinite(ms)) return '';
    const d = new Date(ms);
    return `${d.getDate()} ${BULAN[d.getMonth()]}, ${jamDari(ms)}`;
}

/** "baru saja", "2 mnt lalu", "3 jam lalu", "5 hari lalu". */
export function waktuRelatif(ms, sekarang) {
    if (!Number.isFinite(ms)) return '';
    const detik = Math.max(0, Math.round((sekarang - ms) / 1000));
    if (detik < 60) return 'baru saja';
    if (detik < 3600) return `${Math.floor(detik / 60)} mnt lalu`;
    if (detik < 86400) return `${Math.floor(detik / 3600)} jam lalu`;
    return `${Math.floor(detik / 86400)} hari lalu`;
}

/** Lama dalam kata: "42 dtk", "2 mnt 10 dtk", "1 jam 5 mnt". */
export function durasiTeks(detik) {
    const s = Math.max(0, Math.round(Number(detik) || 0));
    if (s < 60) return `${s} dtk`;
    if (s < 3600) return `${Math.floor(s / 60)} mnt${s % 60 ? ` ${s % 60} dtk` : ''}`;
    const menit = Math.floor((s % 3600) / 60);
    return `${Math.floor(s / 3600)} jam${menit ? ` ${menit} mnt` : ''}`;
}

/** Selisih dua waktu backend dalam detik; null kalau salah satunya kosong. */
export function selisihDetik(dariIso, sampaiIso) {
    const a = msDari(dariIso);
    const b = msDari(sampaiIso);
    return Number.isFinite(a) && Number.isFinite(b) ? (b - a) / 1000 : null;
}

/** Jam sekarang yang ikut berganti, untuk teks relatif seperti "2 mnt lalu". */
export function useJam(selangMs = 30000) {
    const [sekarang, setSekarang] = useState(() => Date.now());
    useEffect(() => {
        const t = setInterval(() => setSekarang(Date.now()), selangMs);
        return () => clearInterval(t);
    }, [selangMs]);
    return sekarang;
}
