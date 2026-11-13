import { useCallback, useEffect, useState } from 'react';
import { Bell, BellOff, Volume2, VolumeX } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { useToast } from '../context/toast';
import { msDari, tanggalJam } from '../waktu';
import { aktifkanSuara, bunyikan, useStatusSuara } from '../hooks/useAlarmSound';
import { kabariAlarm, mintaIzinNotifikasi, useStatusNotifikasi } from '../hooks/useNotifikasi';
import { Penjelasan } from '../components/MenuKecil';

const KARTU = 'bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm';
const TOMBOL_NETRAL = 'shrink-0 min-h-10 px-3 rounded-lg text-sm font-semibold border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50';
const PILIH = 'w-full min-h-10 bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50';
const LABEL = 'text-sm font-medium text-slate-700 dark:text-slate-300';

/**
 * Satu kartu pengaturan: judul, satu baris keterangan, dan penjelasan lengkap di ikon ⓘ,
 * supaya kartunya pendek dan halaman muat satu layar.
 */
function Bagian({ id, judul, keterangan, penjelasan, aksi, className = '', children }) {
    return (
        <section aria-labelledby={id} className={`${KARTU} flex flex-col gap-3 ${className}`}>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-1">
                        <h2 id={id} className="font-semibold">{judul}</h2>
                        {penjelasan && <Penjelasan judul={judul}>{penjelasan}</Penjelasan>}
                    </div>
                    {keterangan && <p className="text-xs text-slate-500">{keterangan}</p>}
                </div>
                {aksi}
            </div>
            {children}
        </section>
    );
}

const TEKS_NOTIFIKASI = {
    granted: 'Notifikasi diizinkan di perangkat ini',
    default: 'Notifikasi belum diizinkan',
    denied: 'Notifikasi diblokir. Izinkan lewat pengaturan situs di browser',
    'perlu-https': 'Notifikasi hanya bisa lewat alamat HTTPS atau localhost',
    'tidak-didukung': 'Browser ini tidak mendukung notifikasi',
};

const masaSimpan = (hari, nol) => (hari > 0 ? `${hari} hari, lalu dihapus otomatis` : nol);

/**
 * Siapa mengubah apa dan kapan. Angka alarm di Riwayat Insiden hanya bisa ditafsirkan bila
 * diketahui ambang dan model yang berlaku saat itu.
 */
function RiwayatPerubahan({ riwayat, daftarMode, opsiFoto }) {
    if (riwayat === 'galat') return <p className="text-sm text-red-700 dark:text-red-400">{PESAN_TERPUTUS}</p>;
    if (!riwayat) return <p className="text-sm text-slate-500">Memuat…</p>;
    if (!riwayat.length) return <p className="text-sm text-slate-500">Belum ada perubahan yang tercatat.</p>;
    const nilai = (r, v) => {
        if (v == null || v === '') return '–';
        if (r.kunci === 'detection_mode') return daftarMode.find((m) => m.id === v)?.label || v;
        if (r.kunci === 'telegram_photo_mode') return opsiFoto.find((o) => o.id === v)?.label || v;
        return v;
    };
    return (
        <ol className="divide-y divide-slate-200 dark:divide-slate-800">
            {riwayat.map((r, i) => (
                <li key={`${r.waktu}-${r.kunci}-${i}`} className="py-2 first:pt-0 last:pb-0">
                    <p className="text-sm">
                        <span className="font-medium">{r.label}</span>: {nilai(r, r.nilai_lama)} → {nilai(r, r.nilai_baru)}
                    </p>
                    <p className="text-xs text-slate-500">
                        {r.oleh} · <time dateTime={r.waktu}>{tanggalJam(msDari(r.waktu))}</time>
                    </p>
                </li>
            ))}
        </ol>
    );
}

/**
 * Pratinjau ambang dari episode berbaring 30 hari terakhir: alarm yang hilang bila ambang
 * dinaikkan (beserta putusannya, termasuk jatuh sungguhan), dan alarm tambahan yang belum
 * pernah dinilai bila diturunkan. Latihan tidak dihitung.
 *
 * Kotaknya selalu ada. Selama angka baru dihitung, hasil sebelumnya tetap tampil dengan
 * warna pudar, supaya isi kartu tidak melompat setiap kali slider digeser.
 */
