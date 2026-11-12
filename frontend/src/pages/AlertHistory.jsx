import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronRight, Download, FlaskConical, Inbox, Loader2 } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { usePengunjung } from '../context/auth';
import { useLive } from '../context/LiveContext';
import DetailInsiden from '../components/DetailInsiden';
import { StatusPenanganan, StatusPutusan, StatusTelegram } from '../components/StatusInsiden';
import { PUTUSAN } from '../putusan';
import { durasiTeks, msDari, tanggalJam, useJam, waktuRelatif } from '../waktu';

const RENTANG = [
    { id: '1', label: '24 jam terakhir' },
    { id: '7', label: '7 hari terakhir' },
    { id: '30', label: '30 hari terakhir' },
    { id: 'semua', label: 'Semua waktu' },
];
const PER_HALAMAN = 50;
const SELECT = 'bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500';

// `bertumpuk`: tanggal di baris kedua, supaya kolom Waktu di tabel tidak memakan
// lebar yang dibutuhkan kolom Penanganan di layar 1024 px.
function Waktu({ iso, sekarang, bertumpuk = false }) {
    const ms = msDari(iso);
    return (
        <time dateTime={iso} className="text-sm tabular-nums whitespace-nowrap">
            <span className="font-medium">{waktuRelatif(ms, sekarang)}</span>
            {bertumpuk
                ? <span className="block text-xs text-slate-500">{tanggalJam(ms)}</span>
                : <span className="text-slate-500"> · {tanggalJam(ms)}</span>}
        </time>
    );
}

// flex-col: isi tombol tidak ditengahkan vertikal, jadi sejajar dengan kartu biasa.
const KARTU = 'flex flex-col text-left rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm';

/** Satu kartu angka. Bila `onPilih` ada, kartunya sekaligus tombol filter. */
function Kartu({ judul, nilai, keterangan, onPilih, tegas = false }) {
    const isi = (
        <>
            <span className="block text-xs text-slate-500">{judul}</span>
            <span className={`block text-2xl font-bold tabular-nums mt-1 ${tegas ? 'text-red-700 dark:text-red-400' : ''}`}>{nilai}</span>
            <span className="block text-xs text-slate-500 mt-0.5">{keterangan}</span>
        </>
    );
    return onPilih
        ? <button type="button" onClick={onPilih} className={`${KARTU} hover:border-slate-400 dark:hover:border-slate-600`}>{isi}</button>
        : <div className={KARTU}>{isi}</div>;
}

/**
 * Empat angka untuk rentang yang dipilih, tanpa latihan. Persen selalu disertai jumlah
 * mutlak, karena dari jumlah kecil persen mudah menyesatkan.
 */
function KartuMetrik({ metrik, perluTindakan, labelRentang, keAntrean, kePalsu }) {
    if (!metrik) return null;
    const dinilai = metrik.jatuh + metrik.palsu + metrik.belum_yakin;
    const persen = dinilai ? Math.round((metrik.palsu / dinilai) * 100) : null;
    return (
        <section aria-label={`Angka ${labelRentang}, tanpa latihan`} className="mb-5">
            <p className="text-xs text-slate-500 mb-2">Angka {labelRentang.toLowerCase()}, tanpa latihan.</p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Kartu judul="Perlu tindakan" nilai={perluTindakan ?? '–'} tegas={perluTindakan > 0}
                    keterangan="belum ditangani atau belum dinilai" onPilih={keAntrean} />
                <Kartu judul="Median waktu respons"
                    nilai={metrik.median_respons_detik != null ? durasiTeks(metrik.median_respons_detik) : '–'}
                    keterangan={metrik.jumlah_respons ? `dari ${metrik.jumlah_respons} alarm, sampai ada yang ke sana` : 'belum ada alarm yang direspons'} />
                <Kartu judul="Alarm palsu"
                    nilai={dinilai ? `${metrik.palsu} dari ${dinilai}` : '–'}
                    keterangan={dinilai
                        ? `${persen}% dari yang dinilai${metrik.belum_dinilai ? `; ${metrik.belum_dinilai} belum dinilai` : ''}`
                        : 'belum ada alarm yang dinilai'}
                    onPilih={kePalsu} />
                <Kartu judul="Telegram gagal" nilai={metrik.telegram_gagal} tegas={metrik.telegram_gagal > 0}
                    keterangan={`dari ${metrik.total} alarm`} />
            </div>
        </section>
    );
}

