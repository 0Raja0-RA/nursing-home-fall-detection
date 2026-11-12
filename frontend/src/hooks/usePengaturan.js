import { useEffect, useState } from 'react';
import { api } from '../api';

/**
 * Pengaturan yang sedang berlaku di backend: ambang durasi jatuh dan status Telegram.
 *
 * Returns: objek dari GET /api/settings/, atau null selama belum terbaca atau
 * backend tidak bisa dihubungi. Pemakainya harus tetap berfungsi tanpa nilai ini.
 */
export function usePengaturan() {
    const [pengaturan, setPengaturan] = useState(null);
    useEffect(() => {
        let batal = false;
        api('/api/settings/')
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (!batal && d) setPengaturan(d); })
            .catch(() => { /* backend belum jalan; label tampil tanpa ambang */ });
        return () => { batal = true; };
    }, []);
    return pengaturan;
}
