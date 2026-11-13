import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Footprints, HeartHandshake, Moon, Sun, TriangleAlert, Video } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import logoSvg from '../assets/logo.svg';

// Isinya mengikuti perilaku sistem sebenarnya (docs/architecture.md, prinsip privasi).
// Angka masa simpan adalah bawaan; pengelola bisa mengubahnya di backend/.env.
const DATA_DISIMPAN = [
    {
        apa: 'Video langsung',
        isi: 'Tidak direkam terus-menerus. Gambar diproses saat itu juga; hanya 30 detik terakhir yang ditahan di memori, dan baru disimpan bila ada alarm. Tampilan tiap kamera bisa utuh, buram, atau kerangka tubuh saja, dan kamera baru bawaannya buram.',
        siapa: 'tim perawat yang sudah masuk, dan pengunjung pameran lewat QR di stand, dengan tampilan yang sama',
    },
    {
        apa: 'Foto saat alarm',
        isi: 'Satu foto per alarm, dalam tampilan privasi kamera yang sama dengan videonya, dihapus otomatis setelah 30 hari. Foto yang dikirim ke grup Telegram bawaannya diburamkan, dan pesannya tidak bisa diteruskan atau disimpan.',
        siapa: 'siapa pun yang bisa melihat videonya di dasbor, dan anggota grup Telegram perawat dalam versi buram',
    },
    {
        apa: 'Klip kejadian',
        isi: 'Dari sekitar 5 detik sebelum orangnya terbaca berbaring sampai 5 detik sesudah alarm, dalam tampilan privasi kamera, dihapus otomatis setelah 7 hari. Tidak pernah dikirim ke Telegram.',
        siapa: 'siapa pun yang bisa melihat videonya di dasbor',
    },
    {
        apa: 'Video asli kamera berprivasi',
        isi: 'Saat ada alarm, perawat bisa membuka video tanpa buram selama 15 detik untuk memastikan keadaan. Setiap pembukaan dicatat: siapa, kamera mana, dan kapan.',
        siapa: 'akun tim perawat',
    },
    {
        apa: 'Riwayat insiden',
        isi: 'Jam alarm, siapa yang menuju lokasi dan menangani, putusan jatuh atau alarm palsu, dan catatan perawat. Disimpan untuk laporan dan untuk menilai seberapa sering sistem keliru.',
        siapa: 'akun tim perawat; pengunjung pameran hanya bisa melihat, tanpa bisa mengubah apa pun',
    },
];

const LANGKAH = [
    {
        judul: 'Kamera membaca postur',
        isi: 'Kamera di kamar mengirim gambar ke komputer panti yang menjalankan FallDetect. Model AI membaca postur setiap orang di gambar: tegak, transisi, atau berbaring.',
    },
    {
        judul: 'Lama berbaring dihitung',
        isi: 'Bila seseorang terbaca berbaring melewati batas waktu yang diatur panti, alarm berbunyi di dasbor dan grup Telegram perawat. Yang dihitung postur dan lamanya, bukan benturan, jadi berbaring di lantai dengan sengaja pun bisa memicu alarm.',
    },
    {
        judul: 'Perawat yang memutuskan',
        isi: 'Satu perawat menekan Saya ke sana supaya yang lain tidak ikut berangkat, menolong, lalu menandai apakah itu benar jatuh. Putusan itu dipakai untuk mengukur seberapa sering sistem keliru.',
    },
];

/**
 * Contoh tampilan alarm, menggantikan foto stok: yang ditunjukkan produknya sendiri.
 * Tombolnya bukan tombol sungguhan, jadi seluruh kartu dibaca pembaca layar sebagai satu gambar.
 */
