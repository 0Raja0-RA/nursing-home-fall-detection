#!/usr/bin/env python3
"""
box_audit.py  ->  ml/scripts/box_audit.py
=========================================
Audit manual kotak otomatis pada dataset training final (ml/data/processed_final).

Dua perintah:
  sample  : ambil sampel audit (seed tetap) -> sample.csv + audit.html (halaman penilaian lokal)
  report  : gabungkan hasil penilaian (CSV ekspor dari audit.html) -> tingkat error per strata

Rancangan sampel (opsi "ringan", disetujui 2026-10-30):
  lying val, lying test      : SEMUA (sensus)
  lying train                : 100 acak
  normal / transitional      : 50 acak per kelas x sumber (mcf, urfall), semua split
  mencurigakan               : 50 kotak dari aturan (menempel tepi, terkecil per sumber, bentuk ekstrem)
  kalibrasi                  : 30 acak di luar sampel, dinilai paling awal, TIDAK ikut dihitung

Rubrik (satu nilai per kotak; berat = setara IoU < 0,5 dengan kotak yang benar):
  1 OK | 2 kurang pas (ringan) | 3 terpotong berat: < separuh tubuh | 4 terlalu besar (> ~2x luas tubuh)
  atau salah objek | 5 kelas salah | 6 ambigu (tidak bisa dinilai; dikeluarkan dari penyebut)

Aturan keputusan (ditetapkan sebelum audit): error berat lying <= 5%.
  strata sensus -> tingkat error apa adanya; strata acak -> batas atas Wilson 95%.

Contoh (dari root repo):
  py ml/scripts/box_audit.py sample
  py ml/scripts/box_audit.py report --hasil ml/data/box_audit/hasil_audit.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
from pathlib import Path

from PIL import Image

NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}
SPLITS = ("train", "val", "test")
RATINGS = {1: "ok", 2: "kurang_pas", 3: "terpotong_berat", 4: "terlalu_besar_salah_objek",
           5: "kelas_salah", 6: "ambigu"}
MAJOR = {3, 4, 5}
LIMIT = 0.05


def load_frames(dataset: Path, meta_csv: Path) -> list[dict]:
    meta = {}
    with open(meta_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            meta[r["stem"]] = r
    rows = []
    for split in SPLITS:
        for lf in sorted((dataset / "labels" / split).glob("*.txt")):
            parts = lf.read_text(encoding="utf-8").split()
            assert len(parts) == 5, f"{lf}: harus tepat satu kotak"
            m = meta[lf.stem]
            with Image.open(dataset / "images" / split / f"{lf.stem}.jpg") as im:
                W, H = im.size
            xc, yc, w, h = map(float, parts[1:])
            rows.append(dict(stem=lf.stem, split=split, cls=int(parts[0]), group=m["group"], video=m["video"],
                             cam=m["cam"], src="mcf" if m["group"] == "mcf" else "urfall",
                             xc=xc, yc=yc, w=w, h=h, W=W, H=H,
                             area_px=w * W * h * H, ar_px=(w * W) / (h * H)))
    return rows


def flags(r: dict, small_cut: dict) -> list[str]:
    out = []
    if min(r["xc"] - r["w"] / 2, r["yc"] - r["h"] / 2, 1 - r["xc"] - r["w"] / 2, 1 - r["yc"] - r["h"] / 2) <= 0.005:
        out.append("tepi")
    if r["area_px"] <= small_cut[r["src"]]:
        out.append("kecil")
    if (r["cls"] == 0 and r["ar_px"] > 1.0) or (r["cls"] == 2 and r["ar_px"] < 0.6):
        out.append("bentuk")
    return out


def cmd_sample(a):
    rows = load_frames(a.dataset, a.meta)
    rng = random.Random(a.seed)
    small_cut = {}
    for src in ("mcf", "urfall"):
        areas = sorted(r["area_px"] for r in rows if r["src"] == src)
        small_cut[src] = areas[int(len(areas) * 0.02)]
    for r in rows:
        r["flag"] = "+".join(flags(r, small_cut))

    taken, picked = set(), []

    def take(items, strata):
        for r in items:
            assert r["stem"] not in taken
            taken.add(r["stem"])
            picked.append(dict(r, strata=strata))

    def pool(cond):
        return [r for r in rows if r["stem"] not in taken and cond(r)]

    take(pool(lambda r: r["cls"] == 2 and r["split"] == "val"), "lying-val (sensus)")
    take(pool(lambda r: r["cls"] == 2 and r["split"] == "test"), "lying-test (sensus)")
    take(rng.sample(pool(lambda r: r["cls"] == 2 and r["split"] == "train"), a.n_lying_train),
         f"lying-train (acak {a.n_lying_train})")
    for c in (0, 1):
        for src in ("mcf", "urfall"):
            take(rng.sample(pool(lambda r: r["cls"] == c and r["src"] == src), a.n_other),
                 f"{NAMES[c]}-{src} (acak {a.n_other})")

    # mencurigakan: bergiliran antar aturan, masing-masing diurutkan dari yang paling ekstrem
    by_rule = {
        "kecil": sorted(pool(lambda r: "kecil" in r["flag"]), key=lambda r: r["area_px"]),
        "bentuk": sorted(pool(lambda r: "bentuk" in r["flag"]), key=lambda r: -abs(math.log(r["ar_px"]))),
        "tepi": rng.sample(t := pool(lambda r: "tepi" in r["flag"]), len(t)),
    }
    sus, seen = [], set()
    while len(sus) < a.n_suspect and any(by_rule.values()):
        for rule in by_rule:
            while by_rule[rule] and by_rule[rule][0]["stem"] in seen:
                by_rule[rule].pop(0)
            if by_rule[rule] and len(sus) < a.n_suspect:
                r = by_rule[rule].pop(0)
                seen.add(r["stem"])
                sus.append(r)
    take(sus, "mencurigakan")

    calib = []
    for c in (0, 1, 2):
        calib += rng.sample(pool(lambda r: r["cls"] == c), a.n_calib // 3)
    take(calib, "kalibrasi")

    main_items = [p for p in picked if p["strata"] != "kalibrasi"]
    calib_items = [p for p in picked if p["strata"] == "kalibrasi"]
    rng.shuffle(main_items)
    rng.shuffle(calib_items)
    ordered = calib_items + main_items

    a.out.mkdir(parents=True, exist_ok=True)
    cols = ["urutan", "stem", "split", "src", "group", "video", "cam", "kelas", "strata", "flag",
            "xc", "yc", "w", "h", "W", "H"]
    with open(a.out / "sample.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols)
        wr.writeheader()
        for i, p in enumerate(ordered, 1):
            wr.writerow({k: v for k, v in dict(p, urutan=i, kelas=NAMES[p["cls"]]).items() if k in cols})

    img_root = Path(os.path.relpath(a.dataset / "images", a.out)).as_posix()
    items = [dict(i=i, stem=p["stem"], split=p["split"], kelas=NAMES[p["cls"]], kal=p["strata"] == "kalibrasi",
                  b=[round(p["xc"], 6), round(p["yc"], 6), round(p["w"], 6), round(p["h"], 6)])
             for i, p in enumerate(ordered, 1)]
    html = (HTML.replace("__ITEMS__", json.dumps(items))
            .replace("__IMGROOT__", img_root)
            .replace("__KEY__", f"box_audit_seed{a.seed}_n{len(items)}"))
    (a.out / "audit.html").write_text(html, encoding="utf-8")

    counts = {}
    for p in ordered:
        counts[p["strata"]] = counts.get(p["strata"], 0) + 1
    print("Sampel audit:")
    for k, v in counts.items():
        print(f"  {k:<32} {v:>4}")
    print(f"  {'TOTAL':<32} {len(ordered):>4}  (dihitung: {len(main_items)}, kalibrasi: {len(calib_items)})")
    print(f"Batas 'kecil' (2% terkecil, px^2): {small_cut}")
    print(f"Ditulis: {a.out / 'sample.csv'} dan {a.out / 'audit.html'}")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - m), min(1.0, c + m)


def cmd_report(a):
    with open(a.out / "sample.csv", newline="", encoding="utf-8") as f:
        sample = {r["stem"]: r for r in csv.DictReader(f)}
    with open(a.hasil, newline="", encoding="utf-8") as f:
        res = {r["stem"]: r for r in csv.DictReader(f)}
    unknown = set(res) - set(sample)
    assert not unknown, f"stem tidak ada di sample.csv: {sorted(unknown)[:5]}"
    missing = [s for s, r in sample.items() if r["strata"] != "kalibrasi" and not res.get(s, {}).get("nilai")]
    if missing:
        print(f"[PERINGATAN] {len(missing)} kotak belum dinilai; laporan bersifat sementara.")

    strata_order = list(dict.fromkeys(r["strata"] for r in sample.values() if r["strata"] != "kalibrasi"))
    strata_order.sort(key=lambda s: (not s.startswith("lying"), s == "mencurigakan", s))
    out_rows = []
    for st in strata_order:
        vals = [int(res[s]["nilai"]) for s, r in sample.items() if r["strata"] == st and res.get(s, {}).get("nilai")]
        n_all = sum(1 for r in sample.values() if r["strata"] == st)
        n = sum(1 for v in vals if v != 6)
        k = sum(1 for v in vals if v in MAJOR)
        lo, hi = wilson(k, n)
        row = {"strata": st, "n_sampel": n_all, "n_dinilai": len(vals), "n_tanpa_ambigu": n}
        row.update({RATINGS[c]: vals.count(c) for c in RATINGS})
        row.update(error_berat=k, error_berat_pct=round(100 * k / n, 2) if n else "",
                   wilson_lo_pct=round(100 * lo, 2) if n else "", wilson_hi_pct=round(100 * hi, 2) if n else "")
        if st.startswith("lying"):
            census = "sensus" in st
            basis = k / n if n else float("nan")
            if not census:
                basis = hi
            row["keputusan"] = ("LAYAK" if basis <= LIMIT else "PERBAIKI") + \
                               (" (tingkat error sensus)" if census else " (batas atas Wilson 95%)")
        else:
            row["keputusan"] = "informasi"
        out_rows.append(row)

    with open(a.out / "ringkasan.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        wr.writeheader()
        wr.writerows(out_rows)

    print(f"{'strata':<30}{'n':>5}{'berat':>7}{'%':>7}{'Wilson 95%':>17}  keputusan")
    for r in out_rows:
        ci = f"{r['wilson_lo_pct']}-{r['wilson_hi_pct']}" if r["n_tanpa_ambigu"] else "-"
        print(f"{r['strata']:<30}{r['n_tanpa_ambigu']:>5}{r['error_berat']:>7}{str(r['error_berat_pct']):>7}"
              f"{ci:>17}  {r['keputusan']}")
    print(f"Ditulis: {a.out / 'ringkasan.csv'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit manual kotak otomatis (sampel + laporan)")
    ap.add_argument("--dataset", type=Path, default=Path("ml/data/processed_final"))
    ap.add_argument("--meta", type=Path, default=Path("ml/data/processed_v2/frames_meta.csv"))
    ap.add_argument("--out", type=Path, default=Path("ml/data/box_audit"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="ambil sampel dan buat audit.html")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--n-lying-train", type=int, default=100)
    s.add_argument("--n-other", type=int, default=50)
    s.add_argument("--n-suspect", type=int, default=50)
    s.add_argument("--n-calib", type=int, default=30)
    s.add_argument("--force", action="store_true", help="timpa sample.csv yang sudah ada")
    r = sub.add_parser("report", help="hitung tingkat error dari CSV hasil penilaian")
    r.add_argument("--hasil", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        if (a.out / "sample.csv").exists() and not a.force:
            sys.exit(f"{a.out / 'sample.csv'} sudah ada; pakai --force untuk mengambil sampel ulang.")
        cmd_sample(a)
    else:
        cmd_report(a)


HTML = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Kotak</title>
<style>
  :root { --bg:#f6f6f4; --panel:#fff; --ink:#1d1d1b; --muted:#6b6b66; --line:#dcdcd6; --accent:#2457c5;
          --ok:#2e7d4f; --warn:#a66300; --bad:#b3261e; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#171716; --panel:#222220; --ink:#ececea; --muted:#a3a39d; --line:#3a3a37; --accent:#7ea2f0;
            --ok:#6cc08f; --warn:#e0a24a; --bad:#f08a80; }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 system-ui, sans-serif; }
  header { display:flex; flex-wrap:wrap; gap:12px 20px; align-items:center; padding:10px 16px;
           border-bottom:1px solid var(--line); background:var(--panel); position:sticky; top:0; z-index:1; }
  header b { font-size:15px; }
  .bar { flex:1 1 200px; height:6px; background:var(--line); border-radius:3px; overflow:hidden; }
  .bar i { display:block; height:100%; background:var(--accent); width:0; }
  main { display:flex; flex-wrap:wrap; gap:16px; padding:16px; }
  .views { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-start; }
  canvas { background:#000; border-radius:4px; max-width:100%; }
  .side { flex:1 1 300px; max-width:440px; display:flex; flex-direction:column; gap:12px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:12px; }
  .cls { font-size:20px; font-weight:700; letter-spacing:.02em; }
  .muted { color:var(--muted); }
  .kal { color:var(--warn); font-weight:600; }
  .rates { display:grid; gap:6px; }
  .rates button { text-align:left; padding:8px 10px; border:1px solid var(--line); border-radius:5px;
                  background:var(--panel); color:var(--ink); font:inherit; cursor:pointer; }
  .rates button kbd { display:inline-block; width:1.6em; font-weight:700; }
  .rates button.on { border-color:var(--accent); box-shadow:inset 0 0 0 2px var(--accent); }
  .rates small { display:block; color:var(--muted); margin-left:1.6em; }
  .row { display:flex; flex-wrap:wrap; gap:8px; }
  .row button, .row label { padding:6px 10px; border:1px solid var(--line); border-radius:5px; background:var(--panel);
                            color:var(--ink); font:inherit; cursor:pointer; }
  input[type=text] { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:5px;
                     background:var(--bg); color:var(--ink); font:inherit; }
  .msg { min-height:1.4em; }
</style>
</head>
<body>
<header>
  <b>Audit kotak</b>
  <span id="pos"></span>
  <div class="bar"><i id="prog"></i></div>
  <span id="done" class="muted"></span>
</header>
<main>
  <div class="views">
    <canvas id="full" width="720" height="480"></canvas>
    <canvas id="zoom" width="380" height="380"></canvas>
  </div>
  <div class="side">
    <div class="card">
      <div class="muted">Label kelas</div>
      <div id="cls" class="cls"></div>
      <div id="meta" class="muted"></div>
      <div id="kal" class="kal"></div>
    </div>
    <div class="card rates" id="rates"></div>
    <div class="card">
      <label class="muted" for="note">Catatan (opsional; tekan Enter untuk kembali)</label>
      <input type="text" id="note" autocomplete="off">
    </div>
    <div class="card">
      <div class="row">
        <button id="prev">&larr; Sebelumnya</button>
        <button id="next">Berikutnya &rarr;</button>
        <button id="jump">Ke yang belum dinilai (U)</button>
      </div>
      <div class="row" style="margin-top:8px">
        <button id="export">Ekspor CSV</button>
        <label>Impor CSV <input type="file" id="import" accept=".csv" hidden></label>
      </div>
      <div id="msg" class="msg muted"></div>
      <div class="muted">Tombol: 1&ndash;6 menilai lalu maju, &larr;/Backspace mundur, &rarr; maju.</div>
    </div>
  </div>
</main>
<script>
const ITEMS = __ITEMS__;
const IMG_ROOT = "__IMGROOT__";
const KEY = "__KEY__";
const RUBRIC = [
  [1, "OK", "seluruh tubuh di dalam kotak, cukup pas"],
  [2, "Kurang pas (ringan)", "orangnya benar, tepi meleset jelas"],
  [3, "Terpotong berat", "kotak memuat kurang dari separuh tubuh"],
  [4, "Terlalu besar / salah objek", "luas > ~2x tubuh, atau kotak bukan pada orang"],
  [5, "Kelas salah", "postur jelas tidak cocok dengan label kelas"],
  [6, "Ambigu", "tidak bisa dinilai (gelap, tertutup)"],
];
let res = {};
try { res = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { res = {}; }
let idx = 0;
const $ = id => document.getElementById(id);
const full = $("full"), zoom = $("zoom");
const img = new Image();

function save() { try { localStorage.setItem(KEY, JSON.stringify(res)); } catch (e) {} }
function firstOpen() { const i = ITEMS.findIndex(it => !res[it.stem]); return i < 0 ? ITEMS.length - 1 : i; }

$("rates").innerHTML = RUBRIC.map(([k, t, d]) =>
  `<button data-k="${k}"><kbd>${k}</kbd>${t}<small>${d}</small></button>`).join("");
$("rates").addEventListener("click", e => { const b = e.target.closest("button"); if (b) rate(+b.dataset.k); });

function drawBox(ctx, x, y, w, h) {
  ctx.lineWidth = 4; ctx.strokeStyle = "#000"; ctx.strokeRect(x, y, w, h);
  ctx.lineWidth = 2; ctx.strokeStyle = "#ffe14d"; ctx.strokeRect(x, y, w, h);
}

function render() {
  const it = ITEMS[idx];
  const W = img.naturalWidth, H = img.naturalHeight;
  full.width = W; full.height = H;
  const f = full.getContext("2d");
  f.drawImage(img, 0, 0);
  const [xc, yc, bw, bh] = it.b;
  const x = (xc - bw / 2) * W, y = (yc - bh / 2) * H, w = bw * W, h = bh * H;
  drawBox(f, x, y, w, h);
  const m = 0.3 * Math.max(w, h);
  const cx0 = Math.max(0, x - m), cy0 = Math.max(0, y - m);
  const cx1 = Math.min(W, x + w + m), cy1 = Math.min(H, y + h + m);
  const s = Math.min(zoom.width / (cx1 - cx0), zoom.height / (cy1 - cy0));
  const z = zoom.getContext("2d");
  z.fillStyle = "#000"; z.fillRect(0, 0, zoom.width, zoom.height);
  z.imageSmoothingQuality = "high";
  z.drawImage(img, cx0, cy0, cx1 - cx0, cy1 - cy0, 0, 0, (cx1 - cx0) * s, (cy1 - cy0) * s);
  drawBox(z, (x - cx0) * s, (y - cy0) * s, w * s, h * s);
}

function show(i) {
  idx = Math.max(0, Math.min(ITEMS.length - 1, i));
  const it = ITEMS[idx], r = res[it.stem];
  $("pos").textContent = `#${it.i} / ${ITEMS.length}`;
  $("cls").textContent = it.kelas.toUpperCase();
  $("meta").textContent = `${it.stem} (${it.split})`;
  $("kal").textContent = it.kal ? "Kalibrasi: tidak ikut dihitung" : "";
  $("note").value = r ? r.catatan : "";
  document.querySelectorAll("#rates button").forEach(b => b.classList.toggle("on", r && +b.dataset.k === r.nilai));
  const n = ITEMS.filter(t => res[t.stem]).length;
  $("done").textContent = `${n} dinilai`;
  $("prog").style.width = (100 * n / ITEMS.length) + "%";
  img.onload = render;
  img.onerror = () => { $("msg").textContent = "Gambar tidak ditemukan: " + img.src; };
  img.src = `${IMG_ROOT}/${it.split}/${it.stem}.jpg`;
}

function rate(k) {
  const it = ITEMS[idx];
  res[it.stem] = { nilai: k, catatan: $("note").value.trim(), waktu: new Date().toISOString() };
  save();
  $("msg").textContent = "";
  show(idx + 1 < ITEMS.length ? idx + 1 : idx);
}

$("note").addEventListener("keydown", e => {
  e.stopPropagation();
  if (e.key === "Enter") {
    const it = ITEMS[idx];
    if (res[it.stem]) { res[it.stem].catatan = $("note").value.trim(); save(); }
    $("note").blur();
  }
});
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  if (e.key >= "1" && e.key <= "6") { rate(+e.key); e.preventDefault(); }
  else if (e.key === "ArrowLeft" || e.key === "Backspace") { show(idx - 1); e.preventDefault(); }
  else if (e.key === "ArrowRight") { show(idx + 1); e.preventDefault(); }
  else if (e.key === "u" || e.key === "U") show(firstOpen());
});
$("prev").onclick = () => show(idx - 1);
$("next").onclick = () => show(idx + 1);
$("jump").onclick = () => show(firstOpen());

function csvCell(v) { v = String(v ?? ""); return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; }
$("export").onclick = () => {
  const lines = ["urutan,stem,nilai,label_nilai,catatan,waktu"];
  for (const it of ITEMS) {
    const r = res[it.stem];
    if (!r) continue;
    lines.push([it.i, it.stem, r.nilai, RUBRIC[r.nilai - 1][1], r.catatan, r.waktu].map(csvCell).join(","));
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/csv" }));
  a.download = "hasil_audit.csv";
  a.click();
  $("msg").textContent = `${lines.length - 1} baris diekspor.`;
};

function parseCsv(text) {
  const rows = []; let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
$("import").onchange = async e => {
  const file = e.target.files[0]; if (!file) return;
  const rows = parseCsv(await file.text());
  const h = rows.shift(), si = h.indexOf("stem"), ni = h.indexOf("nilai"), ci = h.indexOf("catatan"), wi = h.indexOf("waktu");
  const known = new Set(ITEMS.map(it => it.stem)); let n = 0;
  for (const r of rows) {
    if (!known.has(r[si]) || !r[ni]) continue;
    res[r[si]] = { nilai: +r[ni], catatan: r[ci] || "", waktu: r[wi] || "" }; n++;
  }
  save(); show(firstOpen());
  $("msg").textContent = `${n} penilaian diimpor.`;
};

show(firstOpen());
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
