"""
demo_pose_fall.py
=================
Prototipe Deteksi Jatuh Berbasis YOLO11-Pose (Keypoint Skeleton Estimation).

Mendeteksi 17 titik sendi manusia dan menghitung sudut kemiringan tulang
belakang (spine tilt angle) terhadap bidang horizontal lantai untuk
menentukan apakah seseorang sedang berdiri, membungkuk, atau jatuh terbaring.

Keunggulan:
- Kebal terhadap false positive perabotan (kursi/kasur/selimut) karena
  benda mati tidak memiliki sendi manusia.
- Tidak memerlukan dataset anotasi baru (menggunakan bobot pretrained COCO).
- Multi-person support secara simultan.

Penggunaan:
    python ml/scripts/demo_pose_fall.py
    python ml/scripts/demo_pose_fall.py --source 0
    python ml/scripts/demo_pose_fall.py --source path/to/video.mp4
"""

import argparse
import math
import sys
import time

import cv2
import numpy as np
from ultralytics import YOLO

# Indeks keypoints standar COCO:
# 0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
# 5: left_shoulder, 6: right_shoulder, 7: left_elbow, 8: right_elbow
# 9: left_wrist, 10: right_wrist, 11: left_hip, 12: right_hip
# 13: left_knee, 14: right_knee, 15: left_ankle, 16: right_ankle

SKELETON_PAIRS = [
    (5, 6),   # Bahu kiri - kanan
    (5, 7), (7, 9),    # Lengan kiri
    (6, 8), (8, 10),   # Lengan kanan
    (5, 11), (6, 12),  # Badan (bahu ke pinggul)
    (11, 12),          # Pinggul kiri - kanan
    (11, 13), (13, 15),# Kaki kiri
    (12, 14), (14, 16),# Kaki kanan
]


