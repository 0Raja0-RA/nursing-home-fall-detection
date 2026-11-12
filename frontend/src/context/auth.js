import { createContext, useContext } from 'react';

/**
 * Akun yang sedang masuk. Nilainya diisi AuthProvider (AuthContext.jsx).
 *
 * status: 'memuat' | 'masuk' | 'keluar' | 'terputus' (backend tidak bisa dihubungi)
 * akun.role: 'pengelola' | 'perawat' | 'pengunjung' (lihat-saja, dari QR di stand)
 */
export const AuthContext = createContext({
    akun: null,
    status: 'memuat',
    sesiHabis: false,
    masuk: async () => {},
    masukPengunjung: async () => {},
    keluar: async () => {},
    periksa: async () => {},
});

export const useAuth = () => useContext(AuthContext);

/**
 * true untuk pengunjung pameran. Tombol yang mengubah data disembunyikan, tetapi
 * yang benar-benar menolaknya backend; ini hanya supaya tidak ada tombol yang
 * ditekan lalu gagal.
 */
export const usePengunjung = () => useContext(AuthContext).akun?.role === 'pengunjung';
