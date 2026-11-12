/**
 * putusan.js
 * ==========
 * Pilihan putusan dan alasan alarm palsu. Sama dengan LABEL_PUTUSAN dan
 * ALASAN_PALSU di backend (app/models/schemas.py), yang juga memvalidasinya.
 *
 * Disalin di sini, bukan hanya diambil dari /api/settings/, supaya formulir
 * penutupan alarm tetap tampil walau pengaturan gagal dimuat saat alarm berbunyi.
 */

export const PUTUSAN = [
    { id: 'jatuh', label: 'Jatuh sungguhan' },
    { id: 'palsu', label: 'Alarm palsu' },
    { id: 'belum_yakin', label: 'Belum yakin' },
];

export const ALASAN_PALSU = [
    { id: 'berbaring_sengaja', label: 'Berbaring sengaja' },
    { id: 'duduk_membungkuk', label: 'Duduk atau membungkuk' },
    { id: 'bukan_orang', label: 'Bukan orang' },
    { id: 'orang_lain', label: 'Orang lain di lantai' },
    { id: 'lainnya', label: 'Lainnya' },
];

export const labelPutusan = (id) => PUTUSAN.find((p) => p.id === id)?.label || 'Belum dinilai';
// Selalu teks: alarm palsu tanpa alasan (data lama atau disunting manual) tidak boleh membuat halaman crash.
export const labelAlasan = (id) => ALASAN_PALSU.find((a) => a.id === id)?.label || id || 'Alasan tidak tercatat';
