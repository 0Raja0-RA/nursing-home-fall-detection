import { useId, useState } from 'react';
import { api, bacaGalat, PESAN_TERPUTUS } from '../api';
import { ALASAN_PALSU, PUTUSAN } from '../putusan';

/**
 * Pilihan berbentuk tombol, tetapi tetap radio bawaan browser supaya bisa dipilih
 * dengan keyboard dan dibaca pembaca layar.
 */
export function PilihanRadio({ nama, pilihan, nilai, onUbah }) {
    return (
        <div className="flex flex-wrap gap-2">
            {pilihan.map((p) => {
                // Warna dipilih di sini, bukan lewat peer-checked: gaya hover yang terang
                // sempat mengalahkan latar gelap pilihan, sehingga pilihan yang baru diklik
                // tampil putih di atas putih selama kursor masih di atasnya.
                const terpilih = nilai === p.id;
                return (
                    <label key={p.id} className="cursor-pointer">
                        <input
                            type="radio"
                            name={nama}
                            value={p.id}
                            checked={terpilih}
                            onChange={() => onUbah(p.id)}
                            className="peer sr-only"
                        />
                        <span className={`inline-flex min-h-11 items-center px-3 rounded-lg border text-sm font-medium peer-focus-visible:ring-2 peer-focus-visible:ring-blue-500 peer-focus-visible:ring-offset-1 ${terpilih
                            ? 'bg-slate-900 border-slate-900 text-white'
                            : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-100'}`}>
                            {p.label}
                        </span>
                    </label>
                );
            })}
        </div>
    );
}

/**
 * Formulir "Tandai Ditangani": putusan, alasan bila alarm palsu, dan catatan.
 *
 * Putusan wajib dipilih di sini; "Belum yakin" adalah jalan keluar yang jujur.
 * Alarm palsu wajib beralasan supaya angka alarm palsu bisa dipakai untuk
 * memperbaiki model atau ambang. Latihan ditutup tanpa putusan, karena tidak
 * ikut dihitung.
 *
 * Dipakai di dialog Tandai Ditangani dari banner alarm dan di laci detail Riwayat
 * Insiden. Kontrolnya berwarna terang, jadi formulir ini selalu berlatar putih: di laci
 * sebagai kartu putih, di dialog (`polos`) menyatu dengan dialog pada tema terang dan
 * menjadi kartu putih pada tema gelap.
 */
export default function FormPenutupan({ alert, onSelesai, onBatal, polos = false }) {
    const id = useId();
    const latihan = Boolean(alert.simulated);
    const [putusan, setPutusan] = useState('');
    const [alasan, setAlasan] = useState('');
    const [catatan, setCatatan] = useState(alert.caregiver_note || '');
    const [sibuk, setSibuk] = useState(false);
    const [galat, setGalat] = useState('');

    const siap = latihan || (putusan && (putusan !== 'palsu' || alasan));

    const kirim = async (e) => {
        e.preventDefault();
        if (!siap || sibuk) return;
        setSibuk(true);
        setGalat('');
        try {
            const r = await api(`/api/alerts/${alert.id}/ack`, {
                method: 'PUT',
                json: latihan
                    ? { note: catatan || null }
                    : { verdict: putusan, reason: putusan === 'palsu' ? alasan : null, note: catatan || null },
            });
            if (!r.ok) {
                setGalat(await bacaGalat(r));
                return;
            }
            onSelesai(await r.json());
        } catch {
            setGalat(`${PESAN_TERPUTUS} Alarm tetap ditampilkan; coba lagi.`);
        } finally {
            setSibuk(false);
        }
    };

    return (
        <form onSubmit={kirim} className={polos
            ? 'w-full space-y-3 dark:rounded-xl dark:bg-white dark:text-slate-800 dark:p-4'
            : 'w-full rounded-xl bg-white text-slate-800 p-3 sm:p-4 shadow-sm space-y-3'}>
            {latihan ? (
                <p className="text-sm text-slate-600">Latihan ditutup tanpa putusan, dan tidak ikut dihitung di riwayat.</p>
            ) : (
                <fieldset className="space-y-2">
                    <legend className="text-sm font-semibold mb-2">Apakah ini benar jatuh?</legend>
                    <PilihanRadio
                        nama={`${id}-putusan`}
                        pilihan={PUTUSAN}
                        nilai={putusan}
                        onUbah={(v) => { setPutusan(v); if (v !== 'palsu') setAlasan(''); }}
                    />
                </fieldset>
            )}

            {putusan === 'palsu' && (
                <fieldset className="space-y-2">
                    <legend className="text-sm font-semibold mb-2">Alasannya <span className="font-normal text-slate-500">(wajib)</span></legend>
                    <PilihanRadio nama={`${id}-alasan`} pilihan={ALASAN_PALSU} nilai={alasan} onUbah={setAlasan} />
                </fieldset>
            )}

            <label className="block text-sm">
                <span className="font-semibold">Catatan tindakan</span>{' '}
                <span className="text-slate-500">({alasan === 'lainnya' ? 'jelaskan singkat' : 'opsional'})</span>
                <textarea
                    rows={2}
                    maxLength={500}
                    value={catatan}
                    onChange={(e) => setCatatan(e.target.value)}
                    placeholder="Contoh: dibantu duduk, tidak ada luka."
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </label>

            {galat && <p role="alert" className="text-sm text-red-700">{galat}</p>}

            <div className="flex flex-col sm:flex-row gap-2">
                <button
                    type="submit"
                    disabled={!siap || sibuk}
                    className="min-h-11 px-4 rounded-lg text-sm font-semibold bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    {sibuk ? 'Menyimpan…' : latihan ? 'Tutup latihan' : 'Simpan dan tutup alarm'}
                </button>
                <button
                    type="button"
                    onClick={onBatal}
                    className="min-h-11 px-4 rounded-lg text-sm font-medium border border-slate-300 text-slate-700 hover:bg-slate-50"
                >
                    Batal
                </button>
                {!siap && !latihan && (
                    <p className="text-xs text-slate-500 self-center">
                        {putusan === 'palsu' ? 'Pilih alasannya dulu.' : 'Pilih salah satu jawaban dulu.'}
                    </p>
                )}
            </div>
        </form>
    );
}
