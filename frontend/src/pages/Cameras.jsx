import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Clock, Info, Loader2, Plug, Plus, Power, Radar, ScanEye, Settings2, Trash2, Usb, VideoOff, X } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { jamDari } from '../statusKamera';
import { msDari, useJam } from '../waktu';

const ROTASI = [0, 90, 180, 270];
const INPUT = 'w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';
const LABEL = 'block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-1.5';
const TOMBOL = 'min-h-11 px-4 rounded-xl text-sm font-semibold inline-flex items-center justify-center gap-2 transition-colors disabled:opacity-60';
const TOMBOL_NETRAL = `${TOMBOL} border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800`;

/** Sisipkan nama pengguna dan kata sandi ke alamat rtsp:// atau http://, kalau diisi. */
function gabungSandi(alamat, pengguna, sandi) {
    if (!pengguna) return alamat;
    const m = alamat.match(/^([a-z][a-z0-9+.-]*:\/\/)(.*)$/i);
    if (!m || m[2].split('/')[0].includes('@')) return alamat;
    const kredensial = encodeURIComponent(pengguna) + (sandi ? `:${encodeURIComponent(sandi)}` : '');
    return `${m[1]}${kredensial}@${m[2]}`;
}

const pakaiJaringan = (alamat) => /^(rtsp|https?):\/\//i.test(alamat.trim());

/** Langkah periksa sesuai jenis alamat, dari yang paling sering terjadi. */
function daftarPeriksa(alamat) {
    const a = alamat.trim();
    if (/^https?:\/\//i.test(a)) {
        return [
            'Aplikasi kamera di HP (mis. IP Webcam) sudah menyala dan server-nya sudah dimulai.',
            'HP dan laptop ada di jaringan yang sama. WiFi kampus atau publik sering memblokir koneksi antarperangkat; pakai hotspot.',
            'Alamatnya sama persis dengan yang tampil di layar HP, termasuk port dan /video.',
            'Coba buka alamat itu di browser laptop. Bila tidak tampil di browser, FallDetect juga tidak bisa membukanya.',
        ];
    }
    if (/^rtsp:\/\//i.test(a)) {
        return [
            'Nama pengguna dan sandi kamera benar.',
            'Port RTSP (biasanya 554) dan jalur stream sesuai manual kamera, mis. /stream1.',
            'Kamera dan laptop ada di jaringan yang sama.',
        ];
    }
    if (/^\d+$/.test(a)) {
        return [
            'Tutup aplikasi lain yang memakai kamera: browser, Zoom, atau aplikasi Kamera.',
            'Kamera kedua atau Iriun biasanya berindeks 1 atau 2.',
        ];
    }
    return ['Periksa jalur berkas video. Jalur dibaca di laptop yang menjalankan backend.'];
}

/** Status kamera beserta alasannya, bukan sekadar Terhubung atau Terputus. */
function StatusKameraDaftar({ cam }) {
    const ms = msDari(cam.last_frame_at);
    const jam = Number.isFinite(ms) ? jamDari(ms) : null;
    if (!cam.enabled) {
        return (
            <p className="text-xs text-slate-500">
                <span className="font-semibold text-slate-700 dark:text-slate-300">Dimatikan.</span> Ruang ini tidak dipantau.
            </p>
        );
    }
    // Backend hanya mengisi dijeda_sampai selama Mode perawatan masih berjalan.
    const jeda = msDari(cam.dijeda_sampai);
    if (cam.is_active && Number.isFinite(jeda)) {
        return (
            <p className="text-xs text-slate-700 dark:text-slate-300 tabular-nums">
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 mr-1.5 rounded border border-blue-500 text-blue-800 dark:text-blue-200 font-semibold">
                    <Clock className="w-3 h-3" aria-hidden="true" /> Mode perawatan
                </span>
                sampai {jamDari(jeda)}{cam.dijeda_oleh ? `, oleh ${cam.dijeda_oleh}` : ''}. Deteksi dan video dijeda.
            </p>
        );
    }
    if (cam.is_active) {
        return (
            <p className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1.5" aria-hidden="true" />
                <span className="font-semibold text-slate-800 dark:text-slate-200">Terhubung</span>
                {cam.fps > 0 && ` · ${cam.fps.toFixed(1)} fps`}
                {jam && ` · gambar terakhir ${jam}`}
            </p>
        );
    }
    return (
        <p className="text-xs text-slate-700 dark:text-slate-300">
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 mr-1.5 rounded border border-dashed border-slate-400 font-semibold">
                <VideoOff className="w-3 h-3" aria-hidden="true" /> Terputus
            </span>
            {jam ? `sejak ${jam}` : 'belum pernah mengirim gambar'}. Periksa daya, jaringan, dan alamatnya.
        </p>
    );
}

