/**
 * config.js
 * =========
 * Alamat backend, dikumpulkan di satu tempat supaya tidak tersebar sebagai
 * string "http://localhost:8000" di banyak file.
 *
 * Bawaannya host yang sama dengan halaman ini, di port 8000. Sesi masuk disimpan
 * di cookie, dan cookie hanya ikut terkirim kalau dashboard dan backend dibuka
 * lewat host yang sama: dashboard di 127.0.0.1 dengan backend di localhost akan
 * selalu dianggap belum masuk. Mengikuti host halaman juga membuat dashboard
 * yang dibuka dari HP di jaringan yang sama langsung menemukan backend-nya.
 *
 * Hasil build (`npm run build`) disajikan oleh backend sendiri, misalnya lewat
 * tunnel saat pameran. Di situ dashboard dan API memakai alamat yang sama persis
 * (https://xxxx.trycloudflare.com tanpa port), jadi bawaannya origin halaman ini.
 * Port 8000 hanya dipakai saat pengembangan dengan Vite (run-frontend.bat).
 *
 * Bisa ditimpa lewat .env Vite tanpa menyunting kode:
 *   VITE_API_BASE=http://192.168.1.10:8000
 */

function alamatBawaan() {
    if (typeof window === 'undefined') return 'http://localhost:8000';
    if (!import.meta.env.DEV) return window.location.origin;
    return `${window.location.protocol}//${window.location.hostname}:8000`;
}

const bawaan = alamatBawaan();

export const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '') || bawaan;

export const WS_URL = API_BASE.replace(/^http/, 'ws') + '/ws';

/** URL lengkap endpoint MJPEG untuk sebuah kamera. */
export function streamUrl(cameraId) {
    return `${API_BASE}/api/cameras/${cameraId}/stream`;
}
