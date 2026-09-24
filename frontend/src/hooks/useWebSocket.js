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
}
