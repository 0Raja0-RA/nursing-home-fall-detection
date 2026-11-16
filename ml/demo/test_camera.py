"""
test_camera.py
==============
Skrip pengujian deteksi pose jatuh langsung pada kamera nyata (Webcam Laptop / Iriun Webcam / CCTV).

Fitur:
- Deteksi pose real-time 17 keypoints menggunakan model YOLO11-Pose.
- Perhitungan sudut tulang belakang (spine angle) & klasifikasi postur (Normal, Transisi, Lying).
- TTA Rotasi interaktif: tekan tombol 'r' untuk toggle mode rotasi secara langsung!
- Dukungan DirectShow di Windows untuk startup kamera cepat.

Kontrol Keyboard:
- 'r' : Toggle TTA Rotasi ON / OFF secara live
- 's' : Simpan screenshot saat ini ke ml/outputs/
- 'q' / ESC : Keluar

Penggunaan:
    python ml/demo/test_camera.py
    python ml/demo/test_camera.py --source 0          # Webcam bawaan laptop
    python ml/demo/test_camera.py --source 1          # Iriun Webcam / Webcam eksternal
    python ml/demo/test_camera.py --source 0 --rotate # Langsung aktifkan rotasi
"""

import argparse
import math
import sys
import time
from pathlib import Path

# Tambahkan root proyek ke sys.path secara otomatis agar bisa dijalankan dari folder mana saja
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from ml.common.labels import CLASS_NAMES
from ml.common.pose import calculate_spine_angle, predict, predict_class

SKELETON_PAIRS = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

POSTURE_COLORS = {
    0: (46, 204, 113),   # Normal: Hijau
    1: (0, 215, 255),    # Transitional: Kuning
    2: (50, 50, 255),    # Lying: Merah
    -1: (180, 180, 180), # Unknown: Abu-abu
}


def smoothing_factor(t_e, cutoff):
    r = 2 * math.pi * cutoff * t_e
    return r / (r + 1)


