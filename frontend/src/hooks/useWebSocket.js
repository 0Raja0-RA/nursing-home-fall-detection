import { useState, useEffect, useRef } from 'react';

export function useWebSocket(url) {
    const [cameraData, setCameraData] = useState({});
    const [alerts, setAlerts] = useState([]);
    const ws = useRef(null);

    useEffect(() => {
        ws.current = new WebSocket(url);

        ws.current.onmessage = (event) => {
            const message = JSON.parse(event.data);
            const { event: eventType, data } = message;

            if (eventType === 'status_update') {
                // Update status kamera (normal, transitional, lying_on_ground)
                // Backend mengirimkan: camera_id, is_active, fall_state, dll
                setCameraData(prev => ({ ...prev, [data.camera_id]: data }));
            } else if (eventType === 'alert') {
                // Menerima peringatan jika batas waktu jatuh (threshold) terlewati
                setAlerts(prev => [...prev, data]);
            }
        };

        ws.current.onclose = () => console.log('WebSocket terputus. Mencoba menyambung kembali...');

        return () => {
            if (ws.current) ws.current.close();
        };
    }, [url]);

    const acknowledgeAlert = (alertId) => {
        setAlerts(prev => prev.filter(a => a.id !== alertId));
        // Kirim konfirmasi ke backend bahwa alarm telah ditangani
        ws.current.send(JSON.stringify({ action: 'acknowledge', alertId }));
    };

    return { cameraData, alerts, acknowledgeAlert };
}
