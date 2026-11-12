import { useEffect, useMemo, useState } from 'react';
import { CircleSlash, ImageOff, Loader2, Pause, Play, RotateCcw, X } from 'lucide-react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { API_BASE } from '../config';
import { durasiTeks, msDari, tanggalJam } from '../waktu';

// Keadaan klip selain "tersimpan". Kejadian dari sebelum ada fitur klip tidak berstatus.
const KABAR_KLIP = {
    merekam: 'Klip sedang disimpan, siap sekitar 5 detik sesudah alarm.',
    kosong: 'Tidak ada klip: kamera tidak mengirim gambar di sekitar kejadian.',
    gagal: 'Klip gagal disimpan di server.',
    dihapus: 'Klip sudah dihapus otomatis karena melewati masa simpan.',
};

const angka = (x) => x.toLocaleString('id-ID', { maximumFractionDigits: 1 });

/** Posisi frame dibaca relatif terhadap alarm, karena itulah patokan perawat. */
function teksWaktu(t) {
    if (Math.abs(t) < 0.15) return 'saat alarm';
    return t < 0 ? `${angka(-t)} dtk sebelum alarm` : `${angka(t)} dtk sesudah alarm`;
}

function indeksTerdekat(frame, t) {
    let terbaik = 0;
    frame.forEach((f, i) => { if (Math.abs(f.t - t) < Math.abs(frame[terbaik].t - t)) terbaik = i; });
    return terbaik;
}

/** Foto saat alarm; kejadian lama atau yang kameranya belum mengirim gambar tidak punya foto. */
function FotoKejadian({ alert }) {
    const [gagal, setGagal] = useState(false);
    if (gagal) {
        return (
            <div className="aspect-video rounded-xl bg-slate-100 dark:bg-slate-800 flex flex-col items-center justify-center gap-2 text-sm text-slate-500">
                <ImageOff className="w-6 h-6" aria-hidden="true" />
                Foto tidak tersimpan untuk kejadian ini.
            </div>
        );
    }
    return (
        <img
            src={`${API_BASE}/api/alerts/${alert.id}/snapshot`}
            alt={`Foto kejadian di ${alert.camera_name || alert.camera_id}`}
            onError={() => setGagal(true)}
            className="w-full rounded-xl bg-slate-950"
        />
    );
}

/**
 * Pemutar klip: frame JPEG yang diputar sesuai jarak waktunya, dengan penanda saat
 * orangnya mulai terbaca tergeletak dan saat alarm berbunyi.
 */
