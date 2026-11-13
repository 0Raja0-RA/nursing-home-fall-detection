import { createContext, useContext } from 'react';

/**
 * Pesan sementara ("Tersimpan.", "Gagal menyimpan …") sebagai toast di pojok kanan
 * bawah, bukan teks yang menyisip di halaman dan menggeser isinya.
 *
 * kabari(teks)            pesan biasa, hilang sendiri setelah beberapa detik
 * kabari(teks, 'galat')   galat yang perlu ditindaklanjuti, tetap sampai ditutup
 */
export const KonteksToast = createContext(() => {});

export const useToast = () => useContext(KonteksToast);