function Ruang({ alert }) {
    return (
        <span className="inline-flex items-center gap-2 font-medium whitespace-nowrap">
            {alert.camera_name || alert.camera_id}
            {alert.simulated && <FlaskConical className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" aria-label="Latihan" />}
        </span>
    );
}

/**
 * Riwayat Insiden sebagai antrean kerja.
 *
 * Tab bawaan "Perlu tindakan" berisi alarm yang belum ditangani dan alarm yang
 * sudah ditangani tetapi belum dinilai. Tab "Semua" untuk menelusuri riwayat,
 * dengan filter ruang, putusan, dan rentang waktu. Detail tiap insiden (foto,
 * linimasa, putusan, catatan, Telegram) dibuka di laci samping.
 */
export default function AlertHistory() {
    const { alerts: alarmAktif, ringkasan, segarkanRingkasan, perbaruiAlert } = useLive();
    const sekarang = useJam(30000);

    const [tab, setTab] = useState('perlu_tindakan');
    const [kameraId, setKameraId] = useState('');
    const [putusan, setPutusan] = useState('');
    const [rentang, setRentang] = useState('30');
    const [latihan, setLatihan] = useState(false);
    const [batas, setBatas] = useState(PER_HALAMAN);

    const [daftar, setDaftar] = useState([]);
    const [adaLagi, setAdaLagi] = useState(false);
    const [memuat, setMemuat] = useState(true);
    const [galat, setGalat] = useState('');
    const [kamera, setKamera] = useState([]);
    const [metrik, setMetrik] = useState(null);
    // Disimpan sebagai objek, bukan id saja: insiden yang baru ditutup keluar dari
    // tab Perlu tindakan, tetapi lacinya tidak boleh ikut tertutup tiba-tiba.
    const [detail, setDetail] = useState(null);

    const pengunjung = usePengunjung();
    const [mengunduh, setMengunduh] = useState(false);
    const [galatUnduh, setGalatUnduh] = useState('');

    // Filter yang sama dipakai daftar dan ekspor CSV.
    const saringan = useCallback(() => {
        const q = new URLSearchParams();
        if (kameraId) q.set('camera_id', kameraId);
        if (tab === 'perlu_tindakan') {
            q.set('status', 'perlu_tindakan');
        } else {
            if (putusan) q.set('verdict', putusan);
            if (!latihan) q.set('simulated', 'false');
            if (rentang !== 'semua') q.set('sejak', new Date(Date.now() - Number(rentang) * 86400e3).toISOString());
        }
        return q;
    }, [tab, kameraId, putusan, rentang, latihan]);

    const ambil = useCallback(async () => {
        const q = saringan();
        q.set('limit', String(batas + 1));
        try {
            const r = await api(`/api/alerts/?${q}`);
            if (!r.ok) throw new Error(String(r.status));
            const d = await r.json();
            setDaftar(d.slice(0, batas));
            setAdaLagi(d.length > batas);
            setGalat('');
        } catch {
            setGalat(PESAN_TERPUTUS);
        } finally {
            setMemuat(false);
        }
    }, [saringan, batas]);

    // Semua baris yang cocok dengan filter, bukan hanya yang sedang tampil.
    const unduh = async () => {
        setMengunduh(true);
        setGalatUnduh('');
        try {
            const r = await api(`/api/alerts/ekspor?${saringan()}`);
            if (!r.ok) {
                setGalatUnduh(await bacaGalat(r));
                return;
            }
            const url = URL.createObjectURL(await r.blob());
            const d = new Date();
            const dua = (n) => String(n).padStart(2, '0');
            const a = document.createElement('a');
            a.href = url;
            a.download = `insiden-falldetect-${d.getFullYear()}${dua(d.getMonth() + 1)}${dua(d.getDate())}-${dua(d.getHours())}${dua(d.getMinutes())}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch {
            setGalatUnduh(PESAN_TERPUTUS);
        } finally {
            setMengunduh(false);
        }
    };

    // Segarkan berkala, dan seketika setiap ada alarm baru atau alarm ditutup.
    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambil();
        const t = setInterval(ambil, 5000);
        return () => clearInterval(t);
    }, [ambil, alarmAktif]);

    // Kartu angka mengikuti rentang waktu yang dipilih, dan ikut segar bersama daftar.
    const ambilMetrik = useCallback(async () => {
        const q = new URLSearchParams();
        if (rentang !== 'semua') q.set('sejak', new Date(Date.now() - Number(rentang) * 86400e3).toISOString());
        try {
            const r = await api(`/api/alerts/metrik?${q}`);
            if (r.ok) setMetrik(await r.json());
        } catch { /* kartu tetap menampilkan angka terakhir */ }
    }, [rentang]);

    useEffect(() => {
        // setState-nya terjadi di callback async setelah fetch selesai, bukan sinkron.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambilMetrik();
    }, [ambilMetrik, alarmAktif, ringkasan]);

    useEffect(() => {
        api('/api/cameras/')
            .then((r) => (r.ok ? r.json() : []))
            .then((d) => setKamera(d.map((c) => ({ id: c.camera_id, nama: c.name }))))
            .catch(() => { /* filter ruang tetap berisi ruang dari daftar insiden */ });
    }, []);

    // Ruang yang kameranya sudah dihapus tetap bisa dipilih, dengan nama saat kejadian.
    const pilihanKamera = useMemo(() => {
        const peta = new Map(kamera.map((k) => [k.id, k.nama]));
        daftar.forEach((a) => { if (!peta.has(a.camera_id)) peta.set(a.camera_id, a.camera_name || a.camera_id); });
        return [...peta.entries()];
    }, [kamera, daftar]);

    const gantiFilter = (setter) => (e) => {
        setter(e.target.type === 'checkbox' ? e.target.checked : e.target.value);
        setBatas(PER_HALAMAN);
    };

    const berubah = (data) => {
        setDetail(data);
        setDaftar((prev) => prev.map((a) => (a.id === data.id ? data : a)));
        perbaruiAlert(data);         // banner di atas ikut berubah tanpa menunggu siaran
        segarkanRingkasan();
        ambil();
    };

    const detailSegar = detail ? (daftar.find((a) => a.id === detail.id) || detail) : null;
    const tabKelas = (aktif) => `min-h-10 px-4 rounded-lg text-sm font-semibold inline-flex items-center gap-2 whitespace-nowrap ${aktif
        ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}`;

    return (
        <div className="p-4 md:p-8 w-full max-w-full min-w-0">
            <div className="mb-5 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div>
                    <h1 className="text-xl md:text-2xl font-bold">Riwayat Insiden</h1>
                    <p className="text-xs md:text-sm text-slate-500">
                        Setiap alarm, siapa yang menangani, dan apakah benar jatuh.
                    </p>
                </div>
                {!pengunjung && (
                    <button type="button" onClick={unduh} disabled={mengunduh}
                        title="Semua insiden sesuai tab dan filter di bawah, untuk uji mini atau laporan"
                        className="self-start shrink-0 min-h-10 px-3 rounded-lg border border-slate-300 dark:border-slate-700 text-sm font-semibold inline-flex items-center gap-2 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-60">
                        {mengunduh
                            ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                            : <Download className="w-4 h-4" aria-hidden="true" />}
                        Unduh CSV
                    </button>
                )}
            </div>

            {galatUnduh && (
                <p role="alert" className="mb-4 text-sm text-red-700 dark:text-red-400">
                    CSV gagal diunduh: {galatUnduh}
                </p>
            )}

            <KartuMetrik
                metrik={metrik}
                perluTindakan={ringkasan?.perlu_tindakan}
                labelRentang={RENTANG.find((r) => r.id === rentang)?.label || ''}
                keAntrean={() => { setTab('perlu_tindakan'); setBatas(PER_HALAMAN); }}
                kePalsu={() => { setTab('semua'); setPutusan('palsu'); setBatas(PER_HALAMAN); }}
            />

            <div className="flex flex-col lg:flex-row lg:items-center gap-3 mb-4">
                <div role="tablist" aria-label="Kelompok insiden" className="inline-flex self-start shrink-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-1 gap-1">
                    <button type="button" role="tab" aria-selected={tab === 'perlu_tindakan'}
                        onClick={() => { setTab('perlu_tindakan'); setBatas(PER_HALAMAN); }}
                        className={tabKelas(tab === 'perlu_tindakan')}>
                        Perlu tindakan
                        {ringkasan && <span className="tabular-nums font-normal">({ringkasan.perlu_tindakan})</span>}
                    </button>
                    <button type="button" role="tab" aria-selected={tab === 'semua'}
                        onClick={() => { setTab('semua'); setBatas(PER_HALAMAN); }}
                        className={tabKelas(tab === 'semua')}>
                        Semua
                    </button>
                </div>

                <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
                    <label className="sr-only" htmlFor="filter-ruang">Ruang</label>
                    <select id="filter-ruang" value={kameraId} onChange={gantiFilter(setKameraId)} className={SELECT}>
                        <option value="">Semua ruang</option>
                        {pilihanKamera.map(([id, nama]) => <option key={id} value={id}>{nama}</option>)}
                    </select>
                    {tab === 'semua' && (
                        <>
                            <label className="sr-only" htmlFor="filter-putusan">Putusan</label>
                            <select id="filter-putusan" value={putusan} onChange={gantiFilter(setPutusan)} className={SELECT}>
                                <option value="">Semua putusan</option>
                                <option value="belum_dinilai">Belum dinilai</option>
                                {PUTUSAN.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                            </select>
                            <label className="sr-only" htmlFor="filter-rentang">Rentang waktu</label>
                            <select id="filter-rentang" value={rentang} onChange={gantiFilter(setRentang)} className={SELECT}>
                                {RENTANG.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                            </select>
                            <label className="inline-flex items-center gap-2 text-sm px-2 min-h-10 cursor-pointer">
                                <input type="checkbox" checked={latihan} onChange={gantiFilter(setLatihan)} className="accent-blue-600" />
                                Tampilkan latihan
                            </label>
                        </>
                    )}
                </div>
            </div>


            {galat && (
                <div role="alert" className="mb-4 p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400 text-sm">
                    {galat}
                </div>
            )}

            {memuat && !daftar.length ? (
                <div className="p-10 text-center text-sm text-slate-500 flex items-center justify-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Memuat riwayat…
                </div>
            ) : !daftar.length && !galat ? (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-10 text-center">
                    <Inbox className="w-8 h-8 mx-auto text-slate-400" aria-hidden="true" />
                    <p className="mt-3 font-semibold">
                        {tab === 'perlu_tindakan' ? 'Tidak ada yang perlu ditindaklanjuti' : 'Tidak ada insiden pada pilihan ini'}
                    </p>
                    <p className="text-sm text-slate-500 mt-1">
                        {tab === 'perlu_tindakan'
                            ? 'Semua alarm sudah ditangani dan dinilai.'
                            : 'Ubah filter ruang, putusan, atau rentang waktu.'}
                    </p>
                </div>
            ) : (
                <>
                    {/* Layar lebar: tabel. */}
                    <div className="hidden md:block bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 text-xs">
                                    <th scope="col" className="p-3 font-semibold">Waktu</th>
                                    <th scope="col" className="p-3 font-semibold">Ruang</th>
                                    <th scope="col" className="p-3 font-semibold">Penanganan</th>
                                    <th scope="col" className="p-3 font-semibold">Putusan</th>
                                    <th scope="col" className="p-3 font-semibold">Telegram</th>
                                    <th scope="col" className="p-3"><span className="sr-only">Detail</span></th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                                {daftar.map((a) => (
                                    <tr key={a.id} onClick={() => setDetail(a)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors align-top">
                                        <td className="p-3"><Waktu iso={a.created_at} sekarang={sekarang} bertumpuk /></td>
                                        <td className="p-3 text-sm"><Ruang alert={a} /></td>
                                        <td className="p-3"><StatusPenanganan alert={a} /></td>
                                        <td className="p-3"><StatusPutusan alert={a} /></td>
                                        <td className="p-3"><StatusTelegram alert={a} /></td>
                                        <td className="p-3 text-right">
                                            <button type="button" onClick={(e) => { e.stopPropagation(); setDetail(a); }}
                                                className="inline-flex items-center gap-1 text-sm font-semibold px-2 py-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
                                                Detail <ChevronRight className="w-4 h-4" aria-hidden="true" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* HP: kartu, supaya status dan tombol tetap terlihat tanpa menggeser tabel. */}
                    <ul className="md:hidden space-y-3">
                        {daftar.map((a) => (
                            <li key={a.id}>
                                <button type="button" onClick={() => setDetail(a)}
                                    className="w-full text-left bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm space-y-2">
                                    <span className="flex items-center justify-between gap-3">
                                        <Ruang alert={a} />
                                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" aria-hidden="true" />
                                    </span>
                                    <Waktu iso={a.created_at} sekarang={sekarang} />
                                    <span className="flex flex-wrap items-start gap-2">
                                        <StatusPenanganan alert={a} />
                                        <StatusPutusan alert={a} />
                                    </span>
                                    <StatusTelegram alert={a} />
                                </button>
                            </li>
                        ))}
                    </ul>

                    {adaLagi && (
                        <div className="mt-4 text-center">
                            <button type="button" onClick={() => setBatas((b) => b + PER_HALAMAN)}
                                className="min-h-11 px-4 rounded-xl border border-slate-300 dark:border-slate-700 text-sm font-semibold hover:bg-slate-100 dark:hover:bg-slate-800">
                                Muat lebih banyak
                            </button>
                        </div>
                    )}
                </>
            )}

            {detailSegar && (
                <DetailInsiden alert={detailSegar} onTutup={() => setDetail(null)} onBerubah={berubah} />
            )}
        </div>
    );
}
