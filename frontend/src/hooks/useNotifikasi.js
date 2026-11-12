import { useEffect, useState } from 'react';

/**
 * Notifikasi browser untuk alarm, saat tab FallDetect tidak sedang dilihat.
 *
 * Bunyi dan judul tab tidak terlihat bila perawat sedang membuka aplikasi lain. Notifikasi
 * sistem muncul di atas aplikasi apa pun, dan untuk alarm sungguhan tetap tampil sampai
 * ditutup. Isinya hanya nama ruang dan lama berbaring, tanpa foto, karena notifikasi bisa
 * terlihat orang lain di layar yang sama.
 *
 * Izinnya diatur per perangkat oleh browser, hanya di HTTPS atau localhost, dan hanya
 * bisa diminta dari tekanan tombol.
 */

/** 'granted', 'denied', 'default', 'perlu-https', atau 'tidak-didukung'. */
export function statusNotifikasi() {
    if (typeof window === 'undefined' || !('Notification' in window)) return 'tidak-didukung';
    if (!window.isSecureContext) return 'perlu-https';
    return Notification.permission;
}

const pendengar = new Set();

/** Panggil dari tekanan tombol. Returns: status sesudah browser menjawab. */
export async function mintaIzinNotifikasi() {
    if (statusNotifikasi() === 'default') {
        try {
            await Notification.requestPermission();
        } catch {
            // Browser lama memakai callback; statusnya tetap dibaca di bawah.
        }
    }
    const s = statusNotifikasi();
    pendengar.forEach((f) => f(s));
    return s;
}

/** Status izin yang ikut berubah setelah diminta dari halaman mana pun. */
export function useStatusNotifikasi() {
    const [status, setStatus] = useState(statusNotifikasi);
    useEffect(() => {
        pendengar.add(setStatus);
        return () => pendengar.delete(setStatus);
    }, []);
    return status;
}

/**
 * Tampilkan satu notifikasi alarm. `tag` per alert, jadi beberapa tab yang terbuka
 * tidak menumpuk notifikasi yang sama. Returns: objek Notification, atau null.
 */
export function kabariAlarm(alert) {
    if (statusNotifikasi() !== 'granted') return null;
    const nama = alert.camera_name || alert.camera_id;
    try {
        const n = new Notification(alert.simulated ? `Latihan: ${nama}` : `Kemungkinan jatuh: ${nama}`, {
            body: alert.simulated
                ? 'Latihan, bukan kejadian sungguhan.'
                : `Terbaca berbaring ${Math.round(alert.fall_duration || 0)} detik. Buka FallDetect untuk menangani.`,
            tag: `falldetect-alert-${alert.id}`,
            icon: '/favicon.svg',
            requireInteraction: !alert.simulated,
        });
        n.onclick = () => {
            window.focus();
            n.close();
        };
        return n;
    } catch {
        return null;    // mis. Chrome Android hanya mengizinkan notifikasi lewat service worker
    }
}
