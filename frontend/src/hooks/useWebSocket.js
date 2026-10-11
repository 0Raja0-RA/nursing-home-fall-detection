import { useCallback, useEffect, useState } from 'react';

/**
 * Langganan WebSocket backend: status kamera per frame dan alert jatuh.
 *
 * Menyambung ulang sendiri kalau putus (backend di-restart, WiFi berpindah).
 * Tanpa itu dashboard diam-diam berhenti menerima alarm sampai halamannya
 * dimuat ulang -- kegagalan yang sangat tidak diinginkan untuk sistem alarm.
 */
export function useWebSocket(url) {
    const [cameraData, setCameraData] = useState({});
    const [alerts, setAlerts] = useState([]);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        let ws = null;
        let timer = null;
        let berhenti = false;

        const sambung = () => {
            ws = new WebSocket(url);

            ws.onopen = () => setConnected(true);

            ws.onmessage = (event) => {
                let pesan;
                try { pesan = JSON.parse(event.data); } catch { return; }
                const { event: jenis, data } = pesan;

                if (jenis === 'status_update') {
                    setCameraData((prev) => ({ ...prev, [data.camera_id]: data }));
                } else if (jenis === 'alert') {
                    // Tanpa duplikat: alert yang sama tidak boleh muncul dua kali.
                    setAlerts((prev) => (prev.some((a) => a.id === data.id) ? prev : [...prev, data]));
                } else if (jenis === 'alert_ack') {
                    // Sudah ditangani -- di layar ini, di halaman Riwayat Insiden, atau
                    // oleh perawat lain. Banner di semua dashboard hilang bersamaan.
                    setAlerts((prev) => prev.filter((a) => a.id !== data.id));
                }
            };

            ws.onerror = () => ws.close();
            ws.onclose = () => {
                setConnected(false);
                if (!berhenti) timer = setTimeout(sambung, 2000);
            };
        };

        sambung();
        return () => {
            berhenti = true;
            clearTimeout(timer);
            if (ws) ws.close();
        };
    }, [url]);

    const dismissAlert = useCallback((id) => {
        setAlerts((prev) => prev.filter((a) => a.id !== id));
    }, []);

    return { cameraData, alerts, connected, dismissAlert };
}