function PemutarKlip({ alert, onTutup }) {
    const [isi, setIsi] = useState(null);
    const [galat, setGalat] = useState('');
    const [idx, setIdx] = useState(0);
    const [jalan, setJalan] = useState(false);
    const [lambat, setLambat] = useState(false);

    useEffect(() => {
        let batal = false;
        (async () => {
            try {
                const r = await api(`/api/alerts/${alert.id}/klip`);
                if (!r.ok) {
                    if (!batal) setGalat(await bacaGalat(r));
                    return;
                }
                const data = await r.json();
                const frame = data.frame.map((f) => ({ t: f.t, src: `data:image/jpeg;base64,${f.jpeg}` }));
                // Urai semua gambar dulu supaya pemutaran tidak berkedip.
                await Promise.all(frame.map((f) => {
                    const g = new Image();
                    g.src = f.src;
                    return g.decode().catch(() => {});
                }));
                if (batal) return;
                setIsi({ ...data, frame });
                setJalan(true);
            } catch {
                if (!batal) setGalat(PESAN_TERPUTUS);
            }
        })();
        return () => { batal = true; };
    }, [alert.id]);

    const n = isi?.frame.length || 0;
    const selesai = n > 0 && idx >= n - 1;

    useEffect(() => {
        if (!jalan || !isi || selesai) return undefined;
        const jeda = (isi.frame[idx + 1].t - isi.frame[idx].t) * 1000 / (lambat ? 0.5 : 1);
        const t = setTimeout(() => setIdx((i) => Math.min(i + 1, n - 1)), Math.max(30, jeda));
        return () => clearTimeout(t);
    }, [jalan, isi, idx, lambat, selesai, n]);

    const penanda = useMemo(() => {
        if (!isi || n < 2) return [];
        const pos = (i) => `${(i / (n - 1)) * 100}%`;
        const hasil = [{ label: 'alarm', i: indeksTerdekat(isi.frame, 0), kelas: 'bg-red-600' }];
        const mulai = -isi.detik_tergeletak;
        if (mulai >= isi.frame[0].t) {
            hasil.unshift({ label: 'tergeletak', i: indeksTerdekat(isi.frame, mulai), kelas: 'bg-slate-500' });
        }
        return hasil.map((p) => ({ ...p, left: pos(p.i) }));
    }, [isi, n]);

    if (galat) {
        return (
            <div className="space-y-2">
                <FotoKejadian alert={alert} />
                <p role="alert" className="text-sm text-red-700 dark:text-red-400">Klip tidak bisa diputar: {galat}</p>
            </div>
        );
    }
    if (!isi) {
        return (
            <div className="aspect-video rounded-xl bg-slate-950 flex items-center justify-center gap-2 text-sm text-slate-300">
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Memuat klip…
            </div>
        );
    }

    const frame = isi.frame[idx];
    const sedangMain = jalan && !selesai;
    const tekanPutar = () => {
        if (selesai) {
            setIdx(0);
            setJalan(true);
        } else {
            setJalan((j) => !j);
        }
    };

    return (
        <figure className="space-y-2">
            <div className="relative">
                <img src={frame.src} alt={`Klip kejadian di ${alert.camera_name || alert.camera_id}, ${teksWaktu(frame.t)}`}
                    className="w-full rounded-xl bg-slate-950" />
                <span className="absolute top-2 left-2 px-2 py-1 rounded-md bg-black/70 text-white text-xs font-semibold tabular-nums">
                    {teksWaktu(frame.t)}
                </span>
                <button type="button" onClick={onTutup} aria-label="Tutup klip, kembali ke foto"
                    className="absolute top-2 right-2 p-1.5 rounded-md bg-black/70 text-white hover:bg-black/85">
                    <X className="w-4 h-4" aria-hidden="true" />
                </button>
            </div>

            <div className="flex items-center gap-3">
                <button type="button" onClick={tekanPutar}
                    aria-label={selesai ? 'Putar ulang' : sedangMain ? 'Jeda' : 'Putar'}
                    className="shrink-0 w-11 h-11 rounded-full bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 inline-flex items-center justify-center">
                    {selesai ? <RotateCcw className="w-5 h-5" aria-hidden="true" />
                        : sedangMain ? <Pause className="w-5 h-5" aria-hidden="true" />
                            : <Play className="w-5 h-5" aria-hidden="true" />}
                </button>
                <div className="flex-1 min-w-0 pb-5">
                    <input type="range" min={0} max={n - 1} step={1} value={idx}
                        onChange={(e) => { setJalan(false); setIdx(Number(e.target.value)); }}
                        aria-label="Posisi klip" aria-valuetext={teksWaktu(frame.t)}
                        className="w-full accent-slate-900 dark:accent-slate-100" />
                    <div className="relative h-0" aria-hidden="true">
                        {penanda.map((p) => (
                            <span key={p.label} className="absolute top-0 -translate-x-1/2 flex flex-col items-center" style={{ left: p.left }}>
                                <span className={`w-0.5 h-2 ${p.kelas}`} />
                                <span className="text-[11px] leading-none text-slate-500 whitespace-nowrap mt-0.5">{p.label}</span>
                            </span>
                        ))}
                    </div>
                </div>
                <button type="button" onClick={() => setLambat((l) => !l)} aria-pressed={lambat}
                    className={`shrink-0 min-h-9 px-2.5 rounded-lg text-xs font-semibold border ${lambat
                        ? 'bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100'
                        : 'border-slate-300 dark:border-slate-700'}`}>
                    0,5×
                </button>
            </div>
            <figcaption className="text-xs text-slate-500">
                {durasiTeks(isi.frame[n - 1].t - isi.frame[0].t)}, {n} gambar. Dihapus otomatis {tanggalJam(msDari(isi.dihapus_pada))}.
            </figcaption>
        </figure>
    );
}

/** Bukti kejadian di laci detail: foto saat alarm, dan klip sebelum sampai sesudahnya bila ada. */
export default function BuktiKejadian({ alert }) {
    const [putar, setPutar] = useState(false);
    const status = alert.klip_status;

    if (putar && status === 'tersimpan') return <PemutarKlip alert={alert} onTutup={() => setPutar(false)} />;
    return (
        <div className="space-y-2">
            <div className="relative">
                <FotoKejadian alert={alert} />
                {status === 'tersimpan' && (
                    <button type="button" onClick={() => setPutar(true)}
                        className="absolute left-3 bottom-3 min-h-10 px-3 rounded-full bg-black/75 text-white text-sm font-semibold inline-flex items-center gap-2 hover:bg-black/90">
                        <Play className="w-4 h-4" aria-hidden="true" />
                        Putar klip{alert.klip_detik ? ` · ${durasiTeks(alert.klip_detik)}` : ''}
                    </button>
                )}
            </div>
            {KABAR_KLIP[status] && (
                <p role="status" className="text-xs text-slate-500 flex items-center gap-2">
                    {status === 'merekam'
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" aria-hidden="true" />
                        : <CircleSlash className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />}
                    {KABAR_KLIP[status]}
                </p>
            )}
        </div>
    );
}
