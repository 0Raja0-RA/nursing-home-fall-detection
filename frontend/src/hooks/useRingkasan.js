import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

/**
 * Jumlah insiden per kelompok (GET /api/alerts/ringkasan), untuk lencana menu
 * dan tab Riwayat Insiden.
 *
 * Disegarkan berkala, dan seketika setiap jumlah alarm aktif berubah.
 *
 * Returns: { ringkasan, segarkanRingkasan }. ringkasan null selama belum terbaca.
 */
export function useRingkasan(jumlahAlarm) {
    const [ringkasan, setRingkasan] = useState(null);

    const segarkanRingkasan = useCallback(async () => {
        try {
            const r = await api('/api/alerts/ringkasan');
            if (r.ok) setRingkasan(await r.json());
        } catch { /* backend belum jalan; lencana disembunyikan */ }
    }, []);

    useEffect(() => {
        // setState terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        segarkanRingkasan();
        const t = setInterval(segarkanRingkasan, 10000);
        return () => clearInterval(t);
    }, [segarkanRingkasan, jumlahAlarm]);

    return { ringkasan, segarkanRingkasan };
}
