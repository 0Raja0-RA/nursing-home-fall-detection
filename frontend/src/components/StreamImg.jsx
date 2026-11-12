import { useEffect, useRef } from 'react';

/**
 * Gambar MJPEG dari backend, yang melepas koneksinya saat dilepas dari DOM.
 *
 * MJPEG adalah respons HTTP yang tidak pernah selesai. Kalau elemen <img>-nya
 * dibuang tanpa mengosongkan src lebih dulu, browser menahan koneksi itu tetap
 * terbuka. Dengan beberapa kamera dan beberapa kali berpindah halaman, batas ~6
 * koneksi per host milik Chrome habis -- fetch berikutnya menggantung dan seluruh
 * dashboard terlihat membeku, padahal backend baik-baik saja.
 */
export default function StreamImg({ src, alt, kunci, onUkuran }) {
    const ref = useRef(null);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        // src dipasang di sini, bukan lewat atribut JSX. React.StrictMode menjalankan
        // efek dua kali di mode dev (pasang -> bersihkan -> pasang lagi); kalau src
        // ditulis di JSX, pembersihan pertama membatalkan permintaan dan React tidak
        // pernah memasangnya kembali karena prop-nya dianggap tidak berubah. Akibatnya
        // gambar kosong selamanya dengan net::ERR_ABORTED.
        el.src = src;
        // Ukuran gambar dibaca berkala, bukan dari onload: MJPEG tidak selalu memicu
        // onload, dan ukurannya berubah bila rotasi kamera diganti. Sampai ukurannya
        // diketahui dibaca tiap 0,3 detik, supaya kartu cepat berhenti berubah tinggi;
        // sesudahnya cukup tiap 2 detik. Efek ini hanya bergantung pada nilai yang
        // stabil, supaya aliran videonya tidak diulang.
        let t = null;
        const baca = (selang) => {
            t = setTimeout(() => {
                const ada = el.naturalWidth && el.naturalHeight;
                if (ada) onUkuran?.(kunci, el.naturalWidth, el.naturalHeight);
                baca(ada ? 2000 : 300);
            }, selang);
        };
        baca(300);
        return () => { clearTimeout(t); el.src = ''; };
    }, [src, kunci, onUkuran]);
    return <img ref={ref} alt={alt} className="absolute inset-0 w-full h-full object-contain" />;
}
