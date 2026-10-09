#!/usr/bin/env python
"""
Bangun halaman HTML beranimasi dari kedua flowchart Excalidraw proyek ini.

    python tools/flowanim/build.py            # tulis kedua halaman HTML
    python tools/flowanim/build.py --list      # cek skala kamera tiap bab saja

Hasilnya: build/flowanim/<nama>.html -- satu berkas mandiri yang bisa dibuka
langsung di browser untuk ditonton, dan juga dipakai `capture.mjs` untuk
mengambil frame satu per satu lalu dirangkai jadi GIF.

CARA KERJA ANIMASINYA
---------------------
Diagramnya lebar (4500-4900 px), jadi tidak mungkin seluruh kanvas dimuat ke
GIF selebar README -- teksnya jadi tidak terbaca. Pendekatannya: BAB.
Tiap bab memarkir kamera di satu area (diam, tidak nge-pan) lalu menyalakan
node di area itu satu per satu. Kamera yang diam itu disengaja: mayoritas piksel
tidak berubah antar frame, sehingga kompresi antar-frame GIF bekerja dan
berkasnya tetap kecil. Pan/zoom halus akan mengubah semua piksel tiap frame
dan membuat GIF-nya membengkak.

Kamera tiap bab DIHITUNG dari kotak pembatas elemen-elemen bab itu, bukan
ditulis manual, supaya tidak pernah meleset kalau diagramnya digeser.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from render import Diagram, bbox_of, load, render_svg

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC_DIR = REPO / "docs" / "flow"
OUT_DIR = REPO / "build" / "flowanim"

VIEW_W, VIEW_H = 1280, 720
CAPTION_H = 96
STAGE_W, STAGE_H = VIEW_W, VIEW_H - CAPTION_H

CAMERA_PAD = 48
MIN_SCALE, MAX_SCALE = 0.55, 1.25
WARN_SCALE = 0.62

# Waktu (milidetik). Satu langkah = panah digambar, lalu node muncul, lalu jeda baca.
ARROW_MS = 330
ARROW_LEAD = 240          # node muncul setelah panahnya hampir selesai
NODE_MS = 220
STEP_MS = 620             # jarak antar langkah
CHAPTER_OUTRO_MS = 520    # jeda sebelum pindah ke bab berikutnya

# Kamera. Alurnya dibuka dengan tampilan utuh, lalu merayap masuk ke bab 1 dan
# BERGESER dari bab ke bab -- bukan memotong. Potongan keras bikin mata
# kehilangan jejak posisi, karena tiap bab berada di bagian kanvas yang
# berbeda dan tidak ada petunjuk ke mana perpindahannya.
OVERVIEW_MS = 2200        # tampilan utuh ditahan di awal
INTRO_MS = 1500           # tampilan utuh -> bab 1
TRANS_MS = 950            # bab -> bab berikutnya
OVERVIEW_PAD = 70


def step(ids, note, hold=None):
    return {"ids": list(ids), "note": note, "hold": hold}


# --------------------------------------------------------------------------
# BAB: flowchart sistem deteksi jatuh.
# Ini state machine bertimer, jadi babnya disusun sebagai SIMULASI jalannya
# sistem -- bukan sekadar memunculkan node berurutan.
# --------------------------------------------------------------------------
SPEC_SISTEM = {
    "src": "flowchart-sistem.excalidraw",
    "out": "flow-detection",
    "title": "Alur sistem deteksi jatuh",
    "chapters": [
        {
            "title": "Mata sistem: dari ruangan ke satu frame",
            "steps": [
                step(["el0010"], "Lansia berada di ruangan, terpantau kamera"),
                step(["el0012"], "Webcam / IP Webcam / Iriun mengalirkan video"),
                step(["el0014"], "Backend mengambil 1 frame terbaru dari aliran"),
                step(["el0018"], "Frame berhasil dibaca?", 820),
            ],
        },
        {
            "title": "Kamera mati pun siklusnya tetap jalan",
            "steps": [
                step(["el0018"], "Frame berhasil dibaca?"),
                step(["el0056", "el0060"], "tidak → kamera ditandai OFFLINE di dashboard"),
                step(["el0016"], "Penghubung A memutar siklus kembali ke ambil frame", 820),
                step(["el0020"], "ya → model YOLO11 memindai frame"),
                step(["el0022"], "Ada objek 'orang' terdeteksi?", 820),
            ],
        },
        {
            "title": "Yakin ini jatuh?",
            "steps": [
                step(["el0024"], "Keyakinan deteksi >= ambang 0,5?", 760),
                step(["el0077"], "tidak → RAGU-RAGU: timer ditahan, tidak direset"),
                step(["el0026"], "ya → ambil kotak tubuh + kelas postur"),
                step(["el0028"], "Postur termasuk kelas pemicu?", 820),
                step(["el0030"], "YA → TIMER JATUH mulai berjalan"),
                step(["el0032"], "Sudah bertahan >= 2 detik?", 760),
            ],
        },
        {
            "title": "Dugaan menjadi terkonfirmasi",
            "steps": [
                step(["el0034"], "ya → DUGAAN JATUH, dashboard berubah kuning"),
                step(["el0036"], "Masih tergeletak >= 10 detik?", 820),
                step(["el0108"], "tidak → kembali memantau lewat penghubung A"),
                step(
                    ["simRect01", "el0028"],
                    "Tombol SIMULASI memaksa jawaban YA — khusus demo, model tetap jalan",
                    900,
                ),
            ],
        },
        {
            "title": "Alarm: cegah dulu alarm beruntun",
            "steps": [
                step(["el0112"], "Status naik ke JATUH TERKONFIRMASI", 760),
                step(["el0116"], "Baru saja kirim alarm untuk kamera ini?", 820),
                step(["el0146", "el0150"], "ya → abaikan, alarm kejadian ini sudah dikirim"),
                step(["el0118"], "tidak → lanjut ke urutan pengiriman alarm"),
            ],
        },
        {
            "title": "Urutan 1-2-3 yang disengaja",
            "steps": [
                step(["el0118"], "1. Database dulu — supaya alert tidak pernah hilang", 900),
                step(["el0120"], "2. Dashboard — perawat mungkin sedang menatap layar", 900),
                step(["el0122"], "3. Telegram terakhir — paling lambat, dicoba ulang 3x", 980),
            ],
        },
        {
            "title": "Kalau Telegram gagal, alert tetap sah",
            "steps": [
                step(["el0124"], "Telegram terkirim? dicoba ulang sampai 3x", 820),
                step(["el0153"], "tidak → kegagalan dicatat, alert tetap tampil"),
                step(["el0126"], "ya → mulai jeda 60 detik", 760),
            ],
        },
        {
            "title": "Sampai perawat menolong",
            "steps": [
                step(["el0128"], "Perawat menekan tombol 'Sudah ditangani'?", 820),
                step(["el0158", "el0162"], "tidak → alarm TETAP AKTIF dan tetap tercatat"),
                step(["el0130"], "ya → kembali ke MONITORING"),
                step(["el0132"], "SELESAI — perawat menolong lansia", 900),
            ],
        },
        {
            "title": "Tahan banting: orang hilang sementara",
            "steps": [
                step(["el0022"], "Kembali ke percabangan: ada objek 'orang'?", 760),
                step(["el0063"], "tidak → orang hilang, mungkin tertutup selimut / kursi"),
                step(["el0067"], "Hilang lebih dari 3 detik?", 820),
                step(["el0070", "el0074"], "ya → dianggap keluar ruangan, timer direset"),
                step(["el0030"], "tidak → TIMER JATUH tetap jalan, jeda tak dihitung", 900),
            ],
        },
        {
            "title": "Tahan banting: salah deteksi 1-2 frame",
            "camera_extra": ["tx0103"],
            "steps": [
                step(["el0028"], "Postur bukan kelas pemicu?", 760),
                step(["el0081"], "TIDAK → tambah penghitung frame bukan-jatuh"),
                step(["el0085"], "Sudah 5 frame berturut-turut?", 820),
                step(["el0095", "el0030"], "tidak → cuma 1-2 frame meleset, TIMER TETAP JALAN"),
                step(["el0088", "el0092"], "ya → orang benar-benar bangkit, timer direset → AMAN", 900),
            ],
        },
    ],
}


# --------------------------------------------------------------------------
# BAB: flowchart endpoint API.
# Ini peta acuan, bukan alur runtime -- jadi babnya mengikuti 6 fase
# pemakaian dashboard dari kiri ke kanan.
# --------------------------------------------------------------------------
SPEC_API = {
    "src": "flowchart-api.excalidraw",
    "out": "flow-api",
    "title": "Alur endpoint API",
    "chapters": [
        {
            "title": "Fase 1 - dashboard dibuka",
            "steps": [
                step(["n003"], "Perawat membuka dashboard"),
                step(["n005"], "Halaman utama dimuat"),
                step(["n018"], "GET / — cek backend hidup, alamat dari src/config.js", 900),
            ],
        },
        {
            "title": "Fase 2 - kelola kamera: yang dibaca",
            "steps": [
                step(["n006"], "Halaman Kelola Kamera"),
                step(["n020"], "GET /api/cameras/ — daftar kamera + status terakhir", 820),
                step(["n022"], "GET /api/cameras/devices — kamera yang menancap di laptop", 820),
                step(["n024"], "POST /api/cameras/scan — pindai subnet, cari HP yang menyiarkan", 820),
                step(["n026"], "POST /api/cameras/ — daftarkan kamera baru", 760),
            ],
        },
        {
            "title": "Fase 2 - kelola kamera: validasi dan ubah",
            "steps": [
                step(["n028"], "Lolos semua pemeriksaan?", 820),
                step(["n030"], "TIDAK → 409 / 400 dengan alasan yang jelas", 900),
                step(["n033"], "YA → 201, capture langsung dinyalakan camera_manager"),
                step(["n036"], "PATCH /{id} — inilah jalur saat kamera pindah WiFi", 820),
                step(["n038"], "DELETE /{id} — capture dimatikan lalu data dihapus", 820),
            ],
        },
        {
            "title": "Fase 3 - simulasi live",
            "steps": [
                step(["n007"], "Halaman Simulasi Live"),
                step(["n040"], "GET /api/cameras/ — mengisi dropdown pilihan kamera"),
                step(["n042"], "GET /{id}/stream — MJPEG, satu respons yang tak pernah selesai", 900),
                step(["n044"], "WS /ws — dibiarkan diam, alert didorong backend tanpa polling", 900),
            ],
        },
        {
            "title": "Fase 4 - pemicu diterima",
            "steps": [
                step(["n008"], "Jatuh terdeteksi"),
                step(["n046"], "POST /{id}/simulate-fall — paksa postur pemicu beberapa detik", 900),
                step(["n048"], "Pipeline + state machine menaikkan status ke CONFIRMED_FALL", 900),
            ],
        },
        {
            "title": "Fase 4 - tiga langkah di dalam backend",
            "camera_extra": ["L056"],
            "steps": [
                step(["n050"], "1. SIMPAN ke database — ditandai bila dari simulasi", 820),
                step(["n052"], "2. DORONG lewat /ws — banner muncul tanpa polling", 820),
                step(["n054"], "3. KIRIM Telegram — dicoba ulang sampai 3x", 900),
            ],
        },
        {
            "title": "Fase 5 - riwayat insiden",
            "steps": [
                step(["n009"], "Halaman Riwayat Insiden"),
                step(["n057"], "GET /api/alerts/ — parameter skip, limit, acknowledged", 820),
                step(["n059"], "GET /api/alerts/count — jumlah total, bisa disaring"),
                step(["n061"], "GET /api/alerts/{id} — 404 kalau tidak ada"),
                step(["n063"], "PUT /{id}/ack — tandai sudah ditangani perawat", 900),
            ],
        },
        {
            "title": "Fase 6 - pengaturan",
            "steps": [
                step(["n010"], "Halaman Pengaturan"),
                step(["n065"], "GET /api/settings/ — ambang aktif + sumber kamera bawaan", 820),
                step(["n067"], "PUT /settings/threshold — berlaku di memori, tidak menulis .env", 900),
                step(["n069"], "POST /settings/test-telegram — kegagalan ketahuan saat menyiapkan", 900),
            ],
        },
        {
            "title": "Dashboard siap dipakai",
            "steps": [
                step(["n010"], "Enam fase selesai dilalui"),
                step(["n004"], "SELESAI — dashboard siap dipakai perawat", 1100),
            ],
        },
    ],
}


# --------------------------------------------------------------------------


def build_timeline(d: Diagram, spec: dict, fps: int) -> dict:
    """Ubah daftar bab menjadi kejadian ber-cap waktu yang bisa dihitung ulang
    dari nomor frame mana pun. Tidak ada rAF, tidak ada transisi CSS -- supaya
    frame ke-N selalu identik setiap kali dijalankan."""
    chapters = []
    t = OVERVIEW_MS + INTRO_MS      # bab 1 baru mulai setelah pembuka
    warnings = []

    # Panah mana saja yang menyentuh sebuah node.
    touching: dict = {}
    for aid, (s, e) in d.arrow_ends.items():
        for end in (s, e):
            if end:
                touching.setdefault(end, []).append(aid)

    for ci, ch in enumerate(spec["chapters"]):
        if ci > 0:
            t += TRANS_MS           # ruang untuk geser kamera ke bab ini
        t0 = t
        active: set = set()
        events = []
        notes = []

        for st in ch["steps"]:
            new_ids = [i for i in st["ids"] if i not in active]
            notes.append({"t": t, "text": st["note"]})

            # Panah yang kedua ujungnya sudah/sedang hidup ikut digambar.
            target = active | set(st["ids"])
            drawn = []
            for nid in st["ids"]:
                for aid in touching.get(nid, []):
                    if aid in active:
                        continue
                    s, e = d.arrow_ends[aid]
                    if s in target and e in target:
                        drawn.append(aid)
            for aid in dict.fromkeys(drawn):
                events.append({"id": aid, "t": t, "dur": ARROW_MS, "kind": "arrow"})
                active.add(aid)

            for nid in new_ids:
                events.append(
                    {"id": nid, "t": t + ARROW_LEAD, "dur": NODE_MS, "kind": "node"}
                )
                active.add(nid)

            t += st["hold"] or STEP_MS

        t += CHAPTER_OUTRO_MS

        cam_ids = set(ch.get("camera_extra", []))
        for st in ch["steps"]:
            cam_ids.update(st["ids"])
        box = bbox_of(d, cam_ids).pad(CAMERA_PAD)
        raw_scale = min(STAGE_W / box.w, STAGE_H / box.h)
        scale = max(MIN_SCALE, min(MAX_SCALE, raw_scale))
        if scale < WARN_SCALE:
            warnings.append(
                f"  bab {ci + 1} '{ch['title']}': skala {scale:.2f} "
                f"({box.w:.0f}x{box.h:.0f}) -- teks mungkin terlalu kecil"
            )

        chapters.append(
            {
                "title": ch["title"],
                "index": ci + 1,
                "t0": t0,
                "t1": t,
                "scale": round(scale, 4),
                # Pusat dalam koordinat gambar, bukan translate jadi: kamera
                # perlu di-interpolasi antar bab, dan menggeser titik tengah
                # jauh lebih masuk akal daripada menggeser hasil translate-nya.
                "cx": round(box.cx, 2),
                "cy": round(box.cy, 2),
                "events": events,
                "notes": notes,
            }
        )

    semua = [e["id"] for e in d.elements if not e.get("isDeleted")]
    ov = bbox_of(d, semua).pad(OVERVIEW_PAD)
    # Sengaja TIDAK dibatasi MIN_SCALE: tampilan pembuka memang harus memuat
    # seluruh kanvas, dan di sini teks belum perlu terbaca.
    ov_scale = min(STAGE_W / ov.w, STAGE_H / ov.h)

    frames = int(round(t / 1000 * fps))
    return {
        "fps": fps,
        "stageW": STAGE_W,
        "stageH": STAGE_H,
        "overview": {
            "scale": round(ov_scale, 4),
            "cx": round(ov.cx, 2),
            "cy": round(ov.cy, 2),
            "t1": OVERVIEW_MS,
        },
        "overviewNote": spec.get(
            "overviewNote",
            "Seluruh alur dalam satu layar — berikutnya ditelusuri bab demi bab.",
        ),
        "durationMs": t,
        "frames": frames,
        "title": spec["title"],
        "nChapters": len(chapters),
        "chapters": chapters,
        "statics": d.statics,
        "_warnings": warnings,
    }


HTML = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root {
    --bg: #ffffff;
    --ink: #1e1e1e;
    --muted: #6b7280;
    --rule: #e5e7eb;
    --accent: #1971c2;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #f3f4f6; }
  #frame {
    width: __VW__px; height: __VH__px;
    background: var(--bg);
    position: relative; overflow: hidden;
    font-family: __FONT__;
  }
  #stage { display: block; background: var(--bg); }
  #caption {
    position: absolute; left: 0; right: 0; bottom: 0; height: __CAPH__px;
    border-top: 1px solid var(--rule);
    padding: 14px 28px 0;
    background: var(--bg);
  }
  /* Node yang kebetulan jatuh di tepi bawah tidak terpotong mendadak. */
  #fade {
    position: absolute; left: 0; right: 0; bottom: __CAPH__px; height: 56px;
    background: linear-gradient(to bottom, rgba(255,255,255,0), var(--bg));
    pointer-events: none;
  }
  #crumb {
    font-size: 13px; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: var(--accent);
    margin-bottom: 6px;
  }
  #note { font-size: 19px; color: var(--ink); line-height: 1.35; }
  #bar { position: absolute; left: 0; bottom: 0; height: 4px; background: var(--accent); width: 0; }
  #watermark {
    position: absolute; right: 24px; top: 18px;
    font-size: 12px; color: var(--muted); letter-spacing: .04em;
  }
  /* Keadaan dasar: semua elemen diredam supaya rangka diagram tetap terbaca. */
  .el { transform-box: fill-box; transform-origin: center; }
  .halo { opacity: 0; }
  .node-label, .free-text, .edge-label { font-weight: 500; }
  .edge-label { font-weight: 700; }
</style>
</head>
<body>
<div id="frame">
  __SVG__
  <div id="fade"></div>
  <div id="watermark">__TITLE__</div>
  <div id="caption">
    <div id="crumb"></div>
    <div id="note"></div>
    <div id="bar"></div>
  </div>
</div>
<script>
const TL = __TIMELINE__;
const OFF = 0.15;          // opasitas elemen yang belum aktif
const STATIC_OP = 0.78;    // judul & catatan pinggir: selalu terlihat
const HALO_MS = 900;

const cam = document.getElementById('cam');
const crumb = document.getElementById('crumb');
const noteEl = document.getElementById('note');
const bar = document.getElementById('bar');

const groups = new Map();
for (const g of document.querySelectorAll('#cam > g[data-id]')) {
  groups.set(g.dataset.id, {
    g,
    kind: g.dataset.kind,
    baseOp: parseFloat(g.dataset.baseOp || '1'),
    len: parseFloat(g.dataset.len || '0'),
    dashed: g.dataset.dashed === '1',
    halo: g.querySelector('.halo'),
    ghost: g.querySelector('.ghost'),
    line: g.querySelector('.line'),
    head: g.querySelector('.head'),
    lbl: g.querySelector('.lbl'),
  });
}
const statics = new Set(TL.statics);

function easeOutCubic(p) { return 1 - Math.pow(1 - p, 3); }

function reset() {
  for (const [id, o] of groups) {
    if (o.kind === 'static' || statics.has(id)) {
      o.g.style.opacity = o.baseOp * STATIC_OP;
      continue;
    }
    if (o.kind === 'arrow') {
      // Grupnya tetap penuh; tiap lapis yang mengatur keadaannya sendiri.
      o.g.style.opacity = o.baseOp;
      o.ghost.style.opacity = OFF;
      o.line.style.opacity = 0;
      o.head.style.opacity = 0;
      if (o.lbl) o.lbl.style.opacity = OFF;
      if (!o.dashed && o.len) {
        o.line.style.strokeDasharray = o.len;
        o.line.style.strokeDashoffset = o.len;
      }
      continue;
    }
    o.g.style.opacity = o.baseOp * OFF;
    o.g.style.transform = '';
    if (o.halo) o.halo.style.opacity = 0;
  }
}

const STAGE_W = TL.stageW, STAGE_H = TL.stageH;

// Mulai dan berhenti sama-sama pelan. Ease kubik saja masih terasa "direm
// mendadak" di akhir geseran sepanjang kanvas ini.
function smoother(p) { return p * p * p * (p * (6 * p - 15) + 10); }

function applyCam(c) {
  const tx = STAGE_W / 2 - c.scale * c.cx;
  const ty = STAGE_H / 2 - c.scale * c.cy;
  cam.setAttribute('transform',
    `translate(${tx.toFixed(2)} ${ty.toFixed(2)}) scale(${c.scale.toFixed(5)})`);
}

// Skala di-interpolasi secara GEOMETRIS, bukan linear. Dengan linear, zoom
// dari 0,26 ke 1,0 terasa melesat di awal lalu merayap di akhir; dengan
// geometris, kecepatan perbesarannya terasa rata.
function camBetween(a, b, p) {
  return {
    scale: a.scale * Math.pow(b.scale / a.scale, p),
    cx: a.cx + (b.cx - a.cx) * p,
    cy: a.cy + (b.cy - a.cy) * p,
  };
}

// Seluruh diagram tampil penuh. `fade` 0 = penuh, 1 = persis keadaan awal bab
// (semuanya redup). Nilai di antaranya dipakai saat zoom pembuka, sehingga
// gambar utuh LARUT menjadi kanvas kosong yang siap digambar bab 1 -- bukan
// ditukar mendadak di satu frame.
function showAll(fade) {
  const f = fade || 0;
  const vis = 1 - f;
  for (const [id, o] of groups) {
    if (o.kind === 'static' || statics.has(id)) {
      o.g.style.opacity = o.baseOp * STATIC_OP;
      continue;
    }
    if (o.kind === 'arrow') {
      o.g.style.opacity = o.baseOp;
      o.ghost.style.opacity = OFF;
      o.line.style.opacity = o.dashed ? vis : 1;
      if (!o.dashed && o.len) o.line.style.strokeDashoffset = o.len * f;
      o.head.style.opacity = vis;
      if (o.lbl) o.lbl.style.opacity = OFF + (1 - OFF) * vis;
      continue;
    }
    o.g.style.opacity = o.baseOp * (OFF + (1 - OFF) * vis);
    o.g.style.transform = '';
    if (o.halo) o.halo.style.opacity = 0;
  }
}

function applyChapter(ch, t) {
  reset();
  for (const ev of ch.events) {
    if (t < ev.t) continue;
    const o = groups.get(ev.id);
    if (!o) continue;
    const p = easeOutCubic(Math.min(1, (t - ev.t) / ev.dur));
    const age = t - ev.t;

    if (ev.kind === 'arrow') {
      if (o.dashed) {
        o.line.style.opacity = p;            // panah putus-putus: cukup difade
      } else {
        o.line.style.opacity = 1;
        o.line.style.strokeDashoffset = o.len * (1 - p);
      }
      // Kepala panah menyusul setelah garisnya hampir sampai.
      o.head.style.opacity = Math.max(0, Math.min(1, (p - 0.72) / 0.28));
      if (o.lbl) o.lbl.style.opacity = OFF + (1 - OFF) * p;
    } else {
      o.g.style.opacity = o.baseOp * (OFF + (1 - OFF) * p);
      o.g.style.transform = `scale(${(0.972 + 0.028 * p).toFixed(4)})`;
      if (o.halo) o.halo.style.opacity = 0.4 * Math.max(0, 1 - age / HALO_MS);
    }
  }
}

function noteAt(ch, t) {
  let note = ch.notes.length ? ch.notes[0].text : '';
  for (const nt of ch.notes) if (t >= nt.t) note = nt.text;
  return note;
}

// Di mana posisi waktu t: pembuka, sedang bergeser antar bab, atau di dalam bab.
function locate(t) {
  if (t < TL.overview.t1) return { mode: 'ov' };
  const first = TL.chapters[0];
  if (t < first.t0) {
    return { mode: 'tr', prev: null, next: 0,
             from: TL.overview, to: first,
             p: (t - TL.overview.t1) / (first.t0 - TL.overview.t1) };
  }
  for (let i = 0; i < TL.chapters.length; i++) {
    const c = TL.chapters[i];
    if (t < c.t1) return { mode: 'ch', i };
    const nx = TL.chapters[i + 1];
    if (nx && t < nx.t0) {
      return { mode: 'tr', prev: i, next: i + 1, from: c, to: nx,
               p: (t - c.t1) / (nx.t0 - c.t1) };
    }
  }
  return { mode: 'ch', i: TL.chapters.length - 1 };
}

function setFrame(n) {
  const t = (n * 1000) / TL.fps;
  const L = locate(t);

  if (L.mode === 'ov') {
    applyCam(TL.overview);
    showAll();
    crumb.textContent = TL.title;
    noteEl.textContent = TL.overviewNote;
  } else if (L.mode === 'tr') {
    applyCam(camBetween(L.from, L.to, smoother(Math.max(0, Math.min(1, L.p)))));
    // Isi layar ditukar di TENGAH geseran, bukan di ujungnya: saat itu kamera
    // sedang bergerak paling kencang, jadi pergantian keadaan nyaris tidak
    // terlihat. Kalau ditukar di awal atau akhir, ia tampak sebagai kedipan.
    if (L.prev === null) {
      // Pembuka: isi gambar melebur sepanjang zoom, jadi tidak ada titik tukar.
      showAll(smoother(Math.max(0, Math.min(1, L.p))));
      const c = TL.chapters[0];
      const masuk = L.p >= 0.5;
      crumb.textContent = masuk
        ? `Bab ${c.index}/${TL.nChapters} · ${c.title}`
        : TL.title;
      noteEl.textContent = masuk ? noteAt(c, -1) : TL.overviewNote;
    } else if (L.p < 0.5) {
      {
        const c = TL.chapters[L.prev];
        applyChapter(c, c.t1);
        crumb.textContent = `Bab ${c.index}/${TL.nChapters} \u00b7 ${c.title}`;
        noteEl.textContent = noteAt(c, c.t1);
      }
    } else {
      const c = TL.chapters[L.next];
      applyChapter(c, c.t0 - 1);        // keadaan awal bab: belum ada yang menyala
      crumb.textContent = `Bab ${c.index}/${TL.nChapters} \u00b7 ${c.title}`;
      noteEl.textContent = noteAt(c, -1);
    }
  } else {
    const c = TL.chapters[L.i];
    applyCam(c);
    applyChapter(c, t);
    crumb.textContent = `Bab ${c.index}/${TL.nChapters} \u00b7 ${c.title}`;
    noteEl.textContent = noteAt(c, t);
  }

  bar.style.width = (100 * Math.min(1, t / TL.durationMs)).toFixed(2) + '%';
}

window.__setFrame = setFrame;
window.__frames = TL.frames;
window.__fps = TL.fps;

setFrame(0);

// Autoplay hanya untuk ditonton manusia; saat capture frame di-set satu per satu.
if (!location.search.includes('capture')) {
  const t0 = performance.now();
  (function tick() {
    const el = performance.now() - t0;
    setFrame(Math.floor((el / 1000) * TL.fps) % (TL.frames + 1));
    requestAnimationFrame(tick);
  })();
}
</script>
</body>
</html>
"""


