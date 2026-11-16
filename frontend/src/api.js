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

/**
 * Satu galat validasi FastAPI (Pydantic) dalam bahasa Indonesia. Pesan bawaannya berbahasa
 * Inggris ("String should have at most 64 characters"); jenis yang umum diterjemahkan.
 */
function terjemahkanValidasi(d) {
    const ctx = d.ctx || {};
    switch (d.type) {
        case 'missing': return 'ada isian wajib yang kosong';
        case 'string_too_long': return `terlalu panjang, paling banyak ${ctx.max_length} huruf`;
        case 'string_too_short': return `terlalu pendek, paling sedikit ${ctx.min_length} huruf`;
        case 'greater_than_equal': return `paling kecil ${ctx.ge}`;
        case 'less_than_equal': return `paling besar ${ctx.le}`;
        default: return String(d.msg || '').replace(/^Value error, /, '');
    }
}

/** Pesan galat yang bisa dibaca manusia dari jawaban backend. */
export async function bacaGalat(r) {
    try {
        const b = await r.json();
        if (typeof b.detail === 'string') return b.detail;
        if (Array.isArray(b.detail)) return b.detail.map(terjemahkanValidasi).join(', ');
    } catch { /* body bukan JSON */ }
    if (r.status >= 500) return `Server FallDetect sedang bermasalah (kode ${r.status}). Coba lagi sebentar lagi.`;
    return `Permintaan ditolak server (kode ${r.status}).`;
}

// Dibaca perawat dan pengunjung, jadi tanpa alamat server. run-backend.bat tetap disebut
// untuk tim yang menjalankan servernya.
export const PESAN_TERPUTUS = 'Server FallDetect tidak bisa dihubungi. Periksa jaringan, atau pastikan server di laptop jaga menyala (run-backend.bat).';

/** Galat dari blok try: putus jaringan (TypeError dari fetch) atau pesan yang sudah dibaca. */
export const pesanGalat = (err) => (err instanceof TypeError ? PESAN_TERPUTUS : err.message);