def calculate_spine_angle(kpts: np.ndarray) -> tuple[float, tuple[int, int], tuple[int, int]]:
    """Menghitung sudut kemiringan tulang belakang terhadap garis horizontal lantai.

    Returns:
        angle_deg: Sudut terhadap bidang horizontal (0° = tidur rata, 90° = tegak lurus).
        mid_shoulder: Koordinat (x, y) tengah bahu.
        mid_hip: Koordinat (x, y) tengah pinggul.
    """
    # Keypoints bahu (5, 6) dan pinggul (11, 12)
    l_sh, r_sh = kpts[5][:2], kpts[6][:2]
    l_hip, r_hip = kpts[11][:2], kpts[12][:2]

    # Titik tengah bahu dan pinggul
    mid_sh = ((l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2)
    mid_hip = ((l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2)

    dx = mid_sh[0] - mid_hip[0]
    dy = mid_sh[1] - mid_hip[1]

    # Sudut terhadap horizontal (0° - 90°)
    rad = math.atan2(abs(dy), abs(dx))
    angle_deg = math.degrees(rad)

    return angle_deg, (int(mid_sh[0]), int(mid_sh[1])), (int(mid_hip[0]), int(mid_hip[1]))


def classify_pose(angle_deg: float, bbox: list[float]) -> tuple[str, tuple[int, int, int]]:
    """Klasifikasi postur berdasarkan sudut tulang belakang dan rasio bounding box."""
    x1, y1, x2, y2 = bbox
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    aspect_ratio = w / h  # > 1.0 berarti lebih lebar daripada tinggi (khas orang tidur)

    # Threshold heuristik kinematika klinis:
    # 1. Sudut tulang belakang < 35° (hampir horizontal) ATAU tubuh melebar horizontal dengan sudut < 45°
    if angle_deg < 35.0 or (aspect_ratio > 1.25 and angle_deg < 48.0):
        return "FALL / LYING", (50, 50, 255)  # Merah
    elif angle_deg < 55.0 or aspect_ratio > 0.95:
        return "TRANSITIONAL / BENDING", (0, 215, 255)  # Kuning
    else:
        return "NORMAL / UPRIGHT", (46, 204, 113)  # Hijau


def main():
    parser = argparse.ArgumentParser(description="Demo Fall Detection via YOLO11-Pose")
    parser.add_argument("--source", type=str, default="0", help="Webcam index (0) atau path file video")
    parser.add_argument("--model", type=str, default="yolo11n-pose.pt", help="Model pose (yolo11n-pose.pt / yolo11s-pose.pt)")
    parser.add_argument("--conf", type=float, default=0.4, help="Confidence threshold")
    args = parser.parse_args()

    print(f"🚀 Memuat model Pose: {args.model}...")
    model = YOLO(args.model)

    src = int(args.source) if args.source.isdigit() else args.source
    if isinstance(src, int) and sys.platform.startswith("win"):
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(src)
    else:
        cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"❌ Gagal membuka kamera/video: {args.source}")
        return

    print("✅ Kamera aktif. Tekan 'q' di jendela video untuk keluar.")
    fps_start = time.time()
    frame_count = 0
    fps = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Video stream selesai atau tidak ada frame.")
            break

        frame_count += 1
        elapsed = time.time() - fps_start
        if elapsed >= 1.0:
            fps = frame_count / elapsed
            frame_count = 0
            fps_start = time.time()

        # Inference YOLO Pose
        results = model(frame, verbose=False, conf=args.conf)
        display = frame.copy()

        person_count = 0

        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            keypoints_data = results[0].keypoints

            for i in range(len(boxes)):
                person_count += 1
                bbox = boxes.xyxy[i].tolist()
                conf = float(boxes.conf[i].item())
                kpts = keypoints_data.data[i].cpu().numpy()  # shape: (17, 3) -> [x, y, conf]

                x1, y1, x2, y2 = map(int, bbox)

                # Hitung sudut tulang belakang
                # Validasi jika keypoints bahu & pinggul terdeteksi dengan confidence cukup
                sh_conf = (kpts[5][2] + kpts[6][2]) / 2
                hip_conf = (kpts[11][2] + kpts[12][2]) / 2

                if sh_conf > 0.3 and hip_conf > 0.3:
                    angle, mid_sh, mid_hip = calculate_spine_angle(kpts)
                    posture_label, color = classify_pose(angle, bbox)

                    # Gambar garis tulang belakang
                    cv2.line(display, mid_sh, mid_hip, (255, 0, 255), 3)
                    cv2.circle(display, mid_sh, 5, (255, 0, 0), -1)
                    cv2.circle(display, mid_hip, 5, (0, 0, 255), -1)
                else:
                    # Fallback ke aspect ratio jika sendi utama terhalang
                    w = max(1, x2 - x1)
                    h = max(1, y2 - y1)
                    aspect_ratio = w / h
                    angle = 90.0 if aspect_ratio < 0.8 else (30.0 if aspect_ratio > 1.3 else 50.0)
                    posture_label, color = classify_pose(angle, bbox)

                # Gambar bounding box orang
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)

                # Gambar rangka skeleton sendi
                for p1, p2 in SKELETON_PAIRS:
                    if kpts[p1][2] > 0.3 and kpts[p2][2] > 0.3:
                        pt1 = (int(kpts[p1][0]), int(kpts[p1][1]))
                        pt2 = (int(kpts[p2][0]), int(kpts[p2][1]))
                        cv2.line(display, pt1, pt2, (200, 200, 200), 2)

                for k in range(len(kpts)):
                    if kpts[k][2] > 0.3:
                        cv2.circle(display, (int(kpts[k][0]), int(kpts[k][1])), 4, (0, 255, 255), -1)

                # Label teks status di atas bounding box
                tag = f"{posture_label} | {angle:.0f} deg ({conf*100:.0f}%)"
                cv2.rectangle(display, (x1, max(0, y1 - 26)), (x1 + len(tag) * 10, y1), color, -1)
                cv2.putText(
                    display, tag, (x1 + 4, max(18, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2
                )

        # Header Info Overlay
        cv2.putText(display, f"YOLO11-Pose Fall Detector | FPS: {fps:.1f} | People: {person_count}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Fall Detection - YOLO11 Pose Estimation", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("👋 Sesi demo pose selesai.")


if __name__ == "__main__":
    main()
