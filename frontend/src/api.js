/**
 * api.js
 * ======
 * Satu pintu untuk memanggil backend.
 *
 * Sesi masuk disimpan backend di cookie HttpOnly, jadi setiap permintaan harus
 * membawa cookie itu (credentials: 'include'). Jawaban 401 di luar /api/auth/
 * berarti sesinya habis; AuthContext mendengarkan kabar itu dan membawa pengguna
 * ke halaman Login.
 */
import { API_BASE } from './config';

export const SESI_HABIS = 'falldetect:sesi-habis';

/**
 * fetch ke backend. `json` (opsional) dikirim sebagai body JSON.
 *
 * Returns: Response, sama seperti fetch. Galat jaringan tetap dilempar.
 */
export async function api(jalur, { json, headers, ...opsi } = {}) {
    const init = { credentials: 'include', ...opsi, headers: { ...(headers || {}) } };
    if (json !== undefined) {
        init.body = JSON.stringify(json);
        init.headers['Content-Type'] = 'application/json';
    }
    const r = await fetch(`${API_BASE}${jalur}`, init);
    if (r.status === 401 && !jalur.startsWith('/api/auth/')) {
        window.dispatchEvent(new Event(SESI_HABIS));
    }
    return r;
}

/** Pesan galat yang bisa dibaca manusia dari jawaban backend. */
export async function bacaGalat(r) {
    try {
        const b = await r.json();
        if (typeof b.detail === 'string') return b.detail;
        if (Array.isArray(b.detail)) {
            return b.detail.map((d) => String(d.msg || '').replace(/^Value error, /, '')).join(', ');
        }
    } catch { /* body bukan JSON */ }
    return `Backend menjawab ${r.status}`;
}

export const PESAN_TERPUTUS = `Tidak bisa menghubungi backend di ${API_BASE}. Jalankan run-backend.bat dulu.`;
