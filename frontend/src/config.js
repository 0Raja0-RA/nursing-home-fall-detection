/**
 * config.js
 * =========
 * Alamat backend, dikumpulkan di satu tempat supaya tidak tersebar sebagai
 * string "http://localhost:8000" di banyak file.
 *
 * Bisa ditimpa lewat .env Vite tanpa menyunting kode:
 *   VITE_API_BASE=http://192.168.1.10:8000
 * Berguna kalau dashboard dibuka dari HP atau laptop lain di jaringan yang sama.
 */

export const API_BASE =
    import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || 'http://localhost:8000';

export const WS_URL = API_BASE.replace(/^http/, 'ws') + '/ws';

/** URL lengkap endpoint MJPEG untuk sebuah kamera. */
export function streamUrl(cameraId) {
    return `${API_BASE}/api/cameras/${cameraId}/stream`;
}