class OneEuroFilter1D:
    """Implementasi 1 Euro Filter (Casiez et al., CHI 2012) untuk peredaman jitter real-time."""
    def __init__(self, t0, x0, dx0=0.0, min_cutoff=1.0, beta=0.05, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = float(x0)
        self.dx_prev = float(dx0)
        self.t_prev = float(t0)

    def filter(self, t, x):
        t_e = max(1e-4, t - self.t_prev)
        a_d = smoothing_factor(t_e, self.d_cutoff)
        dx = (x - self.x_prev) / t_e
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = smoothing_factor(t_e, cutoff)
        x_hat = a * x + (1.0 - a) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


class PoseKeypointSmoother:
    """
    Menghaluskan 17 keypoint pose tubuh dengan 1 Euro Filter standar industri:
    - Meredam jitter/getaran saat tubuh rebahan atau diam di lantai (cutoff rendah).
    - Menghilangkan lag saat bergerak cepat atau jatuh (cutoff adaptif naik).
    - Mencegah garis skeleton kedip-kedip saat ada keypoint drop sesaat.
    """
    def __init__(self, min_cutoff=1.0, beta=0.05):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.filters_x = {}
        self.filters_y = {}
        self.last_seen = {}

    def smooth(self, kpts: np.ndarray, timestamp: float) -> np.ndarray:
        smoothed = kpts.copy()
        for i in range(17):
            x, y, conf = kpts[i]
            if conf < 0.15:
                # Jika keypoint drop sesaat (<0.25 detik), pertahankan posisi terakhir agar tidak kedap-kedip
                if i in self.filters_x and (timestamp - self.last_seen.get(i, 0.0) < 0.25):
                    smoothed[i, 0] = self.filters_x[i].x_prev
                    smoothed[i, 1] = self.filters_y[i].x_prev
                    smoothed[i, 2] = max(conf, 0.26)
                continue

            self.last_seen[i] = timestamp

            if i not in self.filters_x:
                self.filters_x[i] = OneEuroFilter1D(timestamp, x, min_cutoff=self.min_cutoff, beta=self.beta)
                self.filters_y[i] = OneEuroFilter1D(timestamp, y, min_cutoff=self.min_cutoff, beta=self.beta)
            else:
                smoothed[i, 0] = self.filters_x[i].filter(timestamp, x)
                smoothed[i, 1] = self.filters_y[i].filter(timestamp, y)

        return smoothed

    def reset(self):
        self.filters_x.clear()
        self.filters_y.clear()
        self.last_seen.clear()


class MultiPersonSmoother:
    """
    Mengelola PoseKeypointSmoother terpisah untuk setiap orang di frame (Multi-Person Tracking).
    Mencegah skeleton antar orang yang berbeda tercampur atau saling tarik-menarik.
    """
    def __init__(self, min_cutoff=1.0, beta=0.05):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.smoothers = {}   # id -> PoseKeypointSmoother
        self.last_boxes = {}  # id -> np.ndarray [x1, y1, x2, y2]
        self.last_seen = {}   # id -> float timestamp
        self.next_id = 0

    def reset(self):
        self.smoothers.clear()
        self.last_boxes.clear()
        self.last_seen.clear()

    def smooth(self, box: np.ndarray, kpts: np.ndarray, timestamp: float) -> np.ndarray:
        # 1. Bersihkan track lama (> 1.0 detik tidak terlihat)
        for pid in list(self.last_seen.keys()):
            if timestamp - self.last_seen[pid] > 1.0:
                self.smoothers.pop(pid, None)
                self.last_boxes.pop(pid, None)
                self.last_seen.pop(pid, None)

        # 2. Cari track orang yang paling cocok berdasarkan jarak pusat bounding box
        bx_cx = (box[0] + box[2]) / 2.0
        bx_cy = (box[1] + box[3]) / 2.0
        bw = max(1.0, box[2] - box[0])
        bh = max(1.0, box[3] - box[1])

        best_id = None
        best_dist = 999999.0
        max_match_dist = max(bw, bh) * 1.5

        for pid, prev_box in self.last_boxes.items():
            prev_cx = (prev_box[0] + prev_box[2]) / 2.0
            prev_cy = (prev_box[1] + prev_box[3]) / 2.0
            dist = math.hypot(bx_cx - prev_cx, bx_cy - prev_cy)
            if dist < best_dist and dist < max_match_dist:
                best_dist = dist
                best_id = pid

        if best_id is None:
            best_id = self.next_id
            self.next_id += 1
            self.smoothers[best_id] = PoseKeypointSmoother(self.min_cutoff, self.beta)

        self.last_boxes[best_id] = box
        self.last_seen[best_id] = timestamp

        # 3. Smooth keypoint secara terisolasi hanya untuk orang ini
        smoothed = self.smoothers[best_id].smooth(kpts, timestamp)

        # 4. Bounding Box Guard: Cegah keypoint terlempar jauh keluar dari kotak orangnya
        pad_x = bw * 0.35
        pad_y = bh * 0.35
        min_x, max_x = box[0] - pad_x, box[2] + pad_x
        min_y, max_y = box[1] - pad_y, box[3] + pad_y

        for i in range(17):
            if smoothed[i, 2] > 0.15:
                smoothed[i, 0] = np.clip(smoothed[i, 0], min_x, max_x)
                smoothed[i, 1] = np.clip(smoothed[i, 1], min_y, max_y)

        return smoothed


def list_available_cameras(max_cams: int = 6):
    """Memindai dan mencetak daftar indeks kamera yang terhubung di sistem Windows/Linux."""
    print("==================================================")
    print("🔍 MEMINDAI INDEKS KAMERA DI SISTEM (0 - 5)...")
    print("==================================================")
    found = 0
    for idx in range(max_cams):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if sys.platform.startswith("win") else cv2.VideoCapture(idx)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"  ✅ [Indeks {idx}] : AKTIF & TERSEDIA ({w}x{h} @ {fps:.0f} FPS)")
            cap.release()
            found += 1
        else:
            print(f"  ❌ [Indeks {idx}] : Tidak Terdeteksi / Nonaktif")
    print("--------------------------------------------------")
    if found == 0:
        print("⚠️ Tidak ada kamera yang terdeteksi.")
    else:
        print(f"Total {found} perangkat video aktif.")
        print("Tips: Jalankan 'python ml/demo/test_camera.py --source <nomor_indeks>'")
    print("==================================================")


def open_camera(source: str, width: int = 640, height: int = 480):
    """Membuka kamera dengan fallback DirectShow di Windows dan resolusi optimal."""
    src = int(source) if source.isdigit() else source
    if isinstance(src, int) and sys.platform.startswith("win"):
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(src)
    else:
        cap = cv2.VideoCapture(src)

    if cap.isOpened():
        # Set resolusi frame agar transfer buffer kamera ringan dan FPS tinggi
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)

    return cap