function ContohAlarm() {
    return (
        <figure className="w-full max-w-md mx-auto md:mr-0">
            <div
                role="img"
                aria-label="Contoh tampilan alarm: kemungkinan jatuh di Kamar 101, terbaca berbaring 12 detik, belum direspons, dengan tombol Saya ke sana dan Lihat kamera. Di bawahnya linimasa penanganan sampai putusan jatuh sungguhan."
                className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden"
            >
                <div aria-hidden="true" className="bg-red-700 text-white p-4 sm:p-5">
                    <p className="flex items-center gap-2 text-xs font-semibold">
                        <TriangleAlert className="w-4 h-4 shrink-0" />
                        Kemungkinan jatuh · belum direspons 0:42
                        <span className="ml-auto rounded bg-white/20 px-1.5 py-0.5 font-medium">Contoh</span>
                    </p>
                    <p className="mt-1 text-xl font-bold">Kamar 101</p>
                    <p className="text-sm text-white/90">Terbaca berbaring 12 detik · 22.14</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                        <span className="min-h-10 px-3 rounded-lg bg-white text-red-800 text-sm font-semibold inline-flex items-center gap-1.5">
                            <Footprints className="w-4 h-4" /> Saya ke sana
                        </span>
                        <span className="min-h-10 px-3 rounded-lg border border-white/70 text-sm font-semibold inline-flex items-center gap-1.5">
                            <Video className="w-4 h-4" /> Lihat kamera
                        </span>
                    </div>
                </div>
                <ol aria-hidden="true" className="p-4 sm:p-5 space-y-2.5 text-sm text-slate-700 dark:text-slate-300">
                    {[
                        ['22.14', 'Alarm di dasbor dan grup Telegram perawat'],
                        ['22.15', 'Siti menekan Saya ke sana; bunyi berhenti di semua layar'],
                        ['22.18', 'Ditangani. Putusan: jatuh sungguhan'],
                    ].map(([jam, isi]) => (
                        <li key={jam} className="grid grid-cols-[3rem_minmax(0,1fr)] gap-2">
                            <span className="text-slate-500 tabular-nums">{jam}</span>
                            <span>{isi}</span>
                        </li>
                    ))}
                </ol>
            </div>
            <figcaption className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                Contoh tampilan. Nama ruang, orang, dan jam hanya ilustrasi.
            </figcaption>
        </figure>
    );
}

