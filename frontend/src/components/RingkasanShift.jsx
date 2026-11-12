import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ChevronLeft, ChevronRight, Clock, Loader2, VideoOff } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { usePengunjung } from '../context/auth';
import { labelPutusan } from '../putusan';
import { jamDari } from '../statusKamera';
import { durasiTeks, msDari, tanggalJam } from '../waktu';
import { StatusPenanganan, StatusPutusan } from './StatusInsiden';

const BAGIAN = 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm';

function Angka({ judul, nilai, keterangan }) {
    return (
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
            <span className="block text-xs text-slate-500">{judul}</span>
            <span className="block text-xl font-bold tabular-nums">{nilai}</span>
            {keterangan && <span className="block text-xs text-slate-500">{keterangan}</span>}
        </div>
    );
}

/**
 * Ringkasan satu shift untuk serah terima: angka alarm, yang masih perlu ditindaklanjuti,
 * catatan perawat, Mode perawatan, dan kamera yang terputus. Bawaannya shift sebelumnya,
 * karena itulah yang dibaca shift yang baru datang. Shift berikutnya menandai sudah dibaca.
 */
export default function RingkasanShift({ onBuka }) {
    const pengunjung = usePengunjung();
    const [geser, setGeser] = useState(-1);
    const [data, setData] = useState(null);
    const [galat, setGalat] = useState('');
    const [menandai, setMenandai] = useState(false);

    const ambil = useCallback(async () => {
        try {
            const r = await api(`/api/ringkasan-shift/?geser=${geser}`);
            if (!r.ok) throw new Error(await bacaGalat(r));
            setData(await r.json());
            setGalat('');
        } catch (err) {
            setGalat(err instanceof TypeError ? PESAN_TERPUTUS : err.message);
        }
    }, [geser]);

    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
        const t = setInterval(ambil, 30_000);
        return () => clearInterval(t);
    }, [ambil]);

    const tandaiDibaca = async () => {
        setMenandai(true);
        try {
            const r = await api(`/api/ringkasan-shift/dibaca?geser=${geser}`, { method: 'POST' });
            if (!r.ok) throw new Error(await bacaGalat(r));
            setData(await r.json());
        } catch (err) {
            setGalat(err instanceof TypeError ? PESAN_TERPUTUS : err.message);
        } finally {
            setMenandai(false);
        }
    };

    if (!data) {
        return galat
            ? <p role="alert" className="text-sm text-red-700 dark:text-red-400">{galat}</p>
            : <p className="p-10 text-center text-sm text-slate-500 flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Memuat ringkasan…</p>;
    }

    const m = data.metrik;
    const dinilai = m.jatuh + m.palsu + m.belum_yakin;
    const mulai = msDari(data.mulai);
    const selesai = msDari(data.selesai);
    const tombolGeser = 'p-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40';

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-2">
                <button type="button" onClick={() => setGeser((g) => g - 1)} aria-label="Shift sebelumnya" className={tombolGeser}>
                    <ChevronLeft className="w-4 h-4" aria-hidden="true" />
                </button>
                <h2 className="font-semibold tabular-nums">
                    Shift {data.nama} · {tanggalJam(mulai)} sampai {jamDari(selesai)}
                    {data.berjalan && <span className="ml-2 text-xs font-medium px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800">sedang berjalan</span>}
                </h2>
                <button type="button" onClick={() => setGeser((g) => Math.min(0, g + 1))} disabled={geser === 0}
                    aria-label="Shift berikutnya" className={tombolGeser}>
                    <ChevronRight className="w-4 h-4" aria-hidden="true" />
                </button>
            </div>
            {galat && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{galat}</p>}

            <section className={BAGIAN} aria-label="Angka shift">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Angka judul="Alarm" nilai={m.total} keterangan={[data.latihan ? `ditambah ${data.latihan} latihan` : 'tanpa latihan',
                        m.terlewat ? `${m.terlewat} jatuh terlewat` : ''].filter(Boolean).join(' · ')} />
                    <Angka judul="Median waktu respons" nilai={m.median_respons_detik != null ? durasiTeks(m.median_respons_detik) : '–'}
                        keterangan={m.jumlah_respons ? `dari ${m.jumlah_respons} alarm` : null} />
                    <Angka judul="Alarm palsu" nilai={dinilai ? `${m.palsu} dari ${dinilai}` : '–'} keterangan="dari yang dinilai" />
                    <Angka judul="Telegram gagal" nilai={m.telegram_gagal} />
                </div>
            </section>

            <section className={BAGIAN}>
                <h3 className="text-sm font-semibold mb-2">Perlu ditindaklanjuti ({data.perlu_tindakan.length})</h3>
                {data.perlu_tindakan.length ? (
                    <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                        {data.perlu_tindakan.map((a) => (
                            <li key={a.id}>
                                <button type="button" onClick={() => onBuka(a)}
                                    className="w-full text-left py-2 flex flex-wrap items-center gap-x-3 gap-y-1 hover:bg-slate-50 dark:hover:bg-slate-800/50 rounded-lg px-1">
                                    <span className="font-medium text-sm">{a.camera_name || a.camera_id}</span>
                                    <span className="text-xs text-slate-500 tabular-nums">{jamDari(msDari(a.created_at))}</span>
                                    <StatusPenanganan alert={a} />
                                    {a.acknowledged && <StatusPutusan alert={a} />}
                                </button>
                            </li>
                        ))}
                    </ul>
                ) : <p className="text-sm text-slate-500">Semua alarm shift ini sudah ditangani dan dinilai.</p>}
            </section>

            <section className={BAGIAN}>
                <h3 className="text-sm font-semibold mb-2">Catatan perawat</h3>
                {data.catatan.length ? (
                    <ul className="space-y-2">
                        {data.catatan.map((a) => (
                            <li key={a.id} className="text-sm">
                                <span className="font-medium">{a.camera_name || a.camera_id}</span>
                                <span className="text-xs text-slate-500 tabular-nums"> · {jamDari(msDari(a.created_at))}
                                    {a.verdict ? ` · ${labelPutusan(a.verdict)}` : ''}</span>
                                <p className="whitespace-pre-wrap break-words text-slate-700 dark:text-slate-300">{a.caregiver_note}</p>
                            </li>
                        ))}
                    </ul>
                ) : <p className="text-sm text-slate-500">Tidak ada catatan.</p>}
            </section>

            {(data.jeda.length > 0 || data.kamera_terputus.length > 0) && (
                <section className={BAGIAN}>
                    <h3 className="text-sm font-semibold mb-2">Ruang yang tidak terpantau</h3>
                    <ul className="space-y-1 text-sm">
                        {data.jeda.map((j) => (
                            <li key={`${j.camera_name}-${j.mulai}`} className="flex items-start gap-2">
                                <Clock className="w-4 h-4 mt-0.5 shrink-0 text-blue-600" aria-hidden="true" />
                                <span className="tabular-nums">
                                    {j.camera_name}: Mode perawatan {jamDari(msDari(j.mulai))} sampai {jamDari(msDari(j.sampai))}
                                    {j.oleh ? `, dimulai ${j.oleh}` : ''}{j.dihentikan_oleh ? `, dihentikan ${j.dihentikan_oleh}` : ''}
                                </span>
                            </li>
                        ))}
                        {data.kamera_terputus.map((nama) => (
                            <li key={nama} className="flex items-start gap-2">
                                <VideoOff className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
                                <span>{nama}: kamera terputus sekarang</span>
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {!data.berjalan && (
                <div className="flex flex-wrap items-center gap-3">
                    {data.dibaca_oleh ? (
                        <p className="text-sm inline-flex items-center gap-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                            Dibaca {data.dibaca_oleh}, {tanggalJam(msDari(data.dibaca_pada))}
                        </p>
                    ) : pengunjung ? (
                        <p className="text-sm text-slate-500">Belum ditandai dibaca shift berikutnya.</p>
                    ) : (
                        <button type="button" onClick={tandaiDibaca} disabled={menandai}
                            className="min-h-11 px-4 rounded-lg bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-60">
                            <CheckCircle2 className="w-4 h-4" aria-hidden="true" /> Tandai sudah dibaca
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
