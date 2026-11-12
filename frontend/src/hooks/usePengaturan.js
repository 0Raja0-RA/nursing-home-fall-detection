import { useEffect, useState } from 'react';
import { api } from '../api';

/**
 * Pengaturan yang sedang berlaku di backend: ambang durasi jatuh, eskalasi, dan status Telegram.
 *
 * Args:
 *   selangMs: bila lebih dari 0, diambil ulang sesering ini, untuk pemakai yang
 *     tetap terpasang lama (banner alarm) supaya perubahan di Pengaturan ikut terbaca.
 *
 * Returns: objek dari GET /api/settings/, atau null selama belum terbaca atau
 * backend tidak bisa dihubungi. Pemakainya harus tetap berfungsi tanpa nilai ini.
 */
export function usePengaturan(selangMs = 0) {
    const [pengaturan, setPengaturan] = useState(null);
    useEffect(() => {
        let batal = false;
        const ambil = () => api('/api/settings/')
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (!batal && d) setPengaturan(d); })
            .catch(() => { /* backend belum jalan; label tampil tanpa ambang */ });
        ambil();
        const t = selangMs > 0 ? setInterval(ambil, selangMs) : null;
        return () => {
            batal = true;
            if (t) clearInterval(t);
        };
    }, [selangMs]);
    return pengaturan;
}