/** Gambar diam terakhir kamera, disegarkan berkala. Bukan stream, supaya daftar ini ringan. */
function GambarMini({ cam, t }) {
    const src = `${API_BASE}/api/cameras/${cam.camera_id}/snapshot?t=${t}`;
    // Alamat gambar berganti setiap beberapa detik, jadi gambar yang tadi gagal
    // otomatis dicoba lagi: kamera yang tadi mati bisa sudah hidup.
    const [srcGagal, setSrcGagal] = useState(null);
    const kosong = !cam.is_active || srcGagal === src;
    return (
        <div className="relative aspect-video bg-slate-950 rounded-xl overflow-hidden">
            {kosong ? (
                <div className="absolute inset-0 flex items-center justify-center text-slate-400">
                    <VideoOff className="w-6 h-6" aria-hidden="true" />
                </div>
            ) : (
                <img
                    src={src}
                    alt={`Gambar terakhir ${cam.name}`}
                    onError={() => setSrcGagal(src)}
                    className="absolute inset-0 w-full h-full object-contain"
                />
            )}
        </div>
    );
}

/** Panel pengaturan satu kamera: rotasi tepat di pratinjau, nama, alamat, nyala/mati, hapus. */
const PRIVASI = [
    { id: 'utuh', label: 'Utuh', arti: 'Video asli tampil di dashboard, foto kejadian, dan klip.' },
    { id: 'buram', label: 'Buram', arti: 'Wajah dan detail tidak terbaca; postur dan kerangka tetap terlihat. Saat ada alarm, perawat bisa membuka video asli 15 detik, dan pembukaannya tercatat.' },
    { id: 'kerangka', label: 'Kerangka saja', arti: 'Hanya kerangka dan kotak deteksi di latar gelap. Saat ada alarm, video asli bisa dibuka 15 detik dan tercatat.' },
];
const labelPrivasi = (id) => PRIVASI.find((p) => p.id === id)?.label || 'Utuh';

