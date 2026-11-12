import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, bacaGalat, SESI_HABIS } from '../api';
import { AuthContext } from './auth';

/**
 * Sumber akun yang sedang masuk untuk seluruh aplikasi.
 *
 * Sesi tersimpan di cookie HttpOnly milik backend, jadi halaman tidak menyimpan
 * token apa pun. Saat dimuat, halaman cukup bertanya ke /api/auth/me.
 */
export function AuthProvider({ children }) {
    const [akun, setAkun] = useState(null);
    const [status, setStatus] = useState('memuat');
    // Diisi saat sesi berakhir di tengah pemakaian, supaya halaman Login bisa
    // menjelaskan kenapa pengguna tiba-tiba dikeluarkan.
    const [sesiHabis, setSesiHabis] = useState(false);

    const periksa = useCallback(async () => {
        try {
            const r = await api('/api/auth/me');
            if (r.ok) {
                setAkun(await r.json());
                setStatus('masuk');
            } else {
                setAkun(null);
                setStatus('keluar');
            }
        } catch {
            setStatus('terputus');
        }
    }, []);

    useEffect(() => {
        // setState terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        periksa();
    }, [periksa]);

    useEffect(() => {
        const habis = () => {
            setAkun(null);
            setStatus('keluar');
            setSesiHabis(true);
        };
        window.addEventListener(SESI_HABIS, habis);
        return () => window.removeEventListener(SESI_HABIS, habis);
    }, []);

    const terima = useCallback(async (r) => {
        if (!r.ok) throw new Error(await bacaGalat(r));
        setAkun(await r.json());
        setStatus('masuk');
        setSesiHabis(false);
    }, []);

    const masuk = useCallback(
        async (username, password) => terima(await api('/api/auth/login', { method: 'POST', json: { username, password } })),
        [terima],
    );

    // Pengunjung pameran: token dari QR di stand ditukar dengan sesi lihat-saja.
    const masukPengunjung = useCallback(
        async (token) => terima(await api('/api/auth/pengunjung', { method: 'POST', json: { token } })),
        [terima],
    );

    const keluar = useCallback(async () => {
        try {
            await api('/api/auth/logout', { method: 'POST' });
        } catch { /* backend mati: tetap keluar di layar ini */ }
        setAkun(null);
        setStatus('keluar');
        setSesiHabis(false);
    }, []);

    const nilai = useMemo(
        () => ({ akun, status, sesiHabis, masuk, masukPengunjung, keluar, periksa }),
        [akun, status, sesiHabis, masuk, masukPengunjung, keluar, periksa],
    );
    return <AuthContext.Provider value={nilai}>{children}</AuthContext.Provider>;
}