def check_hand_gesture(kpts):
    """
    Mendeteksi gesture sementara:
    1. Raise Hand: Pergelangan tangan (wrist) berada lebih tinggi dari bahu (shoulder).
    2. Squeeze Hand: Tangan ditekuk/siku ditekuk rapat ke arah bahu (flex/squeeze),
       atau kedua pergelangan tangan dirapatkan/dikepal bersama.
    """
    raised = False
    squeezed = False

    # 1. Cek tangan kanan (6: r_shoulder, 8: r_elbow, 10: r_wrist)
    if kpts[10][2] > 0.25 and kpts[6][2] > 0.25:
        if kpts[10][1] < kpts[6][1]:  # Wrist lebih tinggi dari shoulder
            raised = True
            d_wrist_sh = np.linalg.norm(kpts[10][:2] - kpts[6][:2])
            if kpts[8][2] > 0.25:
                d_arm = np.linalg.norm(kpts[6][:2] - kpts[8][:2]) + np.linalg.norm(kpts[8][:2] - kpts[10][:2])
                if d_arm > 10 and (d_wrist_sh / d_arm) < 0.65:
                    squeezed = True
            elif d_wrist_sh < 60:
                squeezed = True

    # 2. Cek tangan kiri (5: l_shoulder, 7: l_elbow, 9: l_wrist)
    if kpts[9][2] > 0.25 and kpts[5][2] > 0.25:
        if kpts[9][1] < kpts[5][1]:
            raised = True
            d_wrist_sh = np.linalg.norm(kpts[9][:2] - kpts[5][:2])
            if kpts[7][2] > 0.25:
                d_arm = np.linalg.norm(kpts[5][:2] - kpts[7][:2]) + np.linalg.norm(kpts[7][:2] - kpts[9][:2])
                if d_arm > 10 and (d_wrist_sh / d_arm) < 0.65:
                    squeezed = True
            elif d_wrist_sh < 60:
                squeezed = True

    # 3. Cek kedua tangan saling menyentuh / squeeze bersama
    if kpts[9][2] > 0.25 and kpts[10][2] > 0.25:
        d_wrists = np.linalg.norm(kpts[9][:2] - kpts[10][:2])
        if raised and d_wrists < 65:
            squeezed = True

    return raised, squeezed


