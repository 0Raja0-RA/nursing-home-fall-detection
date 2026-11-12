import { useCallback, useEffect, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { aktifkanSuara, bunyikan, useStatusSuara } from '../hooks/useAlarmSound';

const KARTU = 'bg-white dark:bg-slate-900 p-4 md:p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4';
const TOMBOL_NETRAL = 'min-h-10 px-3 rounded-lg text-sm font-semibold border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50';

function Bagian({ id, judul, keterangan, children }) {
    return (
        <section aria-labelledby={id} className={KARTU}>
            <div>
                <h2 id={id} className="font-semibold">{judul}</h2>
                {keterangan && <p className="text-xs text-slate-500 mt-0.5">{keterangan}</p>}
            </div>
            {children}
        </section>
    );
}

function Kabar({ kabar }) {
    if (!kabar) return null;
    return (
        <div role="status" className={`text-sm rounded-lg px-3 py-2 border ${kabar.tipe === 'ok'
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-400'
            : 'bg-red-500/10 border-red-500/20 text-red-700 dark:text-red-400'}`}>
            {kabar.teks}
        </div>
    );
}

export default function Settings() {
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
    const [kabar, setKabar] = useState(null);           // deteksi: { tipe: 'ok' | 'galat', teks }
    const [kabarTg, setKabarTg] = useState(null);       // { tipe, teks, bagian: 'telegram' | 'privasi' }
    const suara = useStatusSuara();

    const terapkan = (d) => {
        setThreshold(d.fall_duration_threshold);
        setMode(d.detection_mode);
        setDaftarMode(d.available_modes || []);
        setTelegramSiap(d.telegram_configured);
        setTg(d.telegram);
        setOpsiFoto(d.photo_modes || []);
        setTersimpan({ threshold: d.fall_duration_threshold, mode: d.detection_mode });
    };

    const ambil = useCallback(async () => {
        try {
            const r = await api('/api/settings/');
            if (!r.ok) throw new Error(String(r.status));
            terapkan(await r.json());
            setKabar(null);
        } catch {
            setKabar({ tipe: 'galat', teks: PESAN_TERPUTUS });
        } finally {
            setMemuat(false);
        }
    }, []);

    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
    }, [ambil]);

    const simpanDeteksi = async (e) => {
        e.preventDefault();
        setSibuk(true);
        setKabar(null);
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
            setKabar({
                tipe: 'ok',
                teks: dilakukan.length ? `Tersimpan: ${dilakukan.join('; ')}.` : 'Tidak ada yang berubah.',
            });
        } catch (err) {
            setKabar({ tipe: 'galat', teks: `Gagal menyimpan: ${err.message}` });
        } finally {
            setSibuk(false);
        }
    };

    /** Pengaturan Telegram tersimpan seketika setiap diubah; kabarnya tampil di kartu asalnya. */
    const ubahTelegram = async (isi, bagian = 'telegram') => {
        setKabarTg(null);
        setTg((t) => ({ ...t, ...isi }));
        try {
            const r = await api('/api/settings/telegram', { method: 'PUT', json: isi });
            if (!r.ok) throw new Error(await bacaGalat(r));
            terapkan(await r.json());
            setKabarTg({ tipe: 'ok', teks: 'Tersimpan.', bagian });
        } catch (err) {
            setKabarTg({ tipe: 'galat', teks: `Gagal menyimpan: ${err.message}`, bagian });
            ambil();
        }
    };

    const ujiTelegram = async () => {
        setSibuk(true);
        setKabarTg(null);
        try {
            const r = await api('/api/settings/test-telegram', { method: 'POST' });
            const d = await r.json();
            setKabarTg({ tipe: d.terkirim ? 'ok' : 'galat', teks: d.pesan, bagian: 'telegram' });
            setTelegramSiap(d.dikonfigurasi);
        } catch {
            setKabarTg({ tipe: 'galat', teks: PESAN_TERPUTUS, bagian: 'telegram' });
        } finally {
            setSibuk(false);
        }
    };

    const tesSuara = async () => {
        if (await aktifkanSuara()) bunyikan();
    };

    const modeTerpilih = daftarMode.find((m) => m.id === mode);

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0">
            <h1 className="text-xl md:text-2xl font-bold mb-6">Pengaturan</h1>

            <div className="max-w-2xl space-y-6">
                <Bagian id="atur-deteksi" judul="Deteksi" keterangan="Berlaku untuk semua kamera.">
                    <form onSubmit={simpanDeteksi} className="space-y-6">
                        <div>
                            <label htmlFor="pilih-model" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                Model deteksi
                            </label>
                            <select
                                id="pilih-model"
                                value={mode}
                                onChange={(e) => setMode(e.target.value)}
                                disabled={memuat || daftarMode.length === 0}
                                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg p-2.5 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                            >
                                {daftarMode.length === 0 && <option value="">Memuat…</option>}
                                {daftarMode.map((m) => (
                                    <option key={m.id} value={m.id}>
                                        {m.label}{m.recommended ? ' (disarankan)' : ''}
                                    </option>
                                ))}
                            </select>
                            <p className="text-xs text-slate-500 mt-1">
                                {modeTerpilih
                                    ? modeTerpilih.description
                                    : 'Model yang dipakai untuk membaca postur dari setiap frame.'}
                            </p>
                            {mode !== tersimpan.mode && (
                                <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
                                    Mengganti model akan mereset hitungan durasi di semua kamera.
                                </p>
                            )}
                        </div>

                        <div>
                            <label htmlFor="ambang" className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                Tunggu sebelum memberi alarm
                            </label>
                            <div className="flex items-center gap-4">
                                <input
                                    id="ambang"
                                    type="range"
                                    min="3" max="30"
                                    value={threshold}
                                    onChange={(e) => setThreshold(e.target.value)}
                                    disabled={memuat}
                                    className="w-full accent-slate-700 dark:accent-slate-300"
                                />
                                <span className="text-lg font-bold text-slate-800 dark:text-slate-200 w-24 text-right tabular-nums">{threshold} detik</span>
                            </div>
                            <p className="text-xs text-slate-500 mt-1">
                                Alarm berbunyi setelah seseorang terbaca berbaring selama {threshold} detik. Lebih pendek,
                                lebih banyak alarm palsu. Lebih panjang, pertolongan bisa terlambat.
                            </p>
                        </div>

                        <Kabar kabar={kabar} />

                        <button
                            type="submit"
                            disabled={sibuk || memuat}
                            className="w-full min-h-11 bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
                        >
                            {sibuk ? 'Menyimpan…' : 'Simpan pengaturan deteksi'}
                        </button>
                    </form>
                </Bagian>

                <Bagian id="atur-suara" judul="Suara" keterangan="Diatur per perangkat, karena browser yang memutuskan boleh tidaknya berbunyi.">
                    <div className="flex flex-wrap items-center gap-3">
                        <span className="inline-flex items-center gap-2 text-sm">
                            {suara === 'aktif'
                                ? <><Volume2 className="w-4 h-4" aria-hidden="true" /> Suara aktif di perangkat ini</>
                                : suara === 'tidak-didukung'
                                    ? <><VolumeX className="w-4 h-4" aria-hidden="true" /> Browser ini tidak bisa membunyikan alarm</>
                                    : <><VolumeX className="w-4 h-4" aria-hidden="true" /> Suara belum aktif</>}
                        </span>
                        <button type="button" onClick={tesSuara} className={`${TOMBOL_NETRAL} ml-auto`}>Tes suara</button>
                    </div>
                    <p className="text-xs text-slate-500">
                        Alarm berbunyi berulang sampai ada yang menekan Saya ke sana. Browser menahan suara sampai ada
                        klik pertama di halaman, jadi klik sekali setiap kali dashboard dibuka.
                    </p>
                </Bagian>

                <Bagian id="atur-telegram" judul="Telegram" keterangan="Pesan alarm ke grup perawat, dengan tombol Saya ke sana dan Alarm palsu.">
                    <div className="flex flex-wrap items-center gap-3">
                        <span className="inline-flex items-center gap-2 text-sm">
                            <span className={`w-2 h-2 rounded-full ${telegramSiap ? 'bg-emerald-500' : 'bg-slate-400 dark:bg-slate-600'}`} aria-hidden="true" />
                            {telegramSiap ? 'Terhubung ke grup' : 'Belum diatur'}
                        </span>
                        <button type="button" onClick={ujiTelegram} disabled={sibuk} className={`${TOMBOL_NETRAL} ml-auto`}>
                            Kirim pesan uji
                        </button>
                    </div>
                    <p className="text-xs text-slate-500">
                        Token bot dan ID grup diatur di server oleh pengelola sistem, bukan dari halaman ini, karena keduanya rahasia.
                    </p>
                    {tg && (
                        <div className="space-y-3">
                            <label className="flex items-start gap-3 text-sm cursor-pointer">
                                <input type="checkbox" checked={tg.send_drills} className="mt-1 accent-blue-600"
                                    onChange={(e) => ubahTelegram({ send_drills: e.target.checked })} />
                                <span>
                                    Kirim juga latihan ke Telegram
                                    <span className="block text-xs text-slate-500">
                                        Bawaannya mati, supaya grup tidak terbiasa mengabaikan pesan alarm.
                                    </span>
                                </span>
                            </label>
                            <label className="flex items-start gap-3 text-sm cursor-pointer">
                                <input type="checkbox" checked={tg.camera_offline} className="mt-1 accent-slate-700"
                                    onChange={(e) => ubahTelegram({ camera_offline: e.target.checked })} />
                                <span>
                                    Kabari grup saat kamera terputus atau dijeda
                                    <span className="block text-xs text-slate-500">
                                        Setelah 30 detik tanpa gambar dan saat kamera pulih, juga saat Mode
                                        perawatan dimulai, diperpanjang, atau selesai.
                                    </span>
                                </span>
                            </label>
                        </div>
                    )}
                    {kabarTg?.bagian === 'telegram' && <Kabar kabar={kabarTg} />}
                </Bagian>

                <Bagian id="atur-privasi" judul="Privasi" keterangan="Foto penghuni yang tergeletak adalah data kesehatan.">
                    {tg && (
                        <fieldset className="space-y-2">
                            <legend className="text-sm font-medium mb-1">Foto di pesan Telegram</legend>
                            {opsiFoto.map((o) => (
                                <label key={o.id} className="flex items-center gap-3 text-sm cursor-pointer min-h-8">
                                    <input type="radio" name="foto-telegram" value={o.id} checked={tg.photo_mode === o.id}
                                        onChange={() => ubahTelegram({ photo_mode: o.id }, 'privasi')} className="accent-slate-700" />
                                    {o.label}
                                </label>
                            ))}
                        </fieldset>
                    )}
                    <p className="text-xs text-slate-500">
                        Semua pesan dilindungi supaya tidak bisa diteruskan atau disimpan dari Telegram. Foto lengkapnya
                        tersimpan di server dan hanya bisa dilihat setelah masuk, di Riwayat Insiden.
                    </p>
                    {kabarTg?.bagian === 'privasi' && <Kabar kabar={kabarTg} />}
                </Bagian>

                <Bagian id="atur-tentang" judul="Tentang sistem">
                    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                        <dt className="text-slate-500">Aplikasi</dt>
                        <dd>FallDetect, prototipe proyek mahasiswa</dd>
                        <dt className="text-slate-500">Model aktif</dt>
                        <dd>{modeTerpilih?.label || '…'}</dd>
                        <dt className="text-slate-500">Backend</dt>
                        <dd className="font-mono text-xs break-all self-center">{API_BASE}</dd>
                    </dl>
                    <p className="text-xs text-slate-500">
                        Bukan alat kesehatan bersertifikat. Alarm adalah pemberitahuan kemungkinan jatuh dan tetap
                        perlu diperiksa langsung oleh perawat.
                    </p>
                </Bagian>
            </div>
        </div>
    );
}
