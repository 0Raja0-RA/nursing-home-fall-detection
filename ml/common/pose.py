"""Inferensi pose (dengan rotasi opsional), sudut tulang belakang, dan penilaian per frame."""

import math

import cv2
import numpy as np

ROTATIONS = {"cw": cv2.ROTATE_90_CLOCKWISE, "ccw": cv2.ROTATE_90_COUNTERCLOCKWISE}
# Memetakan titik dari gambar terputar kembali ke gambar asli (w, h = ukuran gambar ASLI)
UNROTATE = {
    "cw": lambda x, y, w, h: (y, h - 1 - x),
    "ccw": lambda x, y, w, h: (w - 1 - y, x),
}


def calculate_spine_angle(kpts: np.ndarray) -> float:
    """Sudut bahu-pinggul terhadap bidang horizontal gambar (0 = rebah, 90 = tegak)."""
    mid_sh = (kpts[5][:2] + kpts[6][:2]) / 2
    mid_hip = (kpts[11][:2] + kpts[12][:2]) / 2
    dx, dy = mid_sh - mid_hip
    return math.degrees(math.atan2(abs(dy), abs(dx)))


def predict_class(angle: float, aspect_ratio: float, fall_angle: float, trans_angle: float, ar_thresh: float) -> int:
    """Aturan postur berbasis sudut dan aspect ratio. 2: lying, 1: transitional, 0: normal.

    Perbaikan:
    - Bungkuk tajam (sudut 30-40 deg) dengan tubuh masih tegak ramping (AR < 0.80)
      diklasifikasikan sebagai TRANSITIONAL (1), bukan LYING (2).
    - LYING dipicu jika sudut < 30 deg mendatar, atau sudut < fall_angle dengan AR >= 0.80,
      atau AR membujur horizontal (> ar_thresh).
    """
    is_very_flat = angle < 30.0
    is_moderate_fall = (angle < fall_angle) and (aspect_ratio >= 0.80)
    is_wide_fall = (aspect_ratio > ar_thresh) and (angle < (fall_angle + 12.0))

    if is_very_flat or is_moderate_fall or is_wide_fall:
        return 2

    if angle < trans_angle or (aspect_ratio > 0.95 and angle < 70.0):
        return 1

    return 0


def iou(a, b) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms_detections(dets: list, iou_thresh: float = 0.45) -> list:
    """Menyaring deteksi yang tumpang-tindih antar sudut pandang rotasi (Cross-View NMS)."""
    if not dets:
        return []
    # Urutkan berdasarkan confidence tertinggi
    dets = sorted(dets, key=lambda d: d[0], reverse=True)
    keep = []
    for d in dets:
        conf, box, kpts = d
        overlap = False
        for k in keep:
            if iou(box, k[1]) > iou_thresh:
                overlap = True
                break
        if not overlap:
            keep.append(d)
    return keep


def predict(model, img, imgsz, conf, rotate, device=None):
    """Inferensi pose cerdas dengan Conditional Fallback TTA dan Cross-View NMS.

    Logika:
    1. Pandangan Asli: Jalankan model pada citra asli terlebih dahulu.
       Jika sudah ada orang terdeteksi, langsung kembalikan (hemat komputasi, nol noise galon/benda).
    2. Fallback Penyelamat: HANYA jika citra asli kosong (0 orang terdeteksi) dan rotate=True,
       jalankan rotasi CW dan CCW untuk menyelamatkan korban jatuh akibat upright bias COCO.
    3. Cross-View NMS: Menghilangkan deteksi duplikat bertumpuk.
    """
    h, w = img.shape[:2]

    # 1. Jalankan inferensi pada sudut pandang normal (asli)
    res = model(img, imgsz=imgsz, conf=conf, device=device, verbose=False)[0]
    dets = []
    if len(res.boxes) > 0:
        boxes = res.boxes.xyxy.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()
        kpts = res.keypoints.data.cpu().numpy()
        for bx, c, k in zip(boxes, confs, kpts):
            dets.append((float(c), bx, k))
        # Jika orang sudah terdeteksi di gambar normal, langsung selesai (tanpa rotasi)
        return dets

    # 2. HANYA jika tidak ada orang terdeteksi pada citra asli dan rotate=True:
    # Aktifkan rotasi penyelamat untuk mendeteksi korban jatuh mendatar
    if rotate:
        for name, code in ROTATIONS.items():
            rot_img = cv2.rotate(img, code)
            res_rot = model(rot_img, imgsz=imgsz, conf=conf, device=device, verbose=False)[0]
            if len(res_rot.boxes) == 0:
                continue
            boxes = res_rot.boxes.xyxy.cpu().numpy()
            confs = res_rot.boxes.conf.cpu().numpy()
            kpts = res_rot.keypoints.data.cpu().numpy()
            unrot = UNROTATE[name]
            for bx, c, k in zip(boxes, confs, kpts):
                corners = np.array([unrot(x, y, w, h) for x, y in ((bx[0], bx[1]), (bx[2], bx[3]))])
                box = np.array([corners[:, 0].min(), corners[:, 1].min(), corners[:, 0].max(), corners[:, 1].max()])
                k2 = k.copy()
                for i in range(17):
                    k2[i, 0], k2[i, 1] = unrot(k[i, 0], k[i, 1], w, h)
                dets.append((float(c), box, k2))

        # Terapkan Cross-View NMS untuk menghilangkan deteksi bertumpuk
        if len(dets) > 1:
            dets = nms_detections(dets, iou_thresh=0.45)

    return dets


def score_frame(dets, gt_box) -> dict:
    """Proxy kualitas pose terhadap bbox label, karena dataset tidak punya label keypoint.

    found: ada deteksi IoU >= 0.5; top1: deteksi conf tertinggi adalah orang yang benar;
    core: top1 + bahu & pinggul conf > 0.25 di dalam bbox; extra: jumlah deteksi selain orang itu.
    """
    ious = [iou(d[1], gt_box) for d in dets]
    found = any(v >= 0.5 for v in ious)
    extra = sum(v < 0.5 for v in ious)
    top1, core = False, False
    if dets:
        i = int(np.argmax([d[0] for d in dets]))
        top1 = bool(ious[i] >= 0.5)
        if top1:
            k = dets[i][2]
            core = all(
                k[j, 2] > 0.25 and gt_box[0] <= k[j, 0] <= gt_box[2] and gt_box[1] <= k[j, 1] <= gt_box[3]
                for j in (5, 6, 11, 12)
            )
    return {"found": found, "top1": top1, "core": bool(core), "extra": int(extra)}