def build_one(spec: dict, fps: int, list_only: bool) -> dict:
    src = SRC_DIR / spec["src"]
    d = load(src)
    tl = build_timeline(d, spec, fps)

    print(f"\n{spec['out']}  ({spec['src']})")
    print(f"  bab      : {tl['nChapters']}")
    print(f"  durasi   : {tl['durationMs'] / 1000:.1f} s")
    print(f"  frame    : {tl['frames']} @ {fps} fps")
    print("  skala    : " + ", ".join(f"{c['scale']:.2f}" for c in tl["chapters"]))
    for w in tl["_warnings"]:
        print("  PERINGATAN:\n" + w)

    if list_only:
        return tl

    svg = render_svg(d, STAGE_W, STAGE_H)
    payload = {k: v for k, v in tl.items() if not k.startswith("_")}
    html = (
        HTML.replace("__TITLE__", spec["title"])
        .replace("__VW__", str(VIEW_W))
        .replace("__VH__", str(VIEW_H))
        .replace("__CAPH__", str(CAPTION_H))
        .replace("__FONT__", "'Segoe UI', 'Inter', system-ui, sans-serif")
        .replace("__SVG__", svg)
        .replace("__TIMELINE__", json.dumps(payload, ensure_ascii=False))
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{spec['out']}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  -> {out.relative_to(REPO)}  ({len(html) / 1024:.0f} KB)")

    (OUT_DIR / f"{spec['out']}.json").write_text(
        json.dumps(
            {"frames": tl["frames"], "fps": fps, "out": spec["out"], "width": VIEW_W, "height": VIEW_H},
            indent=2,
        ),
        encoding="utf-8",
    )
    return tl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--list", action="store_true", help="hitung skala kamera saja")
    ap.add_argument("--only", choices=["detection", "api"], help="bangun satu saja")
    args = ap.parse_args()

    specs = {"detection": SPEC_SISTEM, "api": SPEC_API}
    chosen = [specs[args.only]] if args.only else [SPEC_SISTEM, SPEC_API]
    for s in chosen:
        build_one(s, args.fps, args.list)


if __name__ == "__main__":
    main()