def main():
    parser = argparse.ArgumentParser(description="Test Real Camera - Fall Detection Pose")
    parser.add_argument("--source", type=str, default="0", help="Indeks kamera (0=laptop, 1=Iriun) atau RTSP/Video")
    parser.add_argument("--model", type=str, default="yolo11n-pose.pt", help="Path bobot model pose")
    parser.add_argument("--imgsz", type=int, default=480, help="Resolusi inferensi YOLO (default: 480 untuk FPS tinggi, coba 640/320)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold (default: 0.25)")
    parser.add_argument("--rotate", action="store_true", help="Mulai dengan TTA Rotasi aktif (Catatan: FPS turun ~2.5x saat rotasi aktif)")
    parser.add_argument("--fall-angle", type=float, default=40.0, help="Ambang sudut jatuh derajat (default: 40.0)")
    parser.add_argument("--trans-angle", type=float, default=60.0, help="Ambang sudut transisi derajat (default: 60.0)")
    parser.add_argument("--ar-thresh", type=float, default=1.25, help="Ambang aspect ratio tubuh rebah (default: 1.25)")
    parser.add_argument("--no-smooth", action="store_true", help="Nonaktifkan 1-Euro Keypoint Smoothing Filter")
    parser.add_argument("--no-auto-snap", action="store_true", help="Nonaktifkan fitur auto-screenshot gesture secara default")
    parser.add_argument("--list-cams", action="store_true", help="Pindai dan tampilkan semua indeks kamera yang tersedia di laptop")
    args = parser.parse_args()

    if args.list_cams:
        list_available_cameras()
        return

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"🚀 Memuat model {args.model} pada device: {device}...")
    model = YOLO(args.model)

    print(f"📷 Membuka kamera sumber: {args.source}...")
    cap = open_camera(args.source)

    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera pada sumber '{args.source}'.")
        print("💡 Tips: Coba ganti '--source 1' jika memakai Iriun Webcam atau kamera USB eksternal.")
        return

    # Ambil resolusi kamera
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✅ Kamera aktif: {width}x{height} piksel.")
    print("-------------------------------------------------------------")
    print("Petunjuk Kontrol:")
    print("  [r] : Toggle TTA Rotasi ON / OFF")
    print("  [m] : Toggle 1-Euro Smoothing Filter (Anti-Jitter) ON / OFF")
    print("  [a] : Toggle Auto-Screenshot Gesture ON / OFF")
    print("  [s] : Simpan screenshot manual ke ml/outputs/")
    print("  [q] : Keluar")
    print("  ✨ AUTO-SCREENSHOT GESTURE (SEMENTARA):")
    print("     Angkat tangan (raise hand) & tekuk/squeeze ke arah bahu/kepala")
    print("     atau tahan tangan di atas kepala selama ~1 detik -> Countdown 2s -> JEPPRET! 📸")
    print("-------------------------------------------------------------")

    rotate_mode = args.rotate
    smooth_mode = not args.no_smooth
    auto_snap_enabled = not args.no_auto_snap
    smoother = MultiPersonSmoother()

    fps_start = time.time()
    frame_count = 0
    fps = 0.0

    out_dir = Path("ml/outputs/camera_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    # State untuk Auto-Screenshot Gesture
    gesture_hold_start = None
    countdown_start = None
    COUNTDOWN_DURATION = 2.0  # 2 detik hitungan mundur sebelum jepret
    last_snap_time = 0.0
    SNAP_COOLDOWN = 3.0       # Cooldown 3 detik setelah jepret agar tidak spam
    flash_frames = 0          # Frame counter untuk visual flash effect

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Stream kamera terputus atau tidak ada frame.")
            break

        frame_count += 1
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            fps_start = time.time()

        display = frame.copy()

        # Jalankan inferensi pose (dengan resolusi imgsz yang dapat disesuaikan)
        dets = predict(model, frame, imgsz=args.imgsz, conf=args.conf, rotate=rotate_mode, device=device)

        person_count = len(dets)
        primary_posture = "NO PERSON (UNKNOWN)"
        primary_color = (180, 180, 180)
        primary_pred_name = "unknown"

        any_raised = False
        any_squeezed = False

        if not dets:
            smoother.reset()
        else:
            for conf, box, kpts in dets:
                # Terapkan 1-Euro Keypoint Smoothing untuk meredam jitter/getaran skeleton
                if smooth_mode:
                    kpts = smoother.smooth(box, kpts, time.time())

                x1, y1, x2, y2 = map(int, box)
                w_box = max(1, x2 - x1)
                h_box = max(1, y2 - y1)
                ar = w_box / h_box

                # Cek ketersediaan keypoints bahu, pinggul, dan kepala
                sh_valid = (kpts[5][2] + kpts[6][2]) / 2 > 0.25
                hip_valid = (kpts[11][2] + kpts[12][2]) / 2 > 0.25
                head_valid = kpts[0][2] > 0.25 or (kpts[1][2] > 0.25 and kpts[2][2] > 0.25)

                if sh_valid and hip_valid:
                    # Kasus 1: Tubuh utuh (bahu + pinggul tampak) -> sudut spine utama
                    angle = calculate_spine_angle(kpts)
                    src_label = "Spine"
                elif sh_valid and head_valid:
                    # Kasus 2: Tubuh bawah terpotong (close-up laptop / dada ke atas)
                    # Cek orientasi kepala terhadap bahu agar tidak salah mengira orang duduk sebagai rebahan
                    mid_sh = (kpts[5][:2] + kpts[6][:2]) / 2
                    head_pt = kpts[0][:2] if kpts[0][2] > 0.25 else ((kpts[1][:2] + kpts[2][:2]) / 2)
                    dx = head_pt[0] - mid_sh[0]
                    dy = mid_sh[1] - head_pt[1]  # Positif jika kepala di atas bahu
                    if dy > 0:
                        angle = math.degrees(math.atan2(dy, abs(dx)))
                        src_label = "Head-Shoulder"
                    else:
                        angle = 20.0
                        src_label = "Head Below Shoulder"
                else:
                    # Kasus 3: Keypoint tidak lengkap
                    is_bottom_truncated = y2 >= (display.shape[0] - 20)
                    if is_bottom_truncated:
                        # Jika tubuh terpotong batas bawah frame kamera, jangan gunakan BBox AR rebahan!
                        angle = 90.0
                        src_label = "Truncated (Upright)"
                    else:
                        angle = 90.0 if ar < 0.8 else (20.0 if ar > 1.3 else 50.0)
                        src_label = "BBox AR"

                pred = predict_class(angle, ar, args.fall_angle, args.trans_angle, args.ar_thresh)

                # Koreksi untuk close-up kepala-bahu: jika sudut kepala-bahu tegak (>= 60 deg),
                # pastikan diklasifikasikan sebagai NORMAL (0), jangan terpengaruh AR bbox yang melebar
                if src_label in ("Head-Shoulder", "Truncated (Upright)") and angle >= args.trans_angle:
                    pred = 0

                label_name = CLASS_NAMES.get(pred, "UNKNOWN").upper()
                color = POSTURE_COLORS.get(pred, (255, 255, 255))

                primary_posture = f"{label_name} ({angle:.0f} deg | {src_label})"
                primary_color = color
                primary_pred_name = label_name.lower()

                # Cek gesture sementara (Raise Hand & Squeeze)
                is_raised, is_squeezed = check_hand_gesture(kpts)
                if is_raised:
                    any_raised = True
                if is_squeezed:
                    any_squeezed = True

                # 1. Gambar bounding box orang
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

                # 2. Gambar garis skeleton tubuh
                for p1, p2 in SKELETON_PAIRS:
                    if kpts[p1][2] > 0.25 and kpts[p2][2] > 0.25:
                        pt1 = (int(kpts[p1][0]), int(kpts[p1][1]))
                        pt2 = (int(kpts[p2][0]), int(kpts[p2][1]))
                        cv2.line(display, pt1, pt2, (230, 230, 230), 2)

                # 3. Gambar titik keypoints
                for j in range(17):
                    if kpts[j][2] > 0.25:
                        cv2.circle(display, (int(kpts[j][0]), int(kpts[j][1])), 4, (0, 255, 255), -1)

                # 4. Gambar garis tulang belakang khusus bahu-pinggul (atau leher-kepala)
                if sh_valid and hip_valid:
                    mid_sh = (int((kpts[5][0] + kpts[6][0]) / 2), int((kpts[5][1] + kpts[6][1]) / 2))
                    mid_hip = (int((kpts[11][0] + kpts[12][0]) / 2), int((kpts[11][1] + kpts[12][1]) / 2))
                    cv2.line(display, mid_sh, mid_hip, (255, 0, 255), 4)
                elif sh_valid and head_valid:
                    mid_sh = (int((kpts[5][0] + kpts[6][0]) / 2), int((kpts[5][1] + kpts[6][1]) / 2))
                    head_pt = (int(kpts[0][0]), int(kpts[0][1])) if kpts[0][2] > 0.25 else (int((kpts[1][0] + kpts[2][0]) / 2), int((kpts[1][1] + kpts[2][1]) / 2))
                    cv2.line(display, mid_sh, head_pt, (255, 100, 255), 3)

                # 5. Label teks per orang
                tag = f"{label_name} | {angle:.0f}deg [{src_label}] | AR:{ar:.2f} ({conf*100:.0f}%)"
                (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(display, (x1, max(0, y1 - 22)), (x1 + tw + 6, y1), color, -1)
                cv2.putText(display, tag, (x1 + 3, max(14, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        # Logika Trigger Auto-Screenshot Gesture
        now = time.time()
        cooldown_rem = SNAP_COOLDOWN - (now - last_snap_time)

        if auto_snap_enabled:
            if cooldown_rem <= 0 and countdown_start is None:
                if any_squeezed:
                    # Squeeze langsung memicu hitungan mundur
                    countdown_start = now
                elif any_raised:
                    # Tahan angkat tangan selama ~1 detik sebagai alternatif
                    if gesture_hold_start is None:
                        gesture_hold_start = now
                    elif now - gesture_hold_start >= 1.0:
                        countdown_start = now
                        gesture_hold_start = None
                else:
                    gesture_hold_start = None
            else:
                if countdown_start is None:
                    gesture_hold_start = None

            # Tampilkan visual countdown jika trigger aktif
            if countdown_start is not None:
                elapsed_cd = now - countdown_start
                rem_cd = COUNTDOWN_DURATION - elapsed_cd
                if rem_cd > 0:
                    cx, cy = display.shape[1] // 2, display.shape[0] // 2
                    overlay = display.copy()
                    cv2.circle(overlay, (cx, cy), 70, (0, 140, 255), -1)
                    cv2.addWeighted(overlay, 0.7, display, 0.3, 0, display)
                    cv2.circle(display, (cx, cy), 70, (255, 255, 255), 3)

                    cd_num = str(int(np.ceil(rem_cd)))
                    (tw, th), _ = cv2.getTextSize(cd_num, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 4)
                    cv2.putText(display, cd_num, (cx - tw // 2, cy + th // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4, cv2.LINE_AA)

                    info_txt = "BERSIAP SCREENSHOT..."
                    (iw, _), _ = cv2.getTextSize(info_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.putText(display, info_txt, (cx - iw // 2, cy + 105),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 215, 255), 2, cv2.LINE_AA)
                else:
                    # Hitungan mundur selesai: AMBIL SCREENSHOT
                    snap_path = out_dir / f"auto_snap_{primary_pred_name}_{int(now)}.jpg"
                    cv2.imwrite(str(snap_path), display)
                    print(f"📸 [AUTO-SCREENSHOT] Berhasil tersimpan: {snap_path}")
                    last_snap_time = now
                    countdown_start = None
                    flash_frames = 4  # Aktifkan efek visual flash kamera
        else:
            countdown_start = None
            gesture_hold_start = None

        # Efek visual flash kamera (layar putih sejenak)
        if flash_frames > 0:
            white_screen = np.full_like(display, 255)
            cv2.addWeighted(display, 0.3, white_screen, 0.7, 0, display)
            flash_frames -= 1

        # Header Dashboard Overlay
        rot_badge = "TTA ROTATION: [ON]" if rotate_mode else "TTA ROTATION: [OFF]"
        rot_color = (0, 255, 0) if rotate_mode else (180, 180, 180)

        smooth_badge = "1-EURO: [ON]" if smooth_mode else "1-EURO: [OFF]"
        smooth_color = (0, 255, 128) if smooth_mode else (150, 150, 150)

        # Status badge Auto-Screenshot
        if not auto_snap_enabled:
            auto_badge = "AUTO-SNAP: [OFF]"
            auto_color = (130, 130, 130)
        elif cooldown_rem > 0:
            auto_badge = f"AUTO-SNAP: [COOLDOWN {int(cooldown_rem)}s]"
            auto_color = (150, 150, 150)
        elif countdown_start is not None:
            auto_badge = "AUTO-SNAP: [📸 CAPTURING...]"
            auto_color = (0, 165, 255)
        elif any_squeezed:
            auto_badge = "AUTO-SNAP: [✊ SQUEEZE!]"
            auto_color = (0, 255, 255)
        elif any_raised:
            auto_badge = "AUTO-SNAP: [✋ RAISE DETECTED]"
            auto_color = (0, 215, 255)
        else:
            auto_badge = "AUTO-SNAP: [READY]"
            auto_color = (200, 200, 200)

        # Background bar atas
        cv2.rectangle(display, (0, 0), (display.shape[1], 52), (30, 30, 30), -1)
        cv2.putText(display, f"FPS: {fps:.1f} | People: {person_count} | Status: {primary_posture}",
                    (12, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.52, primary_color, 1, cv2.LINE_AA)
        cv2.putText(display, f"{rot_badge} | {smooth_badge} | {auto_badge} (r=rot, m=smooth, a=snap-tog, s=snap, q=exit)",
                    (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)

        cv2.imshow("Real Camera Test - YOLO11 Pose Fall Detection", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q") or key == 27:  # 27 = ESC
            break
        elif key == ord("r"):
            rotate_mode = not rotate_mode
            print(f"🔄 TTA Rotasi diubah menjadi: {'AKTIF (ON)' if rotate_mode else 'NONAKTIF (OFF)'}")
        elif key == ord("m"):
            smooth_mode = not smooth_mode
            if not smooth_mode:
                smoother.reset()
            print(f"✨ 1-Euro Keypoint Smoothing diubah menjadi: {'AKTIF (ON)' if smooth_mode else 'NONAKTIF (OFF)'}")
        elif key == ord("a"):
            auto_snap_enabled = not auto_snap_enabled
            countdown_start = None
            gesture_hold_start = None
            print(f"📸 Auto-Screenshot Gesture diubah menjadi: {'AKTIF (ON)' if auto_snap_enabled else 'NONAKTIF (OFF)'}")
        elif key == ord("s"):
            snap_path = out_dir / f"snap_{int(time.time())}.jpg"
            cv2.imwrite(str(snap_path), display)
            print(f"📸 Screenshot tersimpan: {snap_path}")

    cap.release()
    cv2.destroyAllWindows()
    print("👋 Pengujian kamera nyata selesai.")


if __name__ == "__main__":
    main()
