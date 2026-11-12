import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Sun, Moon, HeartHandshake } from 'lucide-react';
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
        isi: 'Satu foto per alarm, dihapus otomatis setelah 30 hari. Foto yang dikirim ke grup Telegram bawaannya diburamkan, dan pesannya tidak bisa diteruskan atau disimpan.',
        siapa: 'akun tim perawat, dan anggota grup Telegram perawat dalam versi buram',
    },
    {
        apa: 'Klip kejadian',
        isi: 'Dari sekitar 5 detik sebelum orangnya terbaca berbaring sampai 5 detik sesudah alarm, dihapus otomatis setelah 7 hari. Tidak pernah dikirim ke Telegram.',
        siapa: 'akun tim perawat',
    },
    {
        apa: 'Video asli kamera berprivasi',
        isi: 'Saat ada alarm, perawat bisa membuka video tanpa buram selama 15 detik untuk memastikan keadaan. Setiap pembukaan dicatat: siapa, kamera mana, dan kapan.',
        siapa: 'akun tim perawat',
    },
    {
        apa: 'Riwayat insiden',
        isi: 'Jam alarm, siapa yang menuju lokasi dan menangani, putusan jatuh atau alarm palsu, dan catatan perawat. Disimpan untuk laporan dan untuk menilai seberapa sering sistem keliru.',
        siapa: 'akun tim perawat; pengunjung pameran hanya bisa melihat, tanpa foto dan klip',
    },
];

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
                        <img src={logoSvg} alt="" className="w-20 h-20 object-contain" />
                        <div>
                            <span className="text-3xl font-bold tracking-tight block text-slate-900 dark:text-white">FallDetect</span>
                            <span className="text-2xs text-emerald-600 dark:text-emerald-400 font-medium">Pemantauan jatuh untuk panti</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-2 sm:gap-4">
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
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl font-medium transition-colors flex items-center gap-2 shadow-lg shadow-emerald-600/20"
                    >
                        Login Caregiver <ArrowRight className="w-4 h-4" />
                    </button>
                </div>
            </nav>

            {/* Hero Section */}
            <header className="max-w-7xl mx-auto px-6 py-12 md:py-20 grid grid-cols-1 md:grid-cols-2 gap-12 items-center">
                <div>
                    <span className="px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        Prototipe proyek mahasiswa, bukan alat kesehatan bersertifikat
                    </span>
                    <h1 className="text-4xl md:text-5xl font-extrabold mt-6 mb-6 tracking-tight leading-tight">
                        Membantu perawat tahu <br />
                        <span className="text-emerald-600 dark:text-emerald-400">lebih cepat saat penghuni jatuh</span>
                    </h1>
                    <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                        Kamera di kamar mengirim gambar ke server. Model AI membaca posisi tubuh, dan bila seseorang
                        terbaca berbaring melewati batas waktu, dasbor dan grup Telegram perawat diberi tahu. Sistem bisa
                        melewatkan kejadian dan bisa memberi alarm palsu, jadi tidak menggantikan pengawasan perawat.
                    </p>
                    <button
                        onClick={() => navigate('/login')}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white px-8 py-4 rounded-2xl font-semibold text-lg shadow-xl shadow-emerald-600/25 transition-all flex items-center gap-3"
                    >
                        <HeartHandshake className="w-5 h-5" aria-hidden="true" /> Masuk ke dasbor
                    </button>
                </div>

                {/* Gambar Ilustrasi Caregiver & Lansia */}
                <div className="relative">
                    <div className="relative rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-2xl bg-slate-900">
                        <img
                            src="https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?q=80&w=1000&auto=format&fit=crop"
                            alt="Caregiver mendampingi lansia di panti jompo"
                            className="w-full h-[400px] object-cover opacity-90 hover:scale-105 transition-transform duration-700"
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-transparent to-transparent flex items-end p-6">
                            <div className="text-white">
                                <p className="font-semibold text-sm">Dirancang untuk perawat panti</p>
                                <p className="text-xs text-slate-300">Foto ilustrasi.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

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