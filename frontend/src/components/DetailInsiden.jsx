import { useEffect, useId, useState } from 'react';
import { CheckCircle2, Footprints, Pencil, RotateCw, X } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { ALASAN_PALSU, labelAlasan, labelPutusan, PUTUSAN } from '../putusan';
import { jamDari } from '../statusKamera';
import { durasiTeks, msDari, selisihDetik, tanggalJam } from '../waktu';
import BuktiKejadian from './BuktiKejadian';
import FormPenutupan, { PilihanRadio } from './FormPenutupan';
import { StatusTelegram } from './StatusInsiden';
import { usePengunjung } from '../context/auth';

const MODEL = { pose: 'YOLO11-Pose', bbox: 'Model custom (bbox)' };
const TOMBOL = 'min-h-11 px-4 rounded-lg text-sm font-semibold inline-flex items-center justify-center gap-2';

/** Ubah putusan alarm yang sudah ditangani. Alasan wajib bila alarm palsu. */
function FormPutusan({ alert, onSelesai, onBatal }) {
    const id = useId();
    const [putusan, setPutusan] = useState(alert.verdict || '');
    const [alasan, setAlasan] = useState(alert.verdict_reason || '');
    const [galat, setGalat] = useState('');
    const [sibuk, setSibuk] = useState(false);
    const siap = putusan && (putusan !== 'palsu' || alasan);

    const simpan = async (e) => {
        e.preventDefault();
        if (!siap || sibuk) return;
        setSibuk(true);
        setGalat('');
        try {
            const r = await api(`/api/alerts/${alert.id}/verdict`, {
                method: 'PUT', json: { verdict: putusan, reason: putusan === 'palsu' ? alasan : null },
            });
            if (r.ok) onSelesai(await r.json());
            else setGalat(await bacaGalat(r));
        } catch {
            setGalat(PESAN_TERPUTUS);
        } finally {
            setSibuk(false);
        }
    };

    return (
        <form onSubmit={simpan} className="space-y-3 rounded-xl border border-slate-200 bg-white p-3 text-slate-800">
            <fieldset>
                <legend className="text-sm font-semibold mb-2">Apakah ini benar jatuh?</legend>
                <PilihanRadio nama={`${id}-p`} pilihan={PUTUSAN} nilai={putusan}
                    onUbah={(v) => { setPutusan(v); if (v !== 'palsu') setAlasan(''); }} />
            </fieldset>
            {putusan === 'palsu' && (
                <fieldset>
                    <legend className="text-sm font-semibold mb-2">Alasannya <span className="font-normal text-slate-500">(wajib)</span></legend>
                    <PilihanRadio nama={`${id}-a`} pilihan={ALASAN_PALSU} nilai={alasan} onUbah={setAlasan} />
                </fieldset>
            )}
            {galat && <p role="alert" className="text-sm text-red-700">{galat}</p>}
            <div className="flex gap-2">
                <button type="submit" disabled={!siap || sibuk} className={`${TOMBOL} bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40`}>
                    {sibuk ? 'Menyimpan…' : 'Simpan putusan'}
                </button>
                <button type="button" onClick={onBatal} className={`${TOMBOL} font-medium border border-slate-300 text-slate-700 hover:bg-slate-50`}>
                    Batal
                </button>
            </div>
        </form>
    );
}

/** Catatan perawat, bisa ditambah atau diubah kapan saja. */
function FormCatatan({ alert, onSelesai, onBatal }) {
    const [teks, setTeks] = useState(alert.caregiver_note || '');
    const [galat, setGalat] = useState('');
    const [sibuk, setSibuk] = useState(false);

    const simpan = async (e) => {
        e.preventDefault();
        setSibuk(true);
        setGalat('');
        try {
            const r = await api(`/api/alerts/${alert.id}/note`, { method: 'PUT', json: { note: teks } });
            if (r.ok) onSelesai(await r.json());
            else setGalat(await bacaGalat(r));
        } catch {
            setGalat(`${PESAN_TERPUTUS} Tulisan Anda masih ada.`);
        } finally {
            setSibuk(false);
        }
    };

    return (
        <form onSubmit={simpan} className="space-y-2">
            <label htmlFor={`catatan-${alert.id}`} className="sr-only">Catatan tindakan</label>
            <textarea
                id={`catatan-${alert.id}`}
                autoFocus
                rows={3}
                maxLength={500}
                value={teks}
                onChange={(e) => setTeks(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Escape') onBatal(); }}
                placeholder="Tindakan yang diambil, mis. dibantu duduk, tidak ada luka."
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {galat && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{galat}</p>}
            <div className="flex gap-2">
                <button type="submit" disabled={sibuk} className={`${TOMBOL} bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-50`}>
                    {sibuk ? 'Menyimpan…' : 'Simpan catatan'}
                </button>
                <button type="button" onClick={onBatal} className={`${TOMBOL} font-medium border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800`}>
                    Batal
                </button>
            </div>
        </form>
    );
}

function BarisWaktu({ judul, waktu, dari, children }) {
    const ms = msDari(waktu);
    const jeda = dari ? selisihDetik(dari, waktu) : null;
    return (
        <li className="relative pl-5">
            <span aria-hidden="true" className="absolute -left-[5.5px] top-1.5 w-2.5 h-2.5 rounded-full bg-slate-400 dark:bg-slate-500" />
            <p className="text-sm font-medium">{judul}</p>
            <p className="text-xs text-slate-500 tabular-nums">
                {Number.isFinite(ms) ? jamDari(ms) : ''}
                {jeda !== null && ` · ${durasiTeks(jeda)} sesudah terdeteksi`}
            </p>
            {children}
        </li>
    );
}

/**
 * Laci detail satu insiden: foto dan klip, linimasa penanganan, keadaan sistem saat itu,
 * putusan, catatan, dan status Telegram. Alarm yang masih terbuka bisa langsung
 * ditangani dari sini, termasuk yang sudah tidak tampil sebagai banner.
 */
export default function DetailInsiden({ alert, onTutup, onBerubah }) {
    const [mode, setMode] = useState(null);     // null | 'tutup' | 'putusan' | 'catatan'
    const [galat, setGalat] = useState('');
    const [sibuk, setSibuk] = useState(false);
    const nama = alert.camera_name || alert.camera_id;
    const latihan = Boolean(alert.simulated);
    // Pengunjung pameran hanya membaca: semua tombol yang mengubah data disembunyikan.
    const pengunjung = usePengunjung();

    useEffect(() => {
        const tekan = (e) => { if (e.key === 'Escape' && !mode) onTutup(); };
        document.addEventListener('keydown', tekan);
        return () => document.removeEventListener('keydown', tekan);
    }, [mode, onTutup]);

    const selesai = (data) => {
        setMode(null);
        onBerubah(data);
    };

    const panggil = async (jalur, opsi) => {
        setSibuk(true);
        setGalat('');
        try {
            const r = await api(jalur, opsi);
            if (r.ok) onBerubah(await r.json());
            else setGalat(await bacaGalat(r));
        } catch {
            setGalat(PESAN_TERPUTUS);
        } finally {
            setSibuk(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex justify-end">
            <div className="absolute inset-0 bg-black/40" onClick={onTutup} aria-hidden="true" />
            <aside
                role="dialog"
                aria-modal="true"
                aria-label={`Detail insiden ${nama}`}
                className="relative h-full w-full sm:max-w-lg overflow-y-auto bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 shadow-2xl"
            >
                <header className="sticky top-0 z-10 flex items-start justify-between gap-3 p-4 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <div className="min-w-0">
                        <h2 className="font-bold text-lg truncate">{nama}</h2>
                        <p className="text-xs text-slate-500 tabular-nums">
                            {latihan ? 'Latihan · ' : ''}{tanggalJam(msDari(alert.created_at))} · insiden #{alert.id}
                        </p>
                    </div>
                    <button type="button" onClick={onTutup} aria-label="Tutup detail" className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
                        <X className="w-5 h-5" />
                    </button>
                </header>

                <div className="p-4 space-y-6">
                    <BuktiKejadian alert={alert} />

                    {!alert.acknowledged && !pengunjung && (
                        <section className="space-y-2">
                            {mode === 'tutup' ? (
                                <FormPenutupan alert={alert} onSelesai={selesai} onBatal={() => setMode(null)} />
                            ) : alert.claimed_by ? (
                                <button type="button" onClick={() => setMode('tutup')} className={`${TOMBOL} w-full bg-slate-900 text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900`}>
                                    <CheckCircle2 className="w-4 h-4" aria-hidden="true" /> Tandai Ditangani
                                </button>
                            ) : (
                                <button type="button" disabled={sibuk} onClick={() => panggil(`/api/alerts/${alert.id}/claim`, { method: 'PUT' })}
                                    className={`${TOMBOL} w-full bg-red-700 text-white hover:bg-red-800 disabled:opacity-60`}>
                                    <Footprints className="w-4 h-4" aria-hidden="true" /> Saya ke sana
                                </button>
                            )}
                        </section>
                    )}

                    {galat && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{galat}</p>}

                    <section>
                        <h3 className="text-sm font-semibold mb-3">Linimasa</h3>
                        <ol className="space-y-3 border-l border-slate-200 dark:border-slate-700 ml-1">
                            <BarisWaktu judul={`Terbaca berbaring ${Math.round(alert.fall_duration)} detik, alarm berbunyi`} waktu={alert.created_at} />
                            {alert.claimed_by && (
                                <BarisWaktu judul={`${alert.claimed_by} menuju lokasi`} waktu={alert.claimed_at} dari={alert.created_at} />
                            )}
                            {alert.acknowledged && (
                                <BarisWaktu judul={`Ditangani${alert.acknowledged_by ? ` oleh ${alert.acknowledged_by}` : ''}`}
                                    waktu={alert.acknowledged_at} dari={alert.created_at} />
                            )}
                            {alert.verdict && (
                                <BarisWaktu
                                    judul={`Putusan: ${labelPutusan(alert.verdict)}${alert.verdict === 'palsu' ? `, ${labelAlasan(alert.verdict_reason).toLowerCase()}` : ''}`}
                                    waktu={alert.verdict_at}
                                >
                                    {alert.verdict_by && <p className="text-xs text-slate-500">oleh {alert.verdict_by}</p>}
                                </BarisWaktu>
                            )}
                        </ol>
                    </section>

                    {alert.acknowledged && !latihan && (
                        <section className="space-y-2">
                            <div className="flex items-center justify-between gap-3">
                                <h3 className="text-sm font-semibold">Putusan</h3>
                                {mode !== 'putusan' && !pengunjung && (
                                    <button type="button" onClick={() => setMode('putusan')} className="text-sm font-semibold underline underline-offset-2">
                                        {alert.verdict ? 'Ubah putusan' : 'Beri putusan'}
                                    </button>
                                )}
                            </div>
                            {mode === 'putusan' ? (
                                <FormPutusan alert={alert} onSelesai={selesai} onBatal={() => setMode(null)} />
                            ) : (
                                <p className="text-sm">
                                    {alert.verdict
                                        ? `${labelPutusan(alert.verdict)}${alert.verdict === 'palsu' ? ` (${labelAlasan(alert.verdict_reason)})` : ''}`
                                        : 'Belum dinilai. Insiden ini tetap di antrean Perlu tindakan sampai dinilai.'}
                                </p>
                            )}
                        </section>
                    )}

                    <section className="space-y-2">
                        <div className="flex items-center justify-between gap-3">
                            <h3 className="text-sm font-semibold">Catatan perawat</h3>
                            {mode !== 'catatan' && !pengunjung && (
                                <button type="button" onClick={() => setMode('catatan')} className="inline-flex items-center gap-1 text-sm font-semibold underline underline-offset-2">
                                    <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                                    {alert.caregiver_note ? 'Ubah' : 'Tambah catatan'}
                                </button>
                            )}
                        </div>
                        {mode === 'catatan' ? (
                            <FormCatatan alert={alert} onSelesai={selesai} onBatal={() => setMode(null)} />
                        ) : (
                            <p className="text-sm whitespace-pre-wrap break-words text-slate-700 dark:text-slate-300">
                                {alert.caregiver_note || 'Belum ada catatan.'}
                            </p>
                        )}
                    </section>

                    <section>
                        <h3 className="text-sm font-semibold mb-2">Keadaan sistem saat itu</h3>
                        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                            <dt className="text-slate-500">Menunggu sebelum alarm</dt>
                            <dd className="tabular-nums">{alert.threshold_sec != null ? `${alert.threshold_sec} detik` : 'tidak tercatat'}</dd>
                            <dt className="text-slate-500">Model</dt>
                            <dd>{MODEL[alert.detection_mode] || alert.detection_mode || 'tidak tercatat'}</dd>
                            <dt className="text-slate-500">Telegram</dt>
                            <dd className="flex flex-wrap items-center gap-2">
                                <StatusTelegram alert={alert} />
                                {alert.telegram_status === 'gagal' && !pengunjung && (
                                    <button type="button" disabled={sibuk}
                                        onClick={() => panggil(`/api/alerts/${alert.id}/telegram`, { method: 'POST' })}
                                        className="inline-flex items-center gap-1 text-sm font-semibold underline underline-offset-2 disabled:opacity-50">
                                        <RotateCw className="w-3.5 h-3.5" aria-hidden="true" /> Coba lagi
                                    </button>
                                )}
                            </dd>
                        </dl>
                    </section>
                </div>
            </aside>
        </div>
    );
}
