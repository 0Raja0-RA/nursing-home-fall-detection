<<<<<<< Updated upstream
/**
 * useWebSocket.js
 * ===============
 * React hook untuk mengelola koneksi WebSocket.
 *
 * Auto-connect saat component mount, auto-disconnect saat unmount.
 * Provides connection status dan handlers untuk event types.
 */

import { useEffect, useRef, useState } from "react";
import { createWebSocket } from "../services/websocket";

/**
 * Hook untuk koneksi WebSocket real-time.
 *
 * @param {Object} params
 * @param {Function} params.onStatusUpdate - Handler untuk status_update event.
 * @param {Function} params.onAlert - Handler untuk alert event.
 * @returns {{ isConnected: boolean }}
 */
export function useWebSocket({ onStatusUpdate, onAlert } = {}) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);
  const handlersRef = useRef({ onStatusUpdate, onAlert });

  // Update handler refs tanpa re-create koneksi
  useEffect(() => {
    handlersRef.current = { onStatusUpdate, onAlert };
  }, [onStatusUpdate, onAlert]);

  useEffect(() => {
    wsRef.current = createWebSocket({
      onStatusUpdate: (data) => handlersRef.current.onStatusUpdate?.(data),
      onAlert: (data) => handlersRef.current.onAlert?.(data),
      onOpen: () => setIsConnected(true),
      onClose: () => setIsConnected(false),
    });

    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { isConnected };
=======
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
>>>>>>> Stashed changes
}