export default function LandingPage() {
    const navigate = useNavigate();
    const { hash } = useLocation();
    const { darkMode, toggleTheme } = useTheme();

    // Tautan /#privasi dari halaman Login: router tidak menggulir ke jangkar dengan sendirinya.
    useEffect(() => {
        if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
    }, [hash]);

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 transition-colors">
            {/* Navbar */}
            <nav className="flex justify-between items-center px-4 sm:px-8 py-6 max-w-7xl mx-auto">
                <div className="flex items-center gap-3">
                    {/* Logo Kustom: Perisai Kesehatan (Emerald Green) */}
                    <div className="flex items-center gap-2.5">
                        {/* Di HP logo diperkecil dan subjudul disembunyikan, supaya tombol masuk
                            tidak menimpa nama FallDetect di layar 360 px. */}
                        <img src={logoSvg} alt="" className="w-12 h-12 sm:w-20 sm:h-20 object-contain" />
                        <div>
                            <span className="text-2xl sm:text-3xl font-bold tracking-tight block text-slate-900 dark:text-white">FallDetect</span>
                            <span className="hidden sm:block text-2xs text-emerald-600 dark:text-emerald-400 font-medium">Pemantauan jatuh untuk panti</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-2 sm:gap-4">
                    <a href="#cara-kerja" className="hidden sm:inline text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                        Cara kerja
                    </a>
                    <a href="#privasi" className="hidden sm:inline text-sm font-medium text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                        Privasi
                    </a>
                    <button
                        onClick={toggleTheme}
                        className="p-2.5 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors hover:bg-emerald-50 dark:hover:bg-emerald-950/50"
                        title="Ubah tema"
                        aria-label="Ubah tema"
                    >
                        {darkMode ? <Sun className="w-5 h-5 text-emerald-400" /> : <Moon className="w-5 h-5 text-emerald-600" />}
                    </button>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 sm:px-5 py-2.5 rounded-xl font-medium transition-colors flex items-center gap-2 shrink-0"
                    >
                        <span className="sm:hidden">Masuk</span>
                        <span className="hidden sm:inline">Login Caregiver</span>
                        <ArrowRight className="hidden sm:block w-4 h-4" aria-hidden="true" />
                    </button>
                </div>
            </nav>

            {/* Hero Section */}
            <header className="max-w-7xl mx-auto px-6 py-12 md:py-20 grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                <div>
                    <span className="inline-block px-3.5 py-1.5 rounded-2xl text-xs font-semibold leading-snug bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20">
                        Prototipe proyek mahasiswa, bukan alat kesehatan bersertifikat
                    </span>
                    <h1 className="text-4xl md:text-5xl font-extrabold mt-6 mb-6 tracking-tight leading-tight text-slate-900 dark:text-white">
                        Membantu perawat tahu lebih cepat saat penghuni jatuh
                    </h1>
                    <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                        Kamera di kamar mengirim gambar ke server. Model AI membaca posisi tubuh, dan bila seseorang
                        terbaca berbaring melewati batas waktu, dasbor dan grup Telegram perawat diberi tahu. Sistem bisa
                        melewatkan kejadian dan bisa memberi alarm palsu, jadi tidak menggantikan pengawasan perawat.
                    </p>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg transition-colors flex items-center gap-3"
                    >
                        <HeartHandshake className="w-5 h-5" aria-hidden="true" /> Masuk ke dasbor
                    </button>
                </div>

                <ContohAlarm />
            </header>

            <section id="cara-kerja" aria-labelledby="judul-cara-kerja" className="border-t border-slate-200 dark:border-slate-800 scroll-mt-6">
                <div className="max-w-7xl mx-auto px-6 py-16 md:py-20">
                    <h2 id="judul-cara-kerja" className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                        Cara kerjanya
                    </h2>
                    <ol className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-8">
                        {LANGKAH.map((l, i) => (
                            <li key={l.judul} className="border-t-2 border-slate-300 dark:border-slate-700 pt-4">
                                <p className="text-sm font-semibold text-slate-500 dark:text-slate-400 tabular-nums">{i + 1}</p>
                                <h3 className="mt-1 font-semibold text-slate-900 dark:text-white">{l.judul}</h3>
                                <p className="mt-2 text-slate-600 dark:text-slate-400 leading-relaxed">{l.isi}</p>
                            </li>
                        ))}
                    </ol>
                </div>
            </section>

            <section id="privasi" aria-labelledby="judul-privasi" className="border-t border-slate-200 dark:border-slate-800 scroll-mt-6">
                <div className="max-w-7xl mx-auto px-6 py-16 md:py-20 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-10">
                    <div>
                        <h2 id="judul-privasi" className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                            Apa yang disimpan, dan siapa yang melihat
                        </h2>
                        <p className="mt-4 text-slate-600 dark:text-slate-400 leading-relaxed">
                            Gambar dari kamar penghuni adalah data kesehatan. Database, foto, dan klip tersimpan di komputer
                            yang menjalankan FallDetect; yang keluar hanya pesan alarm ke grup Telegram perawat. Tidak ada
                            pengenalan wajah.
                        </p>
                    </div>
                    <dl className="divide-y divide-slate-200 dark:divide-slate-800">
                        {DATA_DISIMPAN.map((d) => (
                            <div key={d.apa} className="py-5 first:pt-0 last:pb-0 grid grid-cols-1 sm:grid-cols-[11rem_minmax(0,1fr)] gap-x-6 gap-y-1">
                                <dt className="font-semibold text-slate-900 dark:text-white">{d.apa}</dt>
                                <dd className="text-slate-600 dark:text-slate-400 leading-relaxed">
                                    {d.isi}
                                    <span className="block mt-1.5 text-sm text-slate-500 dark:text-slate-400">Bisa dilihat: {d.siapa}.</span>
                                </dd>
                            </div>
                        ))}
                    </dl>
                </div>
            </section>
        </div>
    );
}