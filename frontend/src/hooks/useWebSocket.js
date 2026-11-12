import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { msDari } from '../waktu';

// Alarm yang belum ditangani dalam rentang ini muncul lagi sebagai banner setelah
// halaman dimuat ulang. Yang lebih tua tetap ada di antrean Riwayat Insiden, tetapi
// tidak berbunyi lagi: catatan uji yang terlupa berhari-hari tidak boleh meraung
// setiap kali dashboard dibuka.
const PULIHKAN_JAM = 24;

/**
 * Terapkan satu alert ke daftar alarm aktif.
 *
 * Alert yang sudah ditangani dibuang; yang lain ditambahkan atau diperbarui
 * (mis. setelah ada yang menekan "Saya ke sana"). Nama ruang lama dipertahankan
 * kalau versi barunya kosong.
 */
function terapkan(daftar, data) {
    if (data.acknowledged) return daftar.filter((a) => a.id !== data.id);
    if (!daftar.some((a) => a.id === data.id)) return [...daftar, data];
    return daftar.map((a) => (a.id === data.id ? { ...a, ...data, camera_name: data.camera_name || a.camera_name } : a));
}

/**
 * Langganan WebSocket backend: status kamera per frame dan alert jatuh.
 *
 * Menyambung ulang sendiri kalau putus (backend di-restart, WiFi berpindah).
 * Tanpa itu dashboard diam-diam berhenti menerima alarm sampai halamannya
 * dimuat ulang -- kegagalan yang sangat tidak diinginkan untuk sistem alarm.
 *
 * Setiap kali tersambung, alarm yang belum ditangani diambil lagi lewat REST.
 * Sebelumnya alarm aktif hilang dari banner begitu halaman dimuat ulang, karena
 * daftar alarm hanya hidup di memori halaman.
 */
export function useWebSocket(url) {
    const [cameraData, setCameraData] = useState({});
    const [alerts, setAlerts] = useState([]);
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        let ws = null;
        let timer = null;
        let berhenti = false;

        const pulihkan = async () => {
            const diminta = Date.now();
            const sejak = new Date(diminta - PULIHKAN_JAM * 3600e3).toISOString();
            try {
                const r = await api(`/api/alerts/?status=terbuka&limit=50&sejak=${encodeURIComponent(sejak)}`);
                if (!r.ok || berhenti) return;
                const terbuka = await r.json();
                const idTerbuka = new Set(terbuka.map((a) => a.id));
                setAlerts((prev) => {
                    // Yang ditangani selama koneksi putus ikut hilang; alarm yang baru
                    // tiba lewat WebSocket sesudah permintaan ini dibuat tetap tinggal.
                    const sisa = prev.filter((a) => idTerbuka.has(a.id) || msDari(a.created_at) > diminta);
                    return [...terbuka].reverse().reduce(terapkan, sisa);
                });
            } catch { /* backend belum siap; alarm baru tetap datang lewat WebSocket */ }
        };

        const sambung = () => {
            ws = new WebSocket(url);

            ws.onopen = () => {
                setConnected(true);
                pulihkan();
            };

            ws.onmessage = (event) => {
                let pesan;
                try { pesan = JSON.parse(event.data); } catch { return; }
                const { event: jenis, data } = pesan;

                if (jenis === 'status_update') {
                    setCameraData((prev) => ({
                        ...prev,
                        [data.camera_id]: {
                            ...data,
                            // Kapan model terakhir melihat orang di kamera ini, untuk
                            // keterangan saat AI tidak menemukan siapa pun.
                            terakhir_terlihat: data.current_posture
                                ? Date.now()
                                : prev[data.camera_id]?.terakhir_terlihat,
                        },
                    }));
                } else if (jenis === 'alert' || jenis === 'alert_update') {
                    // alert_update: ada yang menekan "Saya ke sana" atau mengubah putusan,
                    // di layar ini, di perangkat lain, atau dari Telegram.
                    setAlerts((prev) => terapkan(prev, data));
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

    /** Hapus alert dari banner, mis. setelah ditandai ditangani dari layar ini. */
    const dismissAlert = useCallback((id) => {
        setAlerts((prev) => prev.filter((a) => a.id !== id));
    }, []);

    /** Terapkan jawaban backend seketika, tanpa menunggu siaran WebSocket. */
    const perbaruiAlert = useCallback((data) => {
        setAlerts((prev) => terapkan(prev, data));
    }, []);

    return { cameraData, alerts, connected, dismissAlert, perbaruiAlert };
}