function PratinjauAmbang({ ambang, ambangKini }) {
    const [hasil, setHasil] = useState(null);
    useEffect(() => {
        let batal = false;
        // Ditunda sebentar supaya menggeser slider tidak mengirim satu permintaan per langkah.
        const t = setTimeout(async () => {
            try {
                const r = await api(`/api/settings/pratinjau-ambang?ambang=${ambang}`);
                if (r.ok && !batal) setHasil(await r.json());
            } catch { /* pratinjau tidak wajib */ }
        }, 400);
        return () => {
            batal = true;
            clearTimeout(t);
        };
    }, [ambang]);

    const kotak = 'rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-xs space-y-0.5 min-h-[3.75rem] transition-opacity';
    if (!hasil) {
        return <div role="status" className={`${kotak} text-slate-500`}>Menghitung pratinjau dari episode berbaring…</div>;
    }
    const pudar = Number(hasil.ambang) !== Number(ambang) ? 'opacity-50' : '';
    if (!hasil.episode) {
        return (
            <div role="status" className={`${kotak} ${pudar} text-slate-500`}>
                Pratinjau: belum ada episode berbaring dalam 30 hari terakhir. Angkanya terisi setelah sistem
                berjalan beberapa hari.
            </div>
        );
    }
    const a = Number(hasil.ambang);
    const naik = a > Number(ambangKini);
    const turun = a < Number(ambangKini);
    const jatuh = hasil.hilang.jatuh || 0;
    const palsu = hasil.hilang.palsu || 0;
    const hilang = Object.values(hasil.hilang).reduce((x, y) => x + y, 0);
    let teks = `Pada ${a} detik, ${hasil.berbunyi} dari ${hasil.episode} episode berbaring memicu alarm.`;
    if (naik) {
        const rincian = [[palsu, 'alarm palsu'], [jatuh, 'jatuh sungguhan'], [hilang - palsu - jatuh, 'belum dinilai atau belum yakin']]
            .filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`);
        teks = hilang ? `${hilang} alarm tidak akan berbunyi: ${rincian.join(', ')}.` : 'Tidak ada alarm yang hilang.';
        if (hasil.belum_tentu) teks += ` ${hasil.belum_tentu} alarm lain belum tentu, karena ditutup sebelum ${a} detik.`;
    } else if (turun) {
        teks = hasil.tambahan
            ? `Ada ${hasil.tambahan} alarm tambahan dari orang yang dulu bangun sebelum ${ambangKini} detik. Belum ada yang menilai apakah itu jatuh.`
            : 'Tidak ada alarm tambahan.';
    }
    return (
        <div role="status" className={`${kotak} ${pudar}`}>
            <p className="font-semibold text-slate-700 dark:text-slate-300">
                Pratinjau dari {hasil.episode} episode berbaring, 30 hari terakhir
            </p>
            <p className="text-slate-600 dark:text-slate-400">{teks}</p>
            {naik && jatuh > 0 && (
                <p className="font-semibold text-amber-700 dark:text-amber-400">
                    Termasuk {jatuh} jatuh sungguhan yang tidak akan dikabarkan.
                </p>
            )}
        </div>
    );
}

export default function Settings() {
    const kabari = useToast();
    const [threshold, setThreshold] = useState(10);
    const [mode, setMode] = useState('');
    const [daftarMode, setDaftarMode] = useState([]);
    const [telegramSiap, setTelegramSiap] = useState(false);
    const [tg, setTg] = useState(null);                  // { photo_mode, send_drills, camera_offline }
    const [opsiFoto, setOpsiFoto] = useState([]);

    // Nilai yang sedang berlaku di backend. Dipakai untuk tahu apa yang benar-benar
    // berubah, supaya tombol Simpan tidak mengirim PUT mode yang tidak perlu --
    // pergantian mode mereset timer semua kamera, jadi jangan dilakukan sia-sia.
    const [tersimpan, setTersimpan] = useState({ threshold: 10, mode: '' });

    const [memuat, setMemuat] = useState(true);
    const [sibuk, setSibuk] = useState(false);
    const [eskalasi, setEskalasi] = useState(2);
    const [polaShift, setPolaShift] = useState('3');
    const [simpan, setSimpan] = useState(null);          // { foto, klip } dalam hari
    const [riwayat, setRiwayat] = useState(null);        // null = memuat, 'galat', atau daftar
    const suara = useStatusSuara();
    const notifikasi = useStatusNotifikasi();

    const terapkan = (d) => {
        setThreshold(d.fall_duration_threshold);
        setMode(d.detection_mode);
        setDaftarMode(d.available_modes || []);
        setTelegramSiap(d.telegram_configured);
        setTg(d.telegram);
        setOpsiFoto(d.photo_modes || []);
        setEskalasi(d.eskalasi_menit ?? 2);
        setPolaShift(d.pola_shift || '3');
        setTersimpan({ threshold: d.fall_duration_threshold, mode: d.detection_mode });
        setSimpan({ foto: d.foto_masa_simpan_hari, klip: d.klip_masa_simpan_hari });
    };

    const ambil = useCallback(async () => {
        try {
            const r = await api('/api/settings/');
            if (!r.ok) throw new Error(String(r.status));
            terapkan(await r.json());
        } catch {
            kabari(PESAN_TERPUTUS, 'galat');
        } finally {
            setMemuat(false);
        }
    }, [kabari]);

    const ambilRiwayat = useCallback(async () => {
        try {
            const r = await api('/api/settings/riwayat');
            if (!r.ok) throw new Error(String(r.status));
            setRiwayat(await r.json());
        } catch {
            setRiwayat('galat');
        }
    }, []);

    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
        ambilRiwayat();
    }, [ambil, ambilRiwayat]);

    const berubah = Number(threshold) !== Number(tersimpan.threshold) || mode !== tersimpan.mode;

    const simpanDeteksi = async (e) => {
        e.preventDefault();
        setSibuk(true);
        try {
            const dilakukan = [];

            if (Number(threshold) !== Number(tersimpan.threshold)) {
                const r = await api('/api/settings/threshold', {
                    method: 'PUT', json: { fall_duration_threshold: Number(threshold) },
                });
                if (!r.ok) throw new Error(await bacaGalat(r));
                dilakukan.push(`menunggu ${threshold} detik sebelum alarm`);
            }

            if (mode !== tersimpan.mode) {
                const r = await api('/api/settings/mode', { method: 'PUT', json: { detection_mode: mode } });
                if (!r.ok) throw new Error(await bacaGalat(r));
                const nama = daftarMode.find((m) => m.id === mode)?.label || mode;
                dilakukan.push(`model jadi ${nama}, hitungan semua kamera direset`);
            }

            await ambil();
            ambilRiwayat();
            if (dilakukan.length) kabari(`Tersimpan: ${dilakukan.join('; ')}.`);
        } catch (err) {
            kabari(`Gagal menyimpan: ${err.message}`, 'galat');
        } finally {
            setSibuk(false);
        }
    };

    /** Pengaturan Telegram tersimpan seketika setiap diubah. */
    const ubahTelegram = async (isi, pesan) => {
        setTg((t) => ({ ...t, ...isi }));
        try {
            const r = await api('/api/settings/telegram', { method: 'PUT', json: isi });
            if (!r.ok) throw new Error(await bacaGalat(r));
            terapkan(await r.json());
            ambilRiwayat();
            kabari(pesan);
        } catch (err) {
            kabari(`Gagal menyimpan: ${err.message}`, 'galat');
            ambil();
        }
    };

    const ujiTelegram = async () => {
        setSibuk(true);
        try {
            const r = await api('/api/settings/test-telegram', { method: 'POST' });
            const d = await r.json();
            kabari(d.pesan, d.terkirim ? 'ok' : 'galat');
            setTelegramSiap(d.dikonfigurasi);
        } catch {
            kabari(PESAN_TERPUTUS, 'galat');
        } finally {
            setSibuk(false);
        }
    };

    /** Tersimpan seketika setiap diubah, seperti pengaturan Telegram. */
    const ubahEskalasi = async (menit) => {
        setEskalasi(menit);
        try {
            const r = await api('/api/settings/eskalasi', { method: 'PUT', json: { eskalasi_menit: menit } });
            if (!r.ok) throw new Error(await bacaGalat(r));
            terapkan(await r.json());
            ambilRiwayat();
            kabari(`Tersimpan: pengingat setelah ${menit} menit.`);
        } catch (err) {
            kabari(`Gagal menyimpan: ${err.message}`, 'galat');
            ambil();
        }
    };

    const ubahPolaShift = async (pola) => {
        setPolaShift(pola);
        try {
            const r = await api('/api/settings/shift', { method: 'PUT', json: { pola_shift: pola } });
            if (!r.ok) throw new Error(await bacaGalat(r));
            terapkan(await r.json());
            ambilRiwayat();
            kabari(`Tersimpan: ${pola} shift.`);
        } catch (err) {
            kabari(`Gagal menyimpan: ${err.message}`, 'galat');
            ambil();
        }
    };

    const tesSuara = async () => {
        if (await aktifkanSuara()) bunyikan();
    };

    // Chrome Android dan Safari iOS menolak notifikasi dari halaman web biasa walau izinnya ada.
    const tesNotifikasi = () => (kabariAlarm({ id: 'uji', camera_name: 'Uji notifikasi', simulated: true })
        ? kabari('Notifikasi uji dikirim. Bila tidak muncul, periksa pengaturan notifikasi sistem operasi.')
        : kabari('Browser ini tidak menampilkan notifikasi dari halaman web, biasanya di HP. Di HP, andalkan pesan Telegram.', 'galat'));

    const modeBerlaku = daftarMode.find((m) => m.id === tersimpan.mode);

    return (
        /* Mulai 1280 px halaman ini setinggi layar dikurangi banner alarm dan tidak menggulir:
           tiga kolom, dan Riwayat perubahan menggulir di dalam kartunya. Di bawah 1280 px
           ketiga kolom terlalu sempit, jadi kartu disusun menurun dengan gulir halaman biasa;
           kolomnya memakai display: contents supaya urutan kartu bisa diatur. */
        <div className="p-4 md:p-6 xl:px-8 xl:pt-6 xl:pb-5 w-full max-w-full min-w-0 xl:h-[calc(100dvh-var(--tinggi-banner,0px))] xl:flex xl:flex-col xl:overflow-hidden">
            <div className="mb-4 xl:mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <h1 className="text-xl md:text-2xl font-bold">Pengaturan</h1>
                <p className="text-xs md:text-sm text-slate-500">
                    Berlaku untuk seluruh panti, kecuali suara dan notifikasi yang diatur per perangkat.
                </p>
            </div>

            <div className="grid gap-4 max-w-2xl xl:max-w-none xl:grid-cols-3 xl:grid-rows-[minmax(0,1fr)] xl:flex-1 xl:min-h-0">
                {/* Kolom 1: deteksi. */}
                <div className="contents xl:flex xl:flex-col xl:gap-4 xl:min-h-0 xl:overflow-y-auto">
                    <Bagian id="atur-deteksi" judul="Deteksi" keterangan="Berlaku untuk semua kamera." className="xl:flex-1"
                        penjelasan={<>
                            <p>Model menentukan cara sistem membaca postur. Mengganti model mereset hitungan durasi berbaring di semua kamera.</p>
                            <p>Waktu tunggu yang lebih pendek berarti lebih banyak alarm palsu. Yang lebih panjang berarti pertolongan bisa terlambat.</p>
                            {daftarMode.some((m) => m.teknis) && (
                                <dl className="space-y-1 text-xs text-slate-500">
                                    {daftarMode.map((m) => (
                                        <div key={m.id}><dt className="inline font-medium">{m.label}: </dt><dd className="inline">{m.teknis}</dd></div>
                                    ))}
                                </dl>
                            )}
                        </>}>
                        <form onSubmit={simpanDeteksi} className="flex flex-col gap-4 xl:flex-1">
                            {/* Dua kartu berisi akibatnya, bukan dropdown nama teknis: yang dipilih
                                perawat adalah perilaku alarmnya, bukan arsitektur modelnya. */}
                            <fieldset>
                                <legend className={`${LABEL} mb-2`}>Model deteksi</legend>
                                {daftarMode.length === 0 && <p className="text-sm text-slate-500">Memuat…</p>}
                                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 gap-2">
                                    {daftarMode.map((m) => (
                                        <label
                                            key={m.id}
                                            className={`flex flex-col gap-1 rounded-xl border px-3 py-2.5 cursor-pointer transition-colors ${mode === m.id
                                                ? 'border-slate-900 ring-1 ring-slate-900 dark:border-slate-100 dark:ring-slate-100'
                                                : 'border-slate-300 dark:border-slate-700 hover:border-slate-500'} ${memuat ? 'opacity-50' : ''}`}
                                        >
                                            <span className="flex items-center gap-2">
                                                <input type="radio" name="model-deteksi" value={m.id} checked={mode === m.id}
                                                    onChange={() => setMode(m.id)} disabled={memuat}
                                                    className="accent-slate-700 dark:accent-slate-300" />
                                                <span className="font-semibold text-sm text-slate-900 dark:text-slate-100">{m.label}</span>
                                                {m.recommended && <span className="text-xs text-slate-500">· disarankan</span>}
                                            </span>
                                            <span className="text-xs text-slate-600 dark:text-slate-400 leading-snug">{m.description}</span>
                                        </label>
                                    ))}
                                </div>
                                {/* Selalu tampil, supaya memilih model lain tidak menyisipkan baris baru. */}
                                <p className={`text-xs mt-1.5 ${mode !== tersimpan.mode ? 'font-semibold text-amber-700 dark:text-amber-400' : 'text-slate-500'}`}>
                                    Mengganti model mereset hitungan di semua kamera.
                                </p>
                            </fieldset>

                            <div className="space-y-1.5">
                                <div className="flex items-baseline justify-between gap-3">
                                    <label htmlFor="ambang" className={LABEL}>Tunggu sebelum memberi alarm</label>
                                    <span className="text-lg font-bold text-slate-800 dark:text-slate-200 tabular-nums whitespace-nowrap">{threshold} detik</span>
                                </div>
                                <input
                                    id="ambang"
                                    type="range"
                                    min="3" max="30"
                                    value={threshold}
                                    onChange={(e) => setThreshold(e.target.value)}
                                    disabled={memuat}
                                    aria-describedby="ambang-ket"
                                    className="w-full accent-slate-700 dark:accent-slate-300"
                                />
                                <p id="ambang-ket" className="text-xs text-slate-500">
                                    Alarm berbunyi setelah {threshold} detik terbaca berbaring.
                                </p>
                                <PratinjauAmbang ambang={threshold} ambangKini={tersimpan.threshold} />
                            </div>

                            {/* Di dasar kartu. Bila kolomnya harus menggulir (layar pendek), tombol
                                menempel di dasar kolom dengan latar kartu di belakangnya. */}
                            <div className="mt-auto xl:sticky xl:bottom-0 xl:pt-2 bg-white dark:bg-slate-900">
                                <button
                                    type="submit"
                                    disabled={sibuk || memuat || !berubah}
                                    className="w-full min-h-11 bg-emerald-700 hover:bg-emerald-800 disabled:bg-slate-200 disabled:text-slate-500 dark:disabled:bg-slate-800 dark:disabled:text-slate-400 text-white font-semibold rounded-lg transition-colors"
                                >
                                    {sibuk ? 'Menyimpan…' : berubah ? 'Simpan pengaturan deteksi' : 'Pengaturan deteksi tersimpan'}
                                </button>
                            </div>
                        </form>
                    </Bagian>
                </div>

                {/* Kolom 2: perangkat ini, pengingat, dan riwayat perubahan yang mengisi sisa tinggi. */}
                <div className="contents xl:flex xl:flex-col xl:gap-4 xl:min-h-0">
                    <Bagian id="atur-suara" judul="Suara dan notifikasi" keterangan="Diatur per perangkat ini."
                        penjelasan={<>
                            <p>Browser yang memutuskan boleh tidaknya halaman berbunyi dan memberi notifikasi, jadi pengaturan ini berlaku per perangkat.</p>
                            <p>Alarm berbunyi berulang sampai ada yang menekan Saya ke sana. Browser menahan suara sampai ada klik pertama di halaman, jadi klik sekali setiap kali dashboard dibuka.</p>
                            <p>Notifikasi muncul saat ada alarm dan tab FallDetect sedang tidak dilihat, berisi nama ruang tanpa foto. Alarm sungguhan tetap tampil sampai ada yang menuju lokasi. Untuk komputer jaga; di HP, perawat dikabari lewat Telegram.</p>
                        </>}>
                        <div className="flex items-center gap-3">
                            <span className="flex-1 min-w-0 inline-flex items-center gap-2 text-sm">
                                {suara === 'aktif'
                                    ? <><Volume2 className="w-4 h-4 shrink-0" aria-hidden="true" /> Suara aktif di perangkat ini</>
                                    : suara === 'tidak-didukung'
                                        ? <><VolumeX className="w-4 h-4 shrink-0" aria-hidden="true" /> Browser ini tidak bisa membunyikan alarm</>
                                        : <><VolumeX className="w-4 h-4 shrink-0" aria-hidden="true" /> Suara belum aktif</>}
                            </span>
                            <button type="button" onClick={tesSuara} className={TOMBOL_NETRAL}>Tes suara</button>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="flex-1 min-w-0 inline-flex items-center gap-2 text-sm">
                                {notifikasi === 'granted'
                                    ? <Bell className="w-4 h-4 shrink-0" aria-hidden="true" />
                                    : <BellOff className="w-4 h-4 shrink-0" aria-hidden="true" />}
                                {TEKS_NOTIFIKASI[notifikasi]}
                            </span>
                            {notifikasi === 'default' && (
                                <button type="button" onClick={mintaIzinNotifikasi} className={TOMBOL_NETRAL}>Izinkan notifikasi</button>
                            )}
                            {notifikasi === 'granted' && (
                                <button type="button" onClick={tesNotifikasi} className={TOMBOL_NETRAL}>Tes notifikasi</button>
                            )}
                        </div>
                    </Bagian>

                    <Bagian id="atur-eskalasi" judul="Bila tidak ada yang merespons" keterangan="Pengingat bila belum ada yang menekan Saya ke sana."
                        penjelasan={<>
                            <p>Alarm yang dibiarkan tidak boleh mati diam-diam. Setelah {eskalasi} menit, banner menulis Belum ada yang merespons beserta lamanya, dan grup Telegram menerima pengingat sebagai balasan ke pesan alarm, setiap {eskalasi} menit, paling banyak 3 kali.</p>
                            <p>Belum ada angka yang teruji untuk panti, jadi sesuaikan dengan pengalaman perawat.</p>
                            <p>Jam shift membagi Ringkasan shift di Riwayat Insiden untuk serah terima: 3 shift mulai pukul 07.00, 14.00, dan 21.00; 2 shift mulai pukul 07.00 dan 19.00.</p>
                        </>}>
                        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2">
                            <label htmlFor="eskalasi" className={LABEL}>Ingatkan setelah</label>
                            <select id="eskalasi" value={eskalasi} onChange={(e) => ubahEskalasi(Number(e.target.value))}
                                disabled={memuat} className={PILIH}>
                                {[1, 2, 3, 5, 10].map((m) => <option key={m} value={m}>{m} menit</option>)}
                            </select>
                            <label htmlFor="pola-shift" className={LABEL}>Jam shift</label>
                            <select id="pola-shift" value={polaShift} onChange={(e) => ubahPolaShift(e.target.value)}
                                disabled={memuat} className={PILIH}>
                                <option value="3">3 shift: 7, 14, 21</option>
                                <option value="2">2 shift: 7, 19</option>
                            </select>
                        </div>
                    </Bagian>

                    <Bagian id="atur-riwayat" judul="Riwayat perubahan" keterangan="Terbaru di atas, beserta siapa yang mengubah."
                        className="max-xl:order-1 xl:flex-1 xl:min-h-0">
                        <div className="xl:flex-1 xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain">
                            <RiwayatPerubahan riwayat={riwayat} daftarMode={daftarMode} opsiFoto={opsiFoto} />
                        </div>
                    </Bagian>
                </div>

                {/* Kolom 3: Telegram, privasi, dan keterangan sistem. */}
                <div className="contents xl:flex xl:flex-col xl:gap-4 xl:min-h-0 xl:overflow-y-auto">
                    <Bagian id="atur-telegram" judul="Telegram"
                        keterangan={(
                            <span className="inline-flex items-center gap-1.5">
                                <span className={`w-2 h-2 shrink-0 rounded-full ${telegramSiap ? 'bg-emerald-500' : 'bg-slate-400 dark:bg-slate-600'}`} aria-hidden="true" />
                                {telegramSiap ? 'Terhubung ke grup perawat' : 'Belum diatur'}
                            </span>
                        )}
                        aksi={(
                            <button type="button" onClick={ujiTelegram} disabled={sibuk} className={TOMBOL_NETRAL}>
                                Kirim pesan uji
                            </button>
                        )}
                        penjelasan={<>
                            <p>Pesan alarm dikirim ke grup perawat, dengan tombol Saya ke sana dan Alarm palsu. Membalas pesan alarm di grup menambah catatan insiden.</p>
                            <p>Token bot dan ID grup diatur di server oleh pengelola sistem, bukan dari halaman ini, karena keduanya rahasia.</p>
                            <p>Latihan tidak dikirim secara bawaan, supaya grup tidak terbiasa mengabaikan pesan alarm.</p>
                            <p>Kabar kamera dikirim setelah 30 detik tanpa gambar dan saat kamera pulih, juga saat Mode perawatan dimulai, diperpanjang, atau selesai.</p>
                        </>}>
                        {tg && (
                            <div className="space-y-0.5">
                                <label className="flex items-center gap-3 text-sm cursor-pointer min-h-7">
                                    <input type="checkbox" checked={tg.send_drills} className="accent-blue-600"
                                        onChange={(e) => ubahTelegram({ send_drills: e.target.checked },
                                            e.target.checked ? 'Tersimpan: latihan ikut dikirim ke Telegram.' : 'Tersimpan: latihan tidak dikirim ke Telegram.')} />
                                    Kirim juga latihan ke Telegram
                                </label>
                                <label className="flex items-center gap-3 text-sm cursor-pointer min-h-7">
                                    <input type="checkbox" checked={tg.camera_offline} className="accent-slate-700"
                                        onChange={(e) => ubahTelegram({ camera_offline: e.target.checked },
                                            e.target.checked ? 'Tersimpan: grup dikabari saat kamera terputus.' : 'Tersimpan: grup tidak dikabari soal kamera.')} />
                                    Kabari grup saat kamera terputus atau dijeda
                                </label>
                            </div>
                        )}
                    </Bagian>

                    <Bagian id="atur-privasi" judul="Privasi" keterangan="Foto penghuni yang tergeletak adalah data kesehatan."
                        penjelasan={<>
                            <p>Semua pesan dilindungi supaya tidak bisa diteruskan atau disimpan dari Telegram. Foto dan klip di server hanya bisa dilihat setelah masuk, di Riwayat Insiden.</p>
                            <p>Masa simpan diubah lewat <code>FOTO_MASA_SIMPAN_HARI</code> dan <code>KLIP_MASA_SIMPAN_HARI</code> di berkas <code>backend/.env</code>. Angka 0 berarti tidak disimpan sama sekali.</p>
                        </>}>
                        {tg && (
                            <fieldset>
                                <legend className={`${LABEL} mb-1`}>Foto di pesan Telegram</legend>
                                {opsiFoto.map((o) => (
                                    <label key={o.id} className="flex items-center gap-3 text-sm cursor-pointer min-h-7">
                                        <input type="radio" name="foto-telegram" value={o.id} checked={tg.photo_mode === o.id}
                                            onChange={() => ubahTelegram({ photo_mode: o.id }, `Tersimpan: ${o.label.toLowerCase()}.`)}
                                            className="accent-slate-700" />
                                        {o.label}
                                    </label>
                                ))}
                            </fieldset>
                        )}
                        {simpan && (
                            <div>
                                <h3 className={`${LABEL} mb-1`}>Masa simpan di server</h3>
                                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-sm">
                                    <dt className="text-slate-500">Foto kejadian</dt>
                                    <dd>{masaSimpan(simpan.foto, 'tidak disimpan')}</dd>
                                    <dt className="text-slate-500">Klip kejadian</dt>
                                    <dd>{masaSimpan(simpan.klip, 'tidak direkam')}</dd>
                                    <dt className="text-slate-500">Catatan insiden</dt>
                                    <dd>tanpa batas waktu, untuk laporan</dd>
                                </dl>
                            </div>
                        )}
                    </Bagian>

                    <Bagian id="atur-tentang" judul="Tentang sistem" keterangan="Bukan alat kesehatan bersertifikat."
                        className="max-xl:order-2 xl:flex-1"
                        penjelasan={<p>FallDetect adalah prototipe proyek mahasiswa. Alarm adalah pemberitahuan kemungkinan jatuh dan tetap perlu diperiksa langsung oleh perawat.</p>}>
                        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-0.5 text-sm">
                            <dt className="text-slate-500">Model aktif</dt>
                            <dd>{modeBerlaku?.label || '…'}</dd>
                            <dt className="text-slate-500">Backend</dt>
                            <dd className="font-mono text-xs break-all self-center">{API_BASE}</dd>
                        </dl>
                    </Bagian>
                </div>
            </div>
        </div>
    );
}
