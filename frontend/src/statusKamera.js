/**
 * statusKamera.js
 * ===============
 * Kosakata status kamera, dipakai di Pemantauan dan Testing Kamera HP.
 *
 * "AI tidak menemukan orang" sengaja dibedakan dari "Terpantau". Model bisa gagal
 * membaca orang yang tergeletak, dan layar tidak boleh menutupi kegagalan itu
 * dengan kata Normal.
 */

/** Detik menjadi mm:ss, misalnya 8.2 menjadi "00:08". */
export function mmss(detik) {
    const total = Math.max(0, Math.floor(Number(detik) || 0));
    const menit = Math.floor(total / 60);
    return `${String(menit).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

/** Jam setempat dari milidetik epoch, misalnya "14.32". */
export function jamDari(ms) {
    return new Date(ms).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Status satu kamera dalam kata yang dipahami perawat.
 *
 * Args:
 *   aktif: kamera mengirim gambar.
 *   state: fall_state dari state machine backend.
 *   adaOrang: model menemukan setidaknya satu orang di frame terakhir.
 *   durasi: lama berbaring yang sedang dihitung, dalam detik.
 *   ambang: batas sebelum alarm, dalam detik (boleh kosong).
 *   latihan: dipicu Mode latihan, bukan kejadian sungguhan.
 *   sisaJeda: detik tersisa Mode perawatan; 0 atau kosong bila tidak dijeda.
 *
 * Returns: { kode, label }. kode menentukan bentuk dan warna di StatusKamera.
 */
export function bacaStatus({ aktif, state, adaOrang, durasi, ambang, latihan, sisaJeda }) {
    if (!aktif) return { kode: 'terputus', label: 'Terputus' };
    if (sisaJeda > 0) return { kode: 'perawatan', label: `Mode perawatan ${mmss(sisaJeda)}` };
    const awalan = latihan ? 'Latihan · ' : '';
    if (state === 'confirmed_fall') {
        return { kode: latihan ? 'latihan' : 'jatuh', label: `${awalan}Kemungkinan jatuh · ${mmss(durasi)}` };
    }
    if (state === 'possible_fall') {
        const batas = ambang ? ` dari ${mmss(ambang)}` : '';
        return { kode: latihan ? 'latihan' : 'berbaring', label: `${awalan}Berbaring ${mmss(durasi)}${batas}` };
    }
    if (latihan) return { kode: 'latihan', label: 'Latihan berjalan' };
    if (adaOrang) return { kode: 'terpantau', label: 'Terpantau' };
    return { kode: 'kosong', label: 'AI tidak menemukan orang' };
}
