"""Menggambar skeleton dan panel perbandingan pose."""

import cv2
import numpy as np

LIMBS = {
    (5, 7): "l", (7, 9): "l", (11, 13): "l", (13, 15): "l", (5, 11): "l",
    (6, 8): "r", (8, 10): "r", (12, 14): "r", (14, 16): "r", (6, 12): "r",
    (5, 6): "c", (11, 12): "c",
}
LIMB_COLOR = {"l": (255, 170, 60), "r": (60, 170, 255), "c": (240, 240, 240)}
STATUS_COLOR = {"ok": (80, 200, 80), "partial": (0, 210, 255), "miss": (60, 60, 240)}
PANEL_W, PANEL_H, BAR_H, ROW_H = 320, 240, 22, 24


def crop_window(box, w, h, margin=0.35):
    """Jendela potong 4:3 di sekitar box, dibatasi ke ukuran gambar."""
    bw, bh = box[2] - box[0], box[3] - box[1]
    cw = max(bw, bh * 4 / 3) * (1 + 2 * margin)
    ch = cw * 3 / 4
    cw, ch = min(cw, w), min(ch, h)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    x1 = min(max(0.0, cx - cw / 2), w - cw)
    y1 = min(max(0.0, cy - ch / 2), h - ch)
    return int(x1), int(y1), int(x1 + cw), int(y1 + ch)


def status_of(score: dict) -> str:
    if score["top1"] and score["core"]:
        return "ok"
    return "partial" if score["found"] else "miss"


def render(img, window, dets, score, label) -> np.ndarray:
    """Panel potongan dengan skeleton deteksi conf tertinggi dan border sesuai status."""
    x1, y1, x2, y2 = window
    sx, sy = PANEL_W / (x2 - x1), PANEL_H / (y2 - y1)
    out = cv2.resize(img[y1:y2, x1:x2], (PANEL_W, PANEL_H), interpolation=cv2.INTER_LINEAR)
    to_px = lambda x, y: (int((x - x1) * sx), int((y - y1) * sy))

    text = f"{label}: TIDAK ADA ORANG"
    if dets:
        conf, box, k = max(dets, key=lambda d: d[0])
        cv2.rectangle(out, to_px(box[0], box[1]), to_px(box[2], box[3]), (200, 200, 90), 1)
        for (a, b), side in LIMBS.items():
            if k[a, 2] > 0.25 and k[b, 2] > 0.25:
                cv2.line(out, to_px(k[a, 0], k[a, 1]), to_px(k[b, 0], k[b, 1]), LIMB_COLOR[side], 2, cv2.LINE_AA)
        for j in range(17):
            if k[j, 2] > 0.25:
                cv2.circle(out, to_px(k[j, 0], k[j, 1]), 3, (0, 255, 255), -1, cv2.LINE_AA)
        text = f"{label}: conf {conf:.2f}"
        if box[2] < x1 or box[0] > x2 or box[3] < y1 or box[1] > y2:
            text += " (DI LUAR AREA INI)"

    state = status_of(score)
    cv2.rectangle(out, (1, 1), (PANEL_W - 2, PANEL_H - 2), STATUS_COLOR[state], 3)
    bar = np.full((BAR_H, PANEL_W, 3), 30, np.uint8)
    cv2.putText(bar, text, (6, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, STATUS_COLOR[state], 1, cv2.LINE_AA)
    return np.vstack([out, bar])


def header(text: str, width: int) -> np.ndarray:
    bar = np.zeros((ROW_H, width, 3), np.uint8)
    cv2.putText(bar, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return bar
