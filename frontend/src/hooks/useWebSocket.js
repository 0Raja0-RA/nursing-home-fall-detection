import { useState, useEffect } from 'react';

export const useWebSocket = (url) => {
    const [alertData, setAlertData] = useState(null);
    const [isConnected, setIsConnected] = useState(false);

    useEffect(() => {
        const ws = new WebSocket(url);

        ws.onopen = () => setIsConnected(true);

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            // Menangkap trigger dari State Machine backend
            if (data.status === 'FALLEN' || data.status === 'FALL') {
                setAlertData(data);
            }
        };

        ws.onclose = () => setIsConnected(false);

        return () => ws.close();
    }, [url]);

    const clearAlert = () => setAlertData(null);

    return { alertData, isConnected, clearAlert };
};