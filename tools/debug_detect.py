"""
debug_detect.py
===============
Menampilkan SEMUA kotak mentah yang dikeluarkan model untuk satu frame, sebelum
disaring atau diterjemahkan sistem. Dipakai untuk membedakan dua kemungkinan
saat orang yang jatuh tidak terdeteksi:

  - modelnya sendiri tidak mengeluarkan kotak untuk orang itu (masalah model), atau
  - kotaknya ada tapi hilang di kode backend (masalah kode).

Pakai (dari root repo, backend dimatikan dulu kalau memakai webcam):

    .venv\\Scripts\\python.exe tools\\debug_detect.py 0                 # webcam
    .venv\\Scripts\\python.exe tools\\debug_detect.py foto.jpg
    .venv\\Scripts\\python.exe tools\\debug_detect.py video.mp4 --frame 120

Hasilnya dicetak dan disimpan sebagai debug_detect_<mode>.jpg di folder kerja.
"""

import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
BOBOT = ROOT / "ml" / "models" / "fall_detection" / "weights"


def ambil_frame(sumber: str, nomor: int):
    if sumber.isdigit():
        cap = cv2.VideoCapture(int(sumber), cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY)
        for _ in range(15):          # buang frame awal supaya eksposur stabil
            cap.read()
    elif Path(sumber).suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
        frame = cv2.imread(sumber)
        if frame is None:
            sys.exit(f"Tidak bisa membaca gambar: {sumber}")
        return frame
    else:
        cap = cv2.VideoCapture(sumber)
        cap.set(cv2.CAP_PROP_POS_FRAMES, nomor)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("Tidak bisa membaca frame dari sumber itu.")
    return frame


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("sumber", help="indeks webcam, path gambar, atau path video")
    p.add_argument("--frame", type=int, default=0, help="nomor frame (video saja)")
    args = p.parse_args()

    from ultralytics import YOLO

    frame = ambil_frame(args.sumber, args.frame)
    print(f"Ukuran frame: {frame.shape[1]}x{frame.shape[0]}\n")

    for mode, berkas in (("bbox", "best.pt"), ("pose", "yolo11n-pose.pt")):
        path = BOBOT / berkas
        if not path.exists():
            print(f"[{mode}] dilewati: {path} tidak ada\n")
            continue

        model = YOLO(str(path))
        # conf sangat rendah dan NMS dilonggarkan, supaya kotak yang biasanya
        # tersaring pun kelihatan.
        hasil = model(frame, verbose=False, conf=0.01, iou=0.95)[0]
        n = len(hasil.boxes)
        print(f"[{mode}] {n} kotak mentah (conf >= 0.01, iou=0.95)")
        for i in range(n):
            b = hasil.boxes
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[i].tolist())
            nama = model.names.get(int(b.cls[i]), "?")
            print(f"   #{i}: {nama:<16} conf={float(b.conf[i]):.2f}  "
                  f"kotak=({x1},{y1})-({x2},{y2})  lebar/tinggi={(x2-x1)/max(1,y2-y1):.2f}")
        print()

        cv2.imwrite(f"debug_detect_{mode}.jpg", hasil.plot())
        print(f"   gambar disimpan: debug_detect_{mode}.jpg\n")


if __name__ == "__main__":
    main()
