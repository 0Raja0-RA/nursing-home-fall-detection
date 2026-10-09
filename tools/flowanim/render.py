#!/usr/bin/env python
"""
Pengubah berkas .excalidraw menjadi SVG beranimasi.

Modul ini hanya mengurus GEOMETRI: membaca elemen Excalidraw lalu menuliskannya
sebagai SVG di mana setiap elemen punya grup `<g data-id="...">` sendiri. Grup
itulah yang nanti dinyalakan/diredam oleh timeline di `build.py`.

Kenapa bikin renderer sendiri dan tidak ekspor SVG dari excalidraw.com:
hasil ekspornya satu gambar utuh tanpa pegangan per elemen, jadi tidak bisa
dianimasikan per node. Kedua diagram di proyek ini dibuat dengan
`roughness: 0` (bentuk geometris bersih, bukan sketsa tangan), jadi menggambar
ulangnya cuma soal rect/ellipse/diamond/polyline -- tidak perlu roughjs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

# Excalidraw memakai "adaptive radius": seperempat sisi terpendek, maksimal 32.
MAX_ADAPTIVE_RADIUS = 32
ARROW_HEAD_LEN = 18.0
ARROW_HEAD_ANGLE = math.radians(26)
ELBOW_RADIUS = 14.0

# Teks pendek satu baris yang menempel di dekat panah dianggap labelnya ("ya"/"tidak").
EDGE_LABEL_MAX_CHARS = 28
EDGE_LABEL_MAX_DIST = 95.0

FONT_STACK = "'Segoe UI', 'Inter', system-ui, -apple-system, 'Helvetica Neue', sans-serif"


def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def pad(self, p: float) -> "Box":
        return Box(self.x0 - p, self.y0 - p, self.x1 + p, self.y1 + p)

    def union(self, other: "Box") -> "Box":
        return Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


@dataclass
class Diagram:
    """Satu berkas .excalidraw yang sudah di-index."""

    elements: list = field(default_factory=list)
    by_id: dict = field(default_factory=dict)
    shapes: list = field(default_factory=list)
    arrows: list = field(default_factory=list)
    label_of: dict = field(default_factory=dict)   # id bentuk  -> elemen teks
    edge_label_of: dict = field(default_factory=dict)  # id panah -> elemen teks
    statics: list = field(default_factory=list)    # id elemen yang selalu tampil
    arrow_ends: dict = field(default_factory=dict)  # id panah -> (id awal, id akhir)
    arrow_len: dict = field(default_factory=dict)   # id panah -> panjang lintasan


def load(path: Path) -> Diagram:
    raw = json.loads(path.read_text(encoding="utf-8"))
    els = [e for e in raw["elements"] if not e.get("isDeleted")]

    d = Diagram(elements=els, by_id={e["id"]: e for e in els})

    for e in els:
        if e["type"] in ("rectangle", "ellipse", "diamond"):
            d.shapes.append(e)
        elif e["type"] == "arrow":
            d.arrows.append(e)

    # Teks yang terikat ke bentuk (containerId) selalu ikut bentuknya.
    for e in els:
        if e["type"] == "text" and e.get("containerId"):
            d.label_of[e["containerId"]] = e

    for a in d.arrows:
        s = (a.get("startBinding") or {}).get("elementId")
        t = (a.get("endBinding") or {}).get("elementId")
        d.arrow_ends[a["id"]] = (s, t)
        d.arrow_len[a["id"]] = _polyline_length(_arrow_points(a))

    _attach_edge_labels(d)
    return d


def _arrow_points(a: dict) -> list:
    return [(a["x"] + px, a["y"] + py) for px, py in a["points"]]


def _polyline_length(pts: list) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1.0


def _dist_point_segment(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def _attach_edge_labels(d: Diagram) -> None:
    """Tempelkan teks lepas yang pendek ke panah terdekat; sisanya jadi statis.

    Dipakai supaya label cabang ("ya" / "tidak" / "YA - ini indikasi jatuh")
    muncul bersamaan dengan panahnya, bukan sebagai teks yang nongol sendiri.
    Jaraknya diukur ke LINTASAN panah, bukan ke titik tengahnya -- panah elbow
    di diagram ini panjang-panjang, titik tengahnya sering jauh dari labelnya.
    """
    free = [
        e
        for e in d.elements
        if e["type"] == "text" and not e.get("containerId")
    ]
    taken: set = set()

    for t in free:
        txt = t.get("text", "")
        if len(txt) > EDGE_LABEL_MAX_CHARS or "\n" in txt:
            d.statics.append(t["id"])
            continue

        cx = t["x"] + t["width"] / 2
        cy = t["y"] + t["height"] / 2
        best, best_d = None, float("inf")
        for a in d.arrows:
            if a["id"] in taken:
                continue
            pts = _arrow_points(a)
            dd = min(
                _dist_point_segment((cx, cy), pts[i], pts[i + 1])
                for i in range(len(pts) - 1)
            )
            if dd < best_d:
                best, best_d = a, dd

        if best is not None and best_d <= EDGE_LABEL_MAX_DIST:
            d.edge_label_of[best["id"]] = t
            taken.add(best["id"])
        else:
            d.statics.append(t["id"])

    # Bentuk tanpa label (kotak KETERANGAN yang cuma jadi wadah) juga statis.
    for s in d.shapes:
        if s["id"] not in d.label_of and s.get("strokeStyle") == "dashed":
            d.statics.append(s["id"])


# ---------------------------------------------------------------- geometri

def element_box(e: dict) -> Box:
    if e["type"] == "arrow":
        pts = _arrow_points(e)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Box(min(xs), min(ys), max(xs), max(ys))
    return Box(e["x"], e["y"], e["x"] + e["width"], e["y"] + e["height"])


def bbox_of(d: Diagram, ids) -> Box:
    boxes = [element_box(d.by_id[i]) for i in ids if i in d.by_id]
    if not boxes:
        raise ValueError("tidak ada elemen yang cocok untuk menghitung kamera")
    out = boxes[0]
    for b in boxes[1:]:
        out = out.union(b)
    return out


def _rect_radius(e: dict) -> float:
    if not e.get("roundness"):
        return 0.0
    return min(MAX_ADAPTIVE_RADIUS, min(e["width"], e["height"]) * 0.25)


def _diamond_points(e: dict) -> list:
    x, y, w, h = e["x"], e["y"], e["width"], e["height"]
    return [
        (x + w / 2, y),
        (x + w, y + h / 2),
        (x + w / 2, y + h),
        (x, y + h / 2),
    ]


def _rounded_polyline_path(pts: list, r: float) -> str:
    """Polyline dengan sudut dibulatkan -- mendekati tampilan panah elbow Excalidraw."""
    if len(pts) < 3:
        return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)

    out = [f"M {pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for i in range(1, len(pts) - 1):
        prev, cur, nxt = pts[i - 1], pts[i], pts[i + 1]
        d_in = math.dist(prev, cur)
        d_out = math.dist(cur, nxt)
        rr = min(r, d_in / 2, d_out / 2)
        if rr < 1:
            out.append(f"L {cur[0]:.2f} {cur[1]:.2f}")
            continue
        ux, uy = (cur[0] - prev[0]) / d_in, (cur[1] - prev[1]) / d_in
        vx, vy = (nxt[0] - cur[0]) / d_out, (nxt[1] - cur[1]) / d_out
        a = (cur[0] - ux * rr, cur[1] - uy * rr)
        b = (cur[0] + vx * rr, cur[1] + vy * rr)
        out.append(f"L {a[0]:.2f} {a[1]:.2f}")
        out.append(f"Q {cur[0]:.2f} {cur[1]:.2f} {b[0]:.2f} {b[1]:.2f}")
    out.append(f"L {pts[-1][0]:.2f} {pts[-1][1]:.2f}")
    return " ".join(out)


def _arrow_head_path(pts: list) -> str:
    """Dua garis ujung panah, digambar dari segmen terakhir."""
    tip = pts[-1]
    # Cari titik sebelumnya yang benar-benar beda posisi.
    prev = next(
        (p for p in reversed(pts[:-1]) if math.dist(p, tip) > 0.5),
        (tip[0] - 1, tip[1]),
    )
    ang = math.atan2(tip[1] - prev[1], tip[0] - prev[0])
    legs = []
    for sign in (1, -1):
        a = ang + math.pi - sign * ARROW_HEAD_ANGLE
        legs.append(
            f"M {tip[0]:.2f} {tip[1]:.2f} "
            f"L {tip[0] + ARROW_HEAD_LEN * math.cos(a):.2f} "
            f"{tip[1] + ARROW_HEAD_LEN * math.sin(a):.2f}"
        )
    return " ".join(legs)


# ---------------------------------------------------------------- penulisan SVG

def _text_svg(t: dict, cls: str = "") -> str:
    """Teks Excalidraw sudah dibungkus manual (ada '\\n'), jadi tiap baris
    ditulis sebagai <text> sendiri. Tidak ada pembungkusan ulang di sini,
    supaya tata letaknya sama dengan yang terlihat di excalidraw.com."""
    lines = t.get("text", "").split("\n")
    size = t.get("fontSize", 16)
    advance = size * t.get("lineHeight", 1.25)
    align = t.get("textAlign", "left")
    anchor = {"left": "start", "center": "middle", "right": "end"}[align]
    if align == "center":
        ax = t["x"] + t["width"] / 2
    elif align == "right":
        ax = t["x"] + t["width"]
    else:
        ax = t["x"]

    # Blok teks ditengahkan vertikal pada kotaknya sendiri.
    block_h = advance * len(lines)
    top = t["y"] + (t["height"] - block_h) / 2

    parts = []
    for i, ln in enumerate(lines):
        cy = top + advance * i + advance / 2
        parts.append(
            f'<text class="{cls}" x="{ax:.2f}" y="{cy:.2f}" font-size="{size}" '
            f'fill="{t["strokeColor"]}" text-anchor="{anchor}" '
            f'dominant-baseline="central">{xml_escape(ln)}</text>'
        )
    return "".join(parts)


def _shape_geom(e: dict, cls: str, extra: str = "") -> str:
    if e["type"] == "rectangle":
        r = _rect_radius(e)
        return (
            f'<rect class="{cls}" x="{e["x"]:.2f}" y="{e["y"]:.2f}" '
            f'width="{e["width"]:.2f}" height="{e["height"]:.2f}" '
            f'rx="{r:.2f}" ry="{r:.2f}" {extra}/>'
        )
    if e["type"] == "ellipse":
        return (
            f'<ellipse class="{cls}" cx="{e["x"] + e["width"] / 2:.2f}" '
            f'cy="{e["y"] + e["height"] / 2:.2f}" rx="{e["width"] / 2:.2f}" '
            f'ry="{e["height"] / 2:.2f}" {extra}/>'
        )
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in _diamond_points(e))
    return f'<polygon class="{cls}" points="{pts}" {extra}/>'


def _dash_for(style: str) -> str:
    if style == "dashed":
        return 'stroke-dasharray="14 9"'
    if style == "dotted":
        return 'stroke-dasharray="2 7"'
    return ""


def render_svg(d: Diagram, stage_w: int, stage_h: int) -> str:
    """Seluruh diagram jadi satu SVG. Urutannya: panah dulu, lalu bentuk,
    supaya bentuk menutupi ekor panah yang masuk ke dalamnya."""
    out: list = []

    for a in d.arrows:
        pts = _arrow_points(a)
        path = _rounded_polyline_path(pts, ELBOW_RADIUS)
        dashed = a.get("strokeStyle", "solid") != "solid"
        length = d.arrow_len[a["id"]]
        label = d.edge_label_of.get(a["id"])
        sw = a.get("strokeWidth", 2)
        col = a["strokeColor"]
        # Tiga lapis: `ghost` = rangka samar yang selalu ada supaya bentuk
        # diagram tetap kebaca, `line` = garis penuh yang "digambar" saat
        # langkahnya tiba, `head` = kepala panah yang baru muncul di akhir
        # tarikan (kalau tidak, kepalanya melayang tanpa garis).
        out.append(
            f'<g data-id="{a["id"]}" data-kind="arrow" data-len="{length:.1f}" '
            f'data-dashed="{int(dashed)}" class="el arrow">'
            f'<path class="ghost" d="{path}" fill="none" stroke="{col}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" '
            f'{_dash_for(a.get("strokeStyle", "solid"))}/>'
            f'<path class="line" d="{path}" fill="none" stroke="{col}" '
            f'stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round" '
            f'{_dash_for(a.get("strokeStyle", "solid"))}/>'
            f'<path class="head" d="{_arrow_head_path(pts)}" fill="none" '
            f'stroke="{col}" stroke-width="{sw}" stroke-linecap="round"/>'
            + (f'<g class="lbl">{_text_svg(label, "edge-label")}</g>' if label else "")
            + "</g>"
        )

    for s in d.shapes:
        fill = s.get("backgroundColor", "transparent")
        if fill == "transparent":
            fill = "none"
        base_op = s.get("opacity", 100) / 100
        label = d.label_of.get(s["id"])
        halo = _shape_geom(s, "halo", f'fill="none" stroke="{s["strokeColor"]}" stroke-width="14"')
        body = _shape_geom(
            s,
            "body",
            f'fill="{fill}" stroke="{s["strokeColor"]}" '
            f'stroke-width="{s.get("strokeWidth", 2)}" '
            f'{_dash_for(s.get("strokeStyle", "solid"))}',
        )
        out.append(
            f'<g data-id="{s["id"]}" data-kind="node" data-base-op="{base_op}" class="el node">'
            + halo
            + body
            + (_text_svg(label, "node-label") if label else "")
            + "</g>"
        )

    # Teks lepas (judul, catatan pinggir, isi kotak KETERANGAN).
    for e in d.elements:
        if e["type"] == "text" and e["id"] in d.statics:
            out.append(
                f'<g data-id="{e["id"]}" data-kind="static" class="el static">'
                + _text_svg(e, "free-text")
                + "</g>"
            )

    return (
        f'<svg id="stage" viewBox="0 0 {stage_w} {stage_h}" '
        f'width="{stage_w}" height="{stage_h}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="{FONT_STACK}">'
        f'<g id="cam">' + "".join(out) + "</g></svg>"
    )