function PanelKamera({ cam, t, onUbah, onHapus, onTutup }) {
    const [nama, setNama] = useState(cam.name);
    const [alamat, setAlamat] = useState('');
    const [sibuk, setSibuk] = useState('');
    const [kabar, setKabar] = useState(null);

    const ubah = async (isi, label) => {
        setSibuk(label);
        setKabar(null);
        const hasil = await onUbah(cam.camera_id, isi);
        setSibuk('');
        setKabar(hasil === true ? { ok: true, teks: 'Tersimpan.' } : { ok: false, teks: hasil });
        if (hasil === true && isi.source) setAlamat('');
    };

    return (
        <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-800 space-y-4">
            <div>
                <GambarMini cam={cam} t={t} />
                <fieldset className="mt-2">
                    <legend className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                        Putar gambar (searah jarum jam). Model membaca gambar yang sudah diputar.
                    </legend>
                    <div className="flex gap-2">
                        {ROTASI.map((d) => (
                            <button
                                key={d}
                                type="button"
                                aria-pressed={cam.rotate === d}
                                disabled={Boolean(sibuk)}
                                onClick={() => ubah({ rotate: d }, 'rotasi')}
                                className={`min-h-10 flex-1 rounded-lg text-sm font-semibold border tabular-nums ${cam.rotate === d
                                    ? 'bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900'
                                    : 'border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                            >
                                {d}&deg;
                            </button>
                        ))}
                    </div>
                </fieldset>
                <fieldset className="mt-3">
                    <legend className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                        Tampilan video. Model tetap membaca gambar asli.
                    </legend>
                    <div className="flex gap-2">
                        {PRIVASI.map((p) => (
                            <button
                                key={p.id}
                                type="button"
                                aria-pressed={(cam.privasi || 'utuh') === p.id}
                                disabled={Boolean(sibuk)}
                                onClick={() => ubah({ privasi: p.id }, 'privasi')}
                                className={`min-h-10 flex-1 rounded-lg text-sm font-semibold border ${(cam.privasi || 'utuh') === p.id
                                    ? 'bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900'
                                    : 'border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                            >
                                {p.label}
                            </button>
                        ))}
                    </div>
                    <p className="text-xs text-slate-500 mt-1.5">
                        {PRIVASI.find((p) => p.id === (cam.privasi || 'utuh'))?.arti} Foto kejadian, klip, dan Telegram
                        mengikuti tampilan ini.
                    </p>
                </fieldset>
                <fieldset className="mt-3">
                    <legend className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5">
                        Letak di denah unit pada layar dinding
                    </legend>
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                        {[['denah_baris', 'Baris'], ['denah_kolom', 'Kolom']].map(([kunci, label]) => (
                            <label key={kunci} className="inline-flex items-center gap-2">
                                {label}
                                <select
                                    value={cam[kunci] || 0}
                                    disabled={Boolean(sibuk)}
                                    onChange={(e) => ubah({ [kunci]: Number(e.target.value) }, 'denah')}
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-2 py-1.5"
                                >
                                    <option value={0}>–</option>
                                    {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                                </select>
                            </label>
                        ))}
                        <span className="text-xs text-slate-500">Kosongkan salah satunya untuk mengeluarkan ruang ini dari denah.</span>
                    </div>
                </fieldset>
            </div>

            <form onSubmit={(e) => { e.preventDefault(); ubah({ name: nama }, 'nama'); }} className="flex flex-col sm:flex-row gap-2 sm:items-end">
                <label className="flex-1">
                    <span className={LABEL}>Nama ruang</span>
                    <input value={nama} onChange={(e) => setNama(e.target.value)} required maxLength={100} className={INPUT} />
                </label>
                <button type="submit" disabled={Boolean(sibuk) || !nama.trim() || nama === cam.name} className={TOMBOL_NETRAL}>
                    {sibuk === 'nama' ? 'Menyimpan…' : 'Simpan nama'}
                </button>
            </form>

            <form onSubmit={(e) => { e.preventDefault(); ubah({ source: alamat.trim() }, 'alamat'); }} className="flex flex-col sm:flex-row gap-2 sm:items-end">
                <label className="flex-1">
                    <span className={LABEL}>Alamat baru</span>
                    <input value={alamat} onChange={(e) => setAlamat(e.target.value)} placeholder={cam.source}
                        className={`${INPUT} font-mono`} spellCheck={false} autoCapitalize="none" />
                    <span className="block text-xs text-slate-500 mt-1">Kosongkan bila alamatnya tidak berubah. Alamat diperiksa dulu sebelum disimpan.</span>
                </label>
                <button type="submit" disabled={Boolean(sibuk) || !alamat.trim()} className={TOMBOL_NETRAL}>
                    {sibuk === 'alamat' ? 'Memeriksa…' : 'Ganti alamat'}
                </button>
            </form>

            {kabar && (
                <p role="status" className={`text-sm ${kabar.ok ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                    {kabar.teks}
                </p>
            )}

            <div className="flex flex-wrap gap-2">
                <button type="button" disabled={Boolean(sibuk)} onClick={() => ubah({ enabled: !cam.enabled }, 'nyala')} className={TOMBOL_NETRAL}>
                    <Power className="w-4 h-4" aria-hidden="true" /> {cam.enabled ? 'Matikan kamera' : 'Nyalakan kamera'}
                </button>
                <button type="button" onClick={() => onHapus(cam.camera_id, cam.name)} className={`${TOMBOL_NETRAL} hover:text-red-700 dark:hover:text-red-400`}>
                    <Trash2 className="w-4 h-4" aria-hidden="true" /> Hapus kamera
                </button>
                <button type="button" onClick={onTutup} className={`${TOMBOL} text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 sm:ml-auto`}>
                    Tutup
                </button>
            </div>
        </div>
    );
}

export default function Cameras() {
    const [cameras, setCameras] = useState([]);
    const [nama, setNama] = useState('');
    const [alamat, setAlamat] = useState('');
    const [pengguna, setPengguna] = useState('');
    const [sandi, setSandi] = useState('');
    const [pesan, setPesan] = useState(null);          // { tipe: 'error' | 'info' | 'koneksi', teks }
    const [menambah, setMenambah] = useState(false);
    const [memindai, setMemindai] = useState(false);
    const [kandidat, setKandidat] = useState(null);     // hasil pemindaian jaringan
    const [tes, setTes] = useState(null);               // { memuat } atau { hasil, alamat }
    const [atur, setAtur] = useState(null);             // id kamera yang panelnya terbuka
    const t = useJam(5000);

    const ambilDaftar = useCallback(async () => {
        try {
            const r = await api('/api/cameras/');
            if (!r.ok) throw new Error(`Backend menjawab ${r.status}`);
            setCameras(await r.json());
            setPesan((p) => (p?.tipe === 'koneksi' ? null : p));
        } catch {
            setPesan({ tipe: 'koneksi', teks: PESAN_TERPUTUS });
        }
    }, []);

    // Muat daftar di awal, lalu segarkan berkala supaya status Terhubung/Terputus ikut hidup.
    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambilDaftar();
        const timer = setInterval(ambilDaftar, 3000);
        return () => clearInterval(timer);
    }, [ambilDaftar]);

    const tambahKamera = async (e) => {
        e.preventDefault();
        if (!nama.trim() || !alamat.trim() || menambah) return;
        if (sandi && !pengguna) {
            setPesan({ tipe: 'error', teks: 'Isi nama pengguna kamera juga, atau kosongkan kata sandinya.' });
            return;
        }
        setMenambah(true);
        setPesan(null);
        try {
            const r = await api('/api/cameras/', {
                method: 'POST',
                json: { name: nama.trim(), source: gabungSandi(alamat.trim(), pengguna.trim(), sandi), rotate: 0 },
            });
            if (!r.ok) {
                setPesan({ tipe: 'error', teks: await bacaGalat(r) });
                return;
            }
            setNama('');
            setAlamat('');
            setPengguna('');
            setSandi('');
            setKandidat(null);
            await ambilDaftar();
        } catch {
            setPesan({ tipe: 'error', teks: PESAN_TERPUTUS });
        } finally {
            setMenambah(false);
        }
    };

    /** Returns: true kalau berhasil, atau pesan galat. */
    const ubahKamera = async (id, isi) => {
        try {
            const r = await api(`/api/cameras/${id}`, { method: 'PATCH', json: isi });
            if (!r.ok) return bacaGalat(r);
            await ambilDaftar();
            return true;
        } catch {
            return PESAN_TERPUTUS;
        }
    };

    const hapusKamera = async (id, namaKamera) => {
        // Satu klik tidak boleh langsung menghentikan pemantauan sebuah ruangan.
        const setuju = window.confirm(
            `Hapus ${namaKamera}? Kamera berhenti memantau dan dihapus dari daftar. Riwayat insidennya tetap tersimpan.`,
        );
        if (!setuju) return;
        setPesan(null);
        try {
            const r = await api(`/api/cameras/${id}`, { method: 'DELETE' });
            if (!r.ok && r.status !== 204) setPesan({ tipe: 'error', teks: await bacaGalat(r) });
            setAtur(null);
            await ambilDaftar();
        } catch {
            setPesan({ tipe: 'error', teks: PESAN_TERPUTUS });
        }
    };

    // Dua sumber kamera dicari sekaligus:
    //  - perangkat lokal (webcam laptop, Iriun lewat USB/WiFi) yang muncul sebagai indeks
    //  - perangkat di jaringan (IP Webcam di HP), yang alamatnya berubah tiap pindah WiFi
    // Keduanya digabung di satu tombol supaya tidak perlu menebak harus menekan yang mana.
    const pindaiJaringan = async () => {
        setMemindai(true);
        setPesan(null);
        setKandidat(null);
        try {
            const [rLokal, rJaringan] = await Promise.all([
                api('/api/cameras/devices'),
                api('/api/cameras/scan', { method: 'POST' }),
            ]);
            if (!rJaringan.ok) {
                setPesan({ tipe: 'error', teks: await bacaGalat(rJaringan) });
                return;
            }
            const jaringan = await rJaringan.json();
            const lokal = rLokal.ok ? await rLokal.json() : [];
            setKandidat({ lokal, jaringan });

            if (lokal.length === 0 && jaringan.candidates.length === 0) {
                setPesan({
                    tipe: 'info',
                    teks: `Tidak ada kamera ditemukan di ${jaringan.subnets.join(', ') || 'jaringan ini'}, `
                        + 'dan tidak ada kamera yang terpasang di komputer ini.',
                    langkah: [
                        'Aplikasi kamera di HP sudah menyala dan server-nya sudah dimulai.',
                        'HP dan laptop ada di jaringan yang sama. WiFi kampus biasanya memblokir koneksi antarperangkat; nyalakan hotspot di laptop lalu sambungkan HP ke sana.',
                        'Tekan Cari kamera lagi setelah keduanya siap, atau ketik alamat dari layar HP lalu tekan Tes koneksi.',
                    ],
                });
            }
        } catch {
            setPesan({ tipe: 'error', teks: PESAN_TERPUTUS });
        } finally {
            setMemindai(false);
        }
    };

    /** Buka alamat dan tampilkan gambarnya sebelum kamera disimpan. */
    const tesKoneksi = async () => {
        const sumber = gabungSandi(alamat.trim(), pengguna.trim(), sandi);
        if (!alamat.trim()) {
            setPesan({ tipe: 'error', teks: 'Isi alamat kamera dulu, lalu tekan Tes koneksi.' });
            return;
        }
        setPesan(null);
        setTes({ memuat: true });
        try {
            const r = await api('/api/cameras/tes', { method: 'POST', json: { source: sumber } });
            if (!r.ok) throw new Error(await bacaGalat(r));
            setTes({ hasil: await r.json(), alamat: alamat.trim() });
        } catch (err) {
            setTes(null);
            setPesan({ tipe: 'error', teks: err instanceof TypeError ? PESAN_TERPUTUS : err.message });
        }
    };

    const pilihKandidat = (source) => {
        setAlamat(source);
        setKandidat(null);
    };

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0">
            <div className="mb-6">
                <h1 className="text-xl md:text-2xl font-bold">Daftar Kamera</h1>
                <p className="text-xs md:text-sm text-slate-500">
                    Setiap kamera mewakili satu ruang. Kata sandi kamera disimpan di server dan tidak ditampilkan lagi.
                </p>
            </div>

            {/* Formulir tambah kamera */}
            <form onSubmit={tambahKamera} className="bg-white dark:bg-slate-900 p-4 md:p-6 rounded-2xl border border-slate-200 dark:border-slate-800 mb-6 shadow-sm space-y-4">
                <h2 className="font-semibold">Tambah kamera</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <label>
                        <span className={LABEL}>Nama ruang</span>
                        <input value={nama} onChange={(e) => setNama(e.target.value)} required maxLength={100}
                            placeholder="Contoh: Kamar 101" className={INPUT} />
                    </label>
                    <label>
                        <span className={LABEL}>Alamat kamera</span>
                        <input value={alamat} onChange={(e) => setAlamat(e.target.value)} required
                            placeholder="http://192.168.43.1:8080/video" spellCheck={false} autoCapitalize="none"
                            className={`${INPUT} font-mono`} />
                        <span className="block text-xs text-slate-500 mt-1">
                            Webcam laptop: <code>0</code>. Kamera HP (IP Webcam): <code>http://IP-HP:8080/video</code>.
                            CCTV: <code>rtsp://IP:554/stream1</code>. Atau tekan Cari kamera.
                        </span>
                    </label>
                </div>

                {pakaiJaringan(alamat) && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <label>
                            <span className={LABEL}>Nama pengguna kamera <span className="font-normal text-slate-500">(opsional)</span></span>
                            <input value={pengguna} onChange={(e) => setPengguna(e.target.value)} autoComplete="off"
                                spellCheck={false} autoCapitalize="none" className={INPUT} />
                        </label>
                        <label>
                            <span className={LABEL}>Kata sandi kamera <span className="font-normal text-slate-500">(opsional)</span></span>
                            <input type="password" value={sandi} onChange={(e) => setSandi(e.target.value)} autoComplete="new-password" className={INPUT} />
                        </label>
                    </div>
                )}

                <p className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-400">
                    <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                    Sebelum memasang kamera, beri tahu penghuni dan keluarganya, dan pasang pemberitahuan bahwa ruang itu dipantau kamera.
                </p>

                <div className="flex flex-col sm:flex-row gap-2">
                    <button type="submit" disabled={menambah} className={`${TOMBOL} bg-emerald-700 hover:bg-emerald-800 text-white`}>
                        {menambah
                            ? <><Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Memeriksa alamat…</>
                            : <><Plus className="w-4 h-4" aria-hidden="true" /> Tambah kamera</>}
                    </button>
                    <button type="button" onClick={tesKoneksi} disabled={tes?.memuat} className={TOMBOL_NETRAL}>
                        {tes?.memuat ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Plug className="w-4 h-4" aria-hidden="true" />}
                        Tes koneksi
                    </button>
                    <button type="button" onClick={pindaiJaringan} disabled={memindai} className={TOMBOL_NETRAL}>
                        {memindai ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Radar className="w-4 h-4" aria-hidden="true" />}
                        Cari kamera
                    </button>
                </div>
            </form>

            {/* Hasil Tes koneksi: gambar pratinjau, atau sebab dan daftar periksa. */}
            {tes?.hasil && (
                <div role="status" className="mb-6 p-4 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm flex flex-col sm:flex-row gap-4">
                    {tes.hasil.ok ? (
                        <>
                            <img src={`data:image/jpeg;base64,${tes.hasil.gambar}`} alt="Pratinjau kamera"
                                className="w-full sm:w-64 rounded-lg bg-slate-950 self-start" />
                            <div className="space-y-1">
                                <p className="font-semibold inline-flex items-center gap-2">
                                    <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" /> Terhubung
                                </p>
                                <p className="text-slate-600 dark:text-slate-400 tabular-nums">
                                    {tes.hasil.lebar} × {tes.hasil.tinggi} piksel
                                    {tes.hasil.fps ? `, sekitar ${String(tes.hasil.fps).replace('.', ',')} gambar per detik` : ''}.
                                    Gambar pertama {String(tes.hasil.detik_gambar_pertama).replace('.', ',')} detik.
                                </p>
                                <p className="text-xs text-slate-500">
                                    Gambar miring atau terbalik? Tambahkan dulu, lalu atur rotasinya di Atur.
                                    {tes.hasil.tinggi > tes.hasil.lebar ? ' Gambar tegak cocok untuk kamera HP yang dipasang berdiri.' : ''}
                                </p>
                            </div>
                        </>
                    ) : (
                        <div className="space-y-2">
                            <p className="font-semibold text-red-700 dark:text-red-400">Belum terhubung: {tes.hasil.pesan}</p>
                            <p className="text-xs font-semibold text-slate-600 dark:text-slate-400">Periksa:</p>
                            <ol className="list-decimal pl-5 space-y-1 text-slate-700 dark:text-slate-300">
                                {daftarPeriksa(tes.alamat).map((l) => <li key={l}>{l}</li>)}
                            </ol>
                        </div>
                    )}
                    <button type="button" onClick={() => setTes(null)} aria-label="Tutup hasil tes" className="self-start sm:ml-auto p-0.5 rounded hover:bg-black/5">
                        <X className="w-4 h-4" />
                    </button>
                </div>
            )}

            {/* Pesan kesalahan / info dari backend */}
            {pesan && (
                <div role={pesan.tipe === 'info' ? 'status' : 'alert'} className={`mb-6 p-4 rounded-xl border text-sm flex items-start gap-2 ${pesan.tipe === 'info'
                    ? 'bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300'
                    : 'bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400'}`}>
                    <Info className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                    <span className="flex-1">
                        {pesan.teks}
                        {pesan.langkah && (
                            <ol className="list-decimal pl-5 mt-2 space-y-1">
                                {pesan.langkah.map((l) => <li key={l}>{l}</li>)}
                            </ol>
                        )}
                    </span>
                    {pesan.tipe !== 'koneksi' && (
                        <button type="button" onClick={() => setPesan(null)} aria-label="Tutup pesan" className="p-0.5 rounded hover:bg-black/5">
                            <X className="w-4 h-4" />
                        </button>
                    )}
                </div>
            )}

            {/* Kamera yang ditemukan: terpasang di komputer ini, dan di jaringan */}
            {kandidat && (kandidat.lokal.length > 0 || kandidat.jaringan.candidates.length > 0) && (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 mb-6 overflow-hidden shadow-sm">
                    {kandidat.lokal.length > 0 && (
                        <>
                            <div className="p-4 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center gap-2">
                                <Usb className="w-4 h-4" aria-hidden="true" />
                                Terpasang di komputer ini
                                <span className="font-normal text-slate-500">(webcam, Iriun)</span>
                            </div>
                            <div className="divide-y divide-slate-200 dark:divide-slate-800">
                                {kandidat.lokal.map((d) => (
                                    <button key={d.source} type="button" disabled={d.in_use} onClick={() => pilihKandidat(d.source)}
                                        className="w-full p-4 flex items-center justify-between gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 disabled:opacity-50 disabled:hover:bg-transparent transition-colors text-left">
                                        <span>
                                            <span className="block font-medium text-sm">
                                                {d.label}
                                                {d.driver && <span className="text-slate-500 font-normal"> · {d.driver}</span>}
                                            </span>
                                            <span className="block text-xs text-slate-500 font-mono">sumber: {d.source} — {d.name}</span>
                                        </span>
                                        <span className="text-xs font-semibold underline underline-offset-2 whitespace-nowrap">
                                            {d.in_use ? 'Sudah dipakai' : 'Pakai kamera ini'}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </>
                    )}

                    {kandidat.jaringan.candidates.length > 0 && (
                        <>
                            <div className="p-4 border-y border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center gap-2">
                                <Radar className="w-4 h-4" aria-hidden="true" />
                                Ditemukan di jaringan
                                <span className="font-normal text-slate-500">
                                    ({kandidat.jaringan.subnets.join(', ')} · {kandidat.jaringan.duration_sec}s)
                                </span>
                            </div>
                            <div className="divide-y divide-slate-200 dark:divide-slate-800">
                                {kandidat.jaringan.candidates.map((k) => (
                                    <button key={`${k.ip}:${k.port}`} type="button" onClick={() => pilihKandidat(k.source)}
                                        className="w-full p-4 flex items-center justify-between gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors text-left">
                                        <span>
                                            <span className="block font-medium text-sm">{k.label}</span>
                                            <span className="block text-xs text-slate-500 font-mono">{k.source}</span>
                                        </span>
                                        <span className="text-xs font-semibold underline underline-offset-2 whitespace-nowrap">Pakai alamat ini</span>
                                    </button>
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}

            {/* Daftar kamera: kartu di semua lebar layar, supaya status, rotasi, dan hapus
                tetap terlihat di HP tanpa menggeser tabel. */}
            {cameras.length === 0 ? (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-8 text-center text-sm text-slate-500">
                    Belum ada kamera terdaftar. Tambahkan lewat formulir di atas, atau tekan Cari kamera.
                </div>
            ) : (
                <ul className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    {cameras.map((cam) => (
                        <li key={cam.camera_id} className={`bg-white dark:bg-slate-900 rounded-2xl border p-4 shadow-sm ${cam.is_active || !cam.enabled
                            ? 'border-slate-200 dark:border-slate-800'
                            : 'border-dashed border-slate-400 dark:border-slate-600'}`}>
                            <div className="flex gap-4">
                                <div className="w-32 sm:w-40 shrink-0">
                                    <GambarMini cam={cam} t={t} />
                                </div>
                                <div className="min-w-0 flex-1 space-y-1.5">
                                    <div className="flex items-start justify-between gap-2">
                                        <h2 className="font-semibold truncate">{cam.name}</h2>
                                        <span className="text-xs text-slate-500 font-mono shrink-0">{cam.camera_id}</span>
                                    </div>
                                    <StatusKameraDaftar cam={cam} />
                                    <p className="text-xs text-slate-500 font-mono break-all">{cam.source}</p>
                                    <p className="text-xs text-slate-500 tabular-nums">Rotasi {cam.rotate}&deg; · Video {labelPrivasi(cam.privasi).toLowerCase()}</p>
                                </div>
                            </div>
                            {atur === cam.camera_id ? (
                                <PanelKamera
                                    key={cam.camera_id}
                                    cam={cam}
                                    t={t}
                                    onUbah={ubahKamera}
                                    onHapus={hapusKamera}
                                    onTutup={() => setAtur(null)}
                                />
                            ) : (
                                <div className="mt-3 flex gap-2">
                                    <Link to={`/dashboard/camera-test?kamera=${cam.camera_id}`} className={TOMBOL_NETRAL}>
                                        <ScanEye className="w-4 h-4" aria-hidden="true" /> Uji
                                    </Link>
                                    <button type="button" onClick={() => setAtur(cam.camera_id)} className={TOMBOL_NETRAL}>
                                        <Settings2 className="w-4 h-4" aria-hidden="true" /> Atur
                                    </button>
                                    <button type="button" onClick={() => hapusKamera(cam.camera_id, cam.name)}
                                        aria-label={`Hapus ${cam.name}`} title={`Hapus ${cam.name}`}
                                        className={`${TOMBOL_NETRAL} px-3 hover:text-red-700 dark:hover:text-red-400`}>
                                        <Trash2 className="w-4 h-4" aria-hidden="true" />
                                    </button>
                                </div>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
