import { AlertCircle, CheckCircle2, FlaskConical, Footprints, Loader2, Send, SendHorizonal, TriangleAlert } from 'lucide-react';
import { labelAlasan, labelPutusan } from '../putusan';
import { durasiTeks, selisihDetik } from '../waktu';

// Aturan warna tunggal: merah hanya untuk alarm yang belum direspons, amber untuk
// yang sudah ada yang menuju lokasi, biru untuk latihan, abu-abu untuk keterangan
// dan hal teknis, hijau hanya untuk tanda selesai.
const CHIP = 'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium whitespace-nowrap';

/** Status penanganan: belum direspons, menuju lokasi, atau ditangani. */
export function StatusPenanganan({ alert }) {
    if (!alert.acknowledged && !alert.claimed_by) {
        return (
            <span className={`${CHIP} bg-red-600 text-white font-semibold`}>
                <TriangleAlert className="w-3.5 h-3.5" aria-hidden="true" /> Belum direspons
            </span>
        );
    }
    if (!alert.acknowledged) {
        return (
            <span className={`${CHIP} bg-amber-400 text-slate-950 font-semibold max-w-full`}>
                <Footprints className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{alert.claimed_by} menuju lokasi</span>
            </span>
        );
    }
    if (alert.terlewat) {
        return (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700 dark:text-slate-300">
                <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
                Dicatat manual{alert.acknowledged_by ? ` oleh ${alert.acknowledged_by}` : ''}
            </span>
        );
    }
    const respons = selisihDetik(alert.created_at, alert.claimed_at || alert.acknowledged_at);
    return (
        <span className="inline-flex flex-col text-xs">
            <span className="inline-flex items-center gap-1.5 font-medium text-slate-800 dark:text-slate-200">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
                Ditangani{alert.acknowledged_by ? ` ${alert.acknowledged_by}` : ''}
            </span>
            {respons !== null && (
                <span className="text-slate-500 tabular-nums pl-5">
                    {alert.claimed_at ? 'Direspons' : 'Ditutup'} dalam {durasiTeks(respons)}
                </span>
            )}
        </span>
    );
}

/** Putusan: jatuh sungguhan, alarm palsu (dengan alasan), belum yakin, atau belum dinilai. */
export function StatusPutusan({ alert }) {
    if (alert.simulated) {
        return (
            <span className={`${CHIP} bg-blue-600 text-white`}>
                <FlaskConical className="w-3.5 h-3.5" aria-hidden="true" /> Latihan
            </span>
        );
    }
    if (!alert.verdict) {
        return (
            <span className={`${CHIP} border border-dashed border-slate-400 dark:border-slate-500 text-slate-600 dark:text-slate-300`}>
                Belum dinilai
            </span>
        );
    }
    if (alert.verdict === 'jatuh') {
        return <span className={`${CHIP} bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 font-semibold`}>{labelPutusan('jatuh')}</span>;
    }
    if (alert.verdict === 'palsu') {
        return (
            <span className="inline-flex flex-col text-xs">
                <span className={`${CHIP} self-start border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200`}>
                    {labelPutusan('palsu')}
                </span>
                <span className="text-slate-500 mt-0.5">{labelAlasan(alert.verdict_reason)}</span>
            </span>
        );
    }
    return (
        <span className={`${CHIP} border border-dashed border-slate-400 dark:border-slate-500 text-slate-700 dark:text-slate-200`}>
            {labelPutusan(alert.verdict)}
        </span>
    );
}

/** Status pesan Telegram insiden ini. Alert lama tanpa kolom status memakai `notified`. */
export function StatusTelegram({ alert }) {
    const s = alert.telegram_status || (alert.notified ? 'terkirim' : null);
    const teks = 'inline-flex items-center gap-1.5 text-xs';
    if (alert.terlewat) return <span className={`${teks} text-slate-500`}>Tanpa pesan (dicatat manual)</span>;
    if (s === 'terkirim') return <span className={`${teks} text-slate-600 dark:text-slate-300`}><Send className="w-3.5 h-3.5" aria-hidden="true" /> Terkirim</span>;
    if (s === 'mengirim') return <span className={`${teks} text-slate-600 dark:text-slate-300`}><Loader2 className="w-3.5 h-3.5 motion-safe:animate-spin" aria-hidden="true" /> Mengirim</span>;
    if (s === 'gagal') return <span className={`${teks} font-semibold text-slate-800 dark:text-slate-100`}><AlertCircle className="w-3.5 h-3.5" aria-hidden="true" /> Gagal terkirim</span>;
    if (s === 'mati') return <span className={`${teks} text-slate-500`}><SendHorizonal className="w-3.5 h-3.5" aria-hidden="true" /> Telegram belum diatur</span>;
    if (s === 'dilewati') return <span className={`${teks} text-slate-500`}><SendHorizonal className="w-3.5 h-3.5" aria-hidden="true" /> Tidak dikirim (latihan)</span>;
    return <span className={`${teks} text-slate-500`}><SendHorizonal className="w-3.5 h-3.5" aria-hidden="true" /> Tidak terkirim</span>;
}
