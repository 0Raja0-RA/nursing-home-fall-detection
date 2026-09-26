"""
preview_dataset.py
==================
Visualisasi preview sampel dataset yang sudah diproses:
1. Mengambil sampel gambar dari masing-masing kelas (normal, transitional, lying_on_ground).
2. Membaca anotasi bounding box (.txt) format YOLO.
3. Menggambar bounding box + label warna berbeda:
   - Hijau  : normal
   - Oranye : transitional
   - Merah  : lying_on_ground
4. Menggabungkan sampel menjadi 1 gambar grid preview (preview_grid.jpg).

Penggunaan:
    python ml/scripts/preview_dataset.py
"""

from pathlib import Path
import cv2
import numpy as np

# Warna BGR untuk tiap kelas
COLORS = {
    0: (46, 204, 113),   # Hijau (normal)
    1: (39, 174, 96),    # Oranye/Kuning (transitional)
    2: (0, 0, 230)       # Merah (lying_on_ground)
}

CLASS_NAMES = ["normal", "transitional", "lying_on_ground"]


def draw_yolo_bbox(img: np.ndarray, label_file: Path) -> np.ndarray:
    """Gambar bounding box YOLO pada gambar."""
    img_out = img.copy()
    h_img, w_img = img.shape[:2]

    if not label_file.exists():
        return img_out

    with open(label_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        cls_id = int(parts[0])
        xc, yc, w, h = map(float, parts[1:5])

        # Denormalisasi ke pixel
        x1 = int((xc - w / 2) * w_img)
        y1 = int((yc - h / 2) * h_img)
        x2 = int((xc + w / 2) * w_img)
        y2 = int((yc + h / 2) * h_img)

        color = COLORS.get(cls_id, (255, 255, 255))
        label_text = f"{CLASS_NAMES[cls_id].upper()} (cls {cls_id})"

        # Gambar box
        cv2.rectangle(img_out, (x1, y1), (x2, y2), color, 3)

        # Background text banner
        text_size, _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(
            img_out,
            (x1, max(0, y1 - text_size[1] - 10)),
            (x1 + text_size[0] + 10, y1),
            color,
            -1
        )
        # Text label
        cv2.putText(
            img_out,
            label_text,
            (x1 + 5, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

    return img_out


def main():
    base_dir = Path("ml/data/processed")
    images_dir = base_dir / "images"
    labels_dir = base_dir / "labels"

    if not images_dir.exists():
        print(f"[ERROR] Folder {images_dir} tidak ditemukan! Jalankan prepare_urfall.py dulu.")
        return

    # Cari 1 sampel per kelas dari split train
    samples_per_class = {0: None, 1: None, 2: None}

    # Telusuri split train, lalu val
    for split in ["train", "val", "test"]:
        lbl_dir = labels_dir / split
        img_dir = images_dir / split

        for txt_file in sorted(lbl_dir.glob("*.txt")):
            with open(txt_file, "r") as f:
                first_line = f.readline().strip()
                if not first_line:
                    continue
                cls_id = int(first_line.split()[0])
                if cls_id in samples_per_class and samples_per_class[cls_id] is None:
                    corresponding_img = img_dir / f"{txt_file.stem}.jpg"
                    if corresponding_img.exists():
                        samples_per_class[cls_id] = (corresponding_img, txt_file)

            if all(v is not None for v in samples_per_class.values()):
                break
        if all(v is not None for v in samples_per_class.values()):
            break

    print("============================================================")
    print("[INFO] MEMBUAT PREVIEW ANOTASI DATASET")
    print("============================================================")

    rendered_images = []
    target_width = 480
    target_height = 360

    for cls_id in [0, 1, 2]:
        item = samples_per_class[cls_id]
        if item is None:
            print(f"[WARN] Tidak ditemukan sampel untuk kelas {CLASS_NAMES[cls_id]}")
            continue

        img_path, lbl_path = item
        img = cv2.imread(str(img_path))
        annotated = draw_yolo_bbox(img, lbl_path)

        # Resize untuk grid seragam
        resized = cv2.resize(annotated, (target_width, target_height))
        rendered_images.append(resized)

        print(f"  + Kelas [{CLASS_NAMES[cls_id]:<16}]: {img_path.name}")

    if rendered_images:
        # Gabungkan secara horizontal
        grid = np.hstack(rendered_images)
        out_preview_path = base_dir / "preview_grid.jpg"
        cv2.imwrite(str(out_preview_path), grid)
        print("============================================================")
        print(f"[DONE] Preview berhasil disimpan di: {out_preview_path.resolve()}")
        print(f"       Dimensi Grid: {grid.shape[1]}x{grid.shape[0]} pixel")
        print("============================================================")


if __name__ == "__main__":
    main()
