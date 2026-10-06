import { useState, useEffect, useRef } from 'react';

export function useWebSocket(url) {
    const [cameraData, setCameraData] = useState({});
    const [alerts, setAlerts] = useState([]);
    const ws = useRef(null);

    useEffect(() => {
        ws.current = new WebSocket(url);

        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'camera_update') {
                // Update status kamera (normal, transitional, lying_on_ground)
                setCameraData(prev => ({ ...prev, [data.cameraId]: data }));
            } else if (data.type === 'emergency_alert') {
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