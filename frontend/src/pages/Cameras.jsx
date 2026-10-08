import { useCallback, useEffect, useState } from 'react';
import { Camera, Plus, Trash2, CheckCircle2, Video, AlertCircle, Loader2, Radar } from 'lucide-react';
import { API_BASE } from '../config';

const ROTASI = [0, 90, 180, 270];

export default function Cameras() {
    const [cameras, setCameras] = useState([]);
    const [newName, setNewName] = useState('');
    const [newUrl, setNewUrl] = useState('');
    const [pesan, setPesan] = useState(null);          // { tipe: 'error' | 'info', teks }
    const [menambah, setMenambah] = useState(false);
    const [memindai, setMemindai] = useState(false);
    const [kandidat, setKandidat] = useState(null);     // hasil pemindaian jaringan

    const ambilDaftar = useCallback(async () => {
        try {
            const r = await fetch(`${API_BASE}/api/cameras/`);
            if (!r.ok) throw new Error(`Backend menjawab ${r.status}`);
            setCameras(await r.json());
            setPesan((p) => (p?.tipe === 'koneksi' ? null : p));
        } catch {
            setPesan({ tipe: 'koneksi', teks: `Tidak bisa menghubungi backend di ${API_BASE}. Jalankan run-backend.bat dulu.` });
        }
    }, []);

    // Muat daftar di awal, lalu segarkan berkala supaya status Terhubung/Terputus ikut hidup.
    useEffect(() => {
        // Ini justru kasus yang dibolehkan aturan tersebut: berlangganan ke sistem luar
        // (backend). setState-nya terjadi di dalam callback async setelah fetch selesai,
        // bukan secara sinkron, tapi linter tidak bisa menelusuri sampai ke sana.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        ambilDaftar();
        const t = setInterval(ambilDaftar, 3000);
        return () => clearInterval(t);
    }, [ambilDaftar]);

    const bacaError = async (r) => {
        try {
            const b = await r.json();
            if (typeof b.detail === 'string') return b.detail;
            if (Array.isArray(b.detail)) return b.detail.map((d) => d.msg).join(', ');
        } catch { /* body bukan JSON */ }
        return `Backend menjawab ${r.status}`;
    };

    const handleAddCamera = async (e) => {
        e.preventDefault();
        if (!newName || !newUrl || menambah) return;
        setMenambah(true);
        setPesan(null);
        try {
            const r = await fetch(`${API_BASE}/api/cameras/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName, source: newUrl, rotate: 0 }),
            });
            if (!r.ok) {
                setPesan({ tipe: 'error', teks: await bacaError(r) });
                return;
            }
            setNewName('');
            setNewUrl('');
            setKandidat(null);
            await ambilDaftar();
        } catch {
            setPesan({ tipe: 'error', teks: `Tidak bisa menghubungi backend di ${API_BASE}.` });
        } finally {
            setMenambah(false);
        }
    };

    const handleDelete = async (id) => {
        setPesan(null);
        try {
            const r = await fetch(`${API_BASE}/api/cameras/${id}`, { method: 'DELETE' });
            if (!r.ok && r.status !== 204) setPesan({ tipe: 'error', teks: await bacaError(r) });
            await ambilDaftar();
        } catch {
            setPesan({ tipe: 'error', teks: `Tidak bisa menghubungi backend di ${API_BASE}.` });
        }
    };

    const ubahRotasi = async (id, rotate) => {
        setPesan(null);
        try {
            const r = await fetch(`${API_BASE}/api/cameras/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rotate: Number(rotate) }),
            });
            if (!r.ok) setPesan({ tipe: 'error', teks: await bacaError(r) });
            await ambilDaftar();
        } catch {
            setPesan({ tipe: 'error', teks: `Tidak bisa menghubungi backend di ${API_BASE}.` });
        }
    };

    // Alamat IP kamera HP berubah setiap pindah WiFi. Pemindaian ini mencari sendiri
    // perangkat yang menyiarkan kamera di jaringan lokal, jadi alamatnya tidak perlu
    // dibaca manual dari layar HP.
    const pindaiJaringan = async () => {
        setMemindai(true);
        setPesan(null);
        setKandidat(null);
        try {
            const r = await fetch(`${API_BASE}/api/cameras/scan`, { method: 'POST' });
            if (!r.ok) {
                setPesan({ tipe: 'error', teks: await bacaError(r) });
                return;
            }
            const hasil = await r.json();
            setKandidat(hasil);
            if (hasil.candidates.length === 0) {
                setPesan({
                    tipe: 'info',
                    teks: `Tidak ada kamera ditemukan di ${hasil.subnets.join(', ') || 'jaringan ini'}. `
                        + 'Pastikan aplikasi kamera di HP sedang menyala dan berada di WiFi yang sama. '
                        + 'WiFi kampus sering memblokir koneksi antar-perangkat, jadi pakai hotspot HP.',
                });
            }
        } catch {
            setPesan({ tipe: 'error', teks: `Tidak bisa menghubungi backend di ${API_BASE}.` });
        } finally {
            setMemindai(false);
        }
    };

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="mb-6">
                <h1 className="text-2xl font-bold">Manajemen Kamera CCTV</h1>
                <p className="text-sm text-slate-500">Hubungkan dan kelola stream RTSP atau IP Camera dari setiap kamar lansia.</p>
            </div>

            {/* Form Tambah Kamera */}
            <form onSubmit={handleAddCamera} className="bg-white dark:bg-slate-900 p-6 rounded-2xl border border-slate-200 dark:border-slate-800 mb-8 grid grid-cols-1 md:grid-cols-3 gap-4 items-end shadow-sm">
                <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">Nama Lokasi / Kamar</label>
                    <input
                        type="text"
                        placeholder="Contoh: Kamar 01 - Jenderal Ilham"
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500"
                    />
                </div>
                <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">URL RTSP Stream</label>
                    <input
                        type="text"
                        placeholder="http://192.168.43.1:8080/video  ·  rtsp://...  ·  0"
                        value={newUrl}
                        onChange={(e) => setNewUrl(e.target.value)}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 font-mono"
                    />
                </div>
                <div className="flex gap-2">
                    <button type="submit" disabled={menambah} className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-medium py-2.5 px-4 rounded-xl flex items-center justify-center gap-2 transition-colors text-sm shadow-md shadow-blue-600/20">
                        {menambah
                            ? <><Loader2 className="w-4 h-4 animate-spin" /> Memeriksa...</>
                            : <><Plus className="w-4 h-4" /> Tambah Kamera</>}
                    </button>
                    <button
                        type="button"
                        onClick={pindaiJaringan}
                        disabled={memindai}
                        title="Cari kamera di jaringan lokal"
                        className="bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 disabled:opacity-60 text-slate-600 dark:text-slate-300 font-medium py-2.5 px-3 rounded-xl flex items-center justify-center gap-2 transition-colors text-sm"
                    >
                        {memindai ? <Loader2 className="w-4 h-4 animate-spin" /> : <Radar className="w-4 h-4" />}
                        <span className="hidden lg:inline">Pindai</span>
                    </button>
                </div>
            </form>

            {/* Pesan kesalahan / info dari backend */}
            {pesan && (
                <div className={`mb-6 p-4 rounded-xl border text-sm flex items-start gap-2 ${
                    pesan.tipe === 'info'
                        ? 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400'
                        : 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400'
                }`}>
                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{pesan.teks}</span>
                </div>
            )}

            {/* Kandidat hasil pemindaian jaringan */}
            {kandidat && kandidat.candidates.length > 0 && (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 mb-8 overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center gap-2">
                        <Radar className="w-4 h-4 text-blue-500" />
                        Ditemukan di jaringan
                        <span className="font-normal text-slate-500">
                            ({kandidat.subnets.join(', ')} · {kandidat.duration_sec}s)
                        </span>
                    </div>
                    <div className="divide-y divide-slate-200 dark:divide-slate-800">
                        {kandidat.candidates.map((k) => (
                            <button
                                key={`${k.ip}:${k.port}`}
                                type="button"
                                onClick={() => { setNewUrl(k.source); setKandidat(null); }}
                                className="w-full p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors text-left"
                            >
                                <div>
                                    <h3 className="font-medium text-sm">{k.label}</h3>
                                    <p className="text-xs text-slate-500 font-mono">{k.source}</p>
                                </div>
                                <span className="text-xs text-blue-500 font-medium">Pakai alamat ini</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Daftar Kamera Terhubung */}
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
                <div className="p-4 border-b border-slate-200 dark:border-slate-800 font-semibold text-sm flex items-center gap-2">
                    <Video className="w-4 h-4 text-blue-500" /> Daftar Kamera Aktif
                </div>
                <div className="divide-y divide-slate-200 dark:divide-slate-800">
                    {cameras.length === 0 && (
                        <div className="p-8 text-center text-sm text-slate-500">
                            Belum ada kamera terdaftar. Tambahkan lewat form di atas, atau tekan Pindai
                            untuk mencari kamera di jaringan.
                        </div>
                    )}
                    {cameras.map((cam) => (
                        <div key={cam.camera_id} className="p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-500">
                                    <Camera className="w-5 h-5" />
                                </div>
                                <div>
                                    <h3 className="font-medium text-sm">{cam.name}</h3>
                                    <p className="text-xs text-slate-500 font-mono">{cam.source}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-4">
                                <select
                                    value={cam.rotate}
                                    onChange={(e) => ubahRotasi(cam.camera_id, e.target.value)}
                                    title="Putar gambar searah jarum jam"
                                    className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-blue-500"
                                >
                                    {ROTASI.map((d) => <option key={d} value={d}>{d}&deg;</option>)}
                                </select>
                                {cam.is_active ? (
                                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                                        <CheckCircle2 className="w-3.5 h-3.5" /> Terhubung
                                    </span>
                                ) : (
                                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-500/10 text-red-500 border border-red-500/20">
                                        <AlertCircle className="w-3.5 h-3.5" /> Terputus
                                    </span>
                                )}
                                <button onClick={() => handleDelete(cam.camera_id)} className="text-slate-400 hover:text-red-500 transition-colors p-2">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
