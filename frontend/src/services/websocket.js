/**
 * websocket.js
 * ============
 * WebSocket client untuk menerima live updates dari backend.
 *
 * Auto-reconnect jika koneksi terputus.
 * Parse pesan JSON dan dispatch ke handler berdasarkan event type.
 */

const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws`;

const RECONNECT_DELAY = 3000; // ms

/**
 * Buat koneksi WebSocket dengan auto-reconnect.
 *
 * @param {Object} handlers
 * @param {Function} handlers.onStatusUpdate - Dipanggil saat ada status_update event.
 * @param {Function} handlers.onAlert - Dipanggil saat ada alert event.
 * @param {Function} handlers.onOpen - Dipanggil saat koneksi terbuka.
 * @param {Function} handlers.onClose - Dipanggil saat koneksi tertutup.
 * @returns {{ close: Function }} Object dengan method close() untuk menutup koneksi.
 */
export function createWebSocket(handlers = {}) {
  let ws = null;
  let shouldReconnect = true;
  let reconnectTimeout = null;

  function connect() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log("🔌 WebSocket connected");
      handlers.onOpen?.();
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        switch (message.event) {
          case "status_update":
            handlers.onStatusUpdate?.(message.data);
            break;
          case "alert":
            handlers.onAlert?.(message.data);
            break;
          case "heartbeat":
            // Heartbeat — no action needed
            break;
          default:
            console.warn("Unknown WS event:", message.event);
        }
      } catch (err) {
        console.error("Failed to parse WS message:", err);
      }
    };

    ws.onclose = () => {
      console.log("🔌 WebSocket disconnected");
      handlers.onClose?.();

      if (shouldReconnect) {
        console.log(`Reconnecting in ${RECONNECT_DELAY / 1000}s...`);
        reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      ws.close();
    };
  }

  connect();

  return {
    close() {
      shouldReconnect = false;
      clearTimeout(reconnectTimeout);
      ws?.close();
    },

    send(data) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(typeof data === "string" ? data : JSON.stringify(data));
      }
    },
  };
}
