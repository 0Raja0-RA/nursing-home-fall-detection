"""
occlusion_resistant_pose.py
===========================
EXP-011: Occlusion-Resistant Multi-Joint Kinematic Heuristics.

Mengevaluasi ketahanan sistem deteksi jatuh ketika sebagian tubuh lansia
terhalang (teroklusi) oleh ranjang, meja, kursi, atau selimut.

Membandingkan:
  1. Baseline Single-Pair Pose (Hanya mengandalkan Bahu-ke-Pinggul)
  2. Hierarchical Multi-Joint Estimator (Fallback adaptif: Kepala-Bahu, Bahu-Pinggul, Pinggul-Lutut, & Aspect Ratio)

Menguji performa di bawah 3 skenario oklusi:
  - Skenario 1: Full Visibility (Tanpa halangan)
  - Skenario 2: Lower-Body Occlusion (Kaki/Lutut/Pinggul terhalang meja/kasur rendah)
  - Skenario 3: Severe Occlusion (Hanya tubuh bagian atas / kepala-bahu yang terlihat)
"""

import math
import time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from ultralytics import YOLO

def vector_angle_to_horizontal(p1, p2) -> float:
    """Menghitung sudut kemiringan vektor dua titik (x, y) terhadap bidang horizontal lantai."""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    rad = math.atan2(abs(dy), abs(dx))
    return math.degrees(rad)

def baseline_spine_angle(kpts: np.ndarray, ar: float) -> tuple[float, str]:
    """Baseline EXP-009: Hanya mengandalkan sendi bahu (5,6) dan pinggul (11,12)."""
    sh_conf = (kpts[5][2] + kpts[6][2]) / 2.0
    hip_conf = (kpts[11][2] + kpts[12][2]) / 2.0
    
    if sh_conf > 0.25 and hip_conf > 0.25:
        mid_sh = ((kpts[5][0] + kpts[6][0]) / 2.0, (kpts[5][1] + kpts[6][1]) / 2.0)
        mid_hip = ((kpts[11][0] + kpts[12][0]) / 2.0, (kpts[11][1] + kpts[12][1]) / 2.0)
        return vector_angle_to_horizontal(mid_sh, mid_hip), "Shoulder-Hip"
    else:
        # Fallback kasar ke bounding box jika pinggul tidak terdeteksi
        fallback_angle = 90.0 if ar < 0.8 else (20.0 if ar > 1.15 else 50.0)
        return fallback_angle, "BBox-Fallback"

def hierarchical_angle_estimator(kpts: np.ndarray, ar: float) -> tuple[float, str]:
    """
    EXP-011 Hierarchical Multi-Joint Estimator:
    Menggunakan pohon keputusan bertingkat (*fallback hierarchy*) jika ada sendi yang terhalang.
    """
    # Confidence metrics
    head_conf = (kpts[0][2] + kpts[1][2] + kpts[2][2]) / 3.0  # Hidung & mata
    sh_conf = (kpts[5][2] + kpts[6][2]) / 2.0                  # Bahu
    hip_conf = (kpts[11][2] + kpts[12][2]) / 2.0                # Pinggul
    knee_conf = (kpts[13][2] + kpts[14][2]) / 2.0              # Lutut
    ankle_conf = (kpts[15][2] + kpts[16][2]) / 2.0            # Pergelangan kaki

    # Tingkat 1: Primary Spine (Bahu ke Pinggul)
    if sh_conf > 0.25 and hip_conf > 0.25:
        mid_sh = ((kpts[5][0] + kpts[6][0]) / 2.0, (kpts[5][1] + kpts[6][1]) / 2.0)
        mid_hip = ((kpts[11][0] + kpts[12][0]) / 2.0, (kpts[11][1] + kpts[12][1]) / 2.0)
        return vector_angle_to_horizontal(mid_sh, mid_hip), "Tier-1 (Spine)"

    # Tingkat 2: Upper Body Only (Kepala/Leher ke Bahu) — jika pinggul terhalang kasur
    if head_conf > 0.20 and sh_conf > 0.25:
        head_pt = (kpts[0][0], kpts[0][1])
        mid_sh = ((kpts[5][0] + kpts[6][0]) / 2.0, (kpts[5][1] + kpts[6][1]) / 2.0)
        # Offset anatomis: saat rebah, sudut kepala-bahu juga mendatar terhadap lantai
        angle = vector_angle_to_horizontal(head_pt, mid_sh)
        return angle, "Tier-2 (Head-Shoulder)"

    # Tingkat 3: Lower Body Only (Pinggul ke Lutut/Kaki) — jika tubuh atas terhalang selimut
    if hip_conf > 0.25 and (knee_conf > 0.20 or ankle_conf > 0.20):
        mid_hip = ((kpts[11][0] + kpts[12][0]) / 2.0, (kpts[11][1] + kpts[12][1]) / 2.0)
        p_lower = ((kpts[13][0] + kpts[14][0]) / 2.0, (kpts[13][1] + kpts[14][1]) / 2.0) if knee_conf > 0.20 else \
                  ((kpts[15][0] + kpts[16][0]) / 2.0, (kpts[15][1] + kpts[16][1]) / 2.0)
        angle = vector_angle_to_horizontal(mid_hip, p_lower)
        return angle, "Tier-3 (Hip-Legs)"

    # Tingkat 4: Full-Body Axis (Kepala ke Kaki) — jika bagian tengah tertutup
    if head_conf > 0.20 and ankle_conf > 0.20:
        head_pt = (kpts[0][0], kpts[0][1])
        mid_ank = ((kpts[15][0] + kpts[16][0]) / 2.0, (kpts[15][1] + kpts[16][1]) / 2.0)
        return vector_angle_to_horizontal(head_pt, mid_ank), "Tier-4 (Head-Ankle Axis)"

    # Tingkat 5: Aspect Ratio & Box Geometry
    fallback_angle = 90.0 if ar < 0.8 else (15.0 if ar > 1.15 else 50.0)
    return fallback_angle, "Tier-5 (Aspect Ratio)"

def evaluate_estimator_under_occlusion(img_dir: Path, model: YOLO, occlusion_mode: str = "none"):
    """
    Mengevaluasi akurasi dan ketahanan estimator pada dataset dengan simulasi oklusi.
    occlusion_mode:
      - 'none' : Kondisi asli tanpa halangan
      - 'lower': Kaki dan pinggul di-masking (mensimulasikan terhalang tempat tidur)
      - 'hips' : Hanya pinggul yang di-masking (mensimulasikan terhalang meja/sofa)
    """
    img_files = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
    
    baseline_correct = 0
    hierarchical_correct = 0
    total = 0
    tier_usage = defaultdict(int)
    
    for img_p in img_files:
        # Tentukan ground truth dari nama file (fall-* -> 1, adl-* -> 0)
        is_fall = 1 if img_p.name.startswith("fall") else 0
        
        res = model(str(img_p), verbose=False, conf=0.25)
        if not res or len(res[0].boxes) == 0:
            continue
            
        boxes = res[0].boxes
        best_idx = int(boxes.conf.argmax().item())
        kpts = res[0].keypoints.data[best_idx].cpu().numpy().copy()
        bbox = boxes.xyxy[best_idx].tolist()
        ar = max(1.0, bbox[2] - bbox[0]) / max(1.0, bbox[3] - bbox[1])
        
        # Simulasi oklusi dengan me-nol-kan confidence titik sendi tertentu
        if occlusion_mode == "lower":
            # Kaki, lutut, dan pinggul terhalang (kasur/meja)
            for idx in [11, 12, 13, 14, 15, 16]:
                kpts[idx][2] = 0.0
        elif occlusion_mode == "hips":
            # Pinggul terhalang
            for idx in [11, 12]:
                kpts[idx][2] = 0.0
                
        # 1. Baseline Decision
        b_angle, b_source = baseline_spine_angle(kpts, ar)
        b_pred = 1 if b_angle < 30.0 else 0
        if b_pred == is_fall:
            baseline_correct += 1
            
        # 2. Hierarchical Decision
        h_angle, h_source = hierarchical_angle_estimator(kpts, ar)
        tier_usage[h_source] += 1
        h_pred = 1 if h_angle < 30.0 else 0
        if h_pred == is_fall:
            hierarchical_correct += 1
            
        total += 1
        
    base_acc = baseline_correct / total if total > 0 else 0.0
    hier_acc = hierarchical_correct / total if total > 0 else 0.0
    return base_acc, hier_acc, total, tier_usage

def main():
    print("=" * 65)
    print("🛡️ EXP-011: OCCLUSION-RESISTANT MULTI-JOINT HEURISTICS")
    print("=" * 65)
    
    model = YOLO("yolo11n-pose.pt")
    
    dataset_dir = Path("ml/data/processed")
    if not dataset_dir.exists():
        dataset_dir = Path("../data/processed")
    test_img_dir = dataset_dir / "images" / "test"
    
    print(f"📁 Menguji pada Test Set: {test_img_dir}")
    
    scenarios = [
        ("Skenario 1: Full Visibility (Normal)", "none"),
        ("Skenario 2: Hip Occlusion (Terhalang Sofa/Meja)", "hips"),
        ("Skenario 3: Lower-Body Occlusion (Terhalang Ranjang)", "lower"),
    ]
    
    results = []
    
    for sc_name, sc_mode in scenarios:
        print(f"\n🔬 Menjalankan {sc_name}...")
        b_acc, h_acc, tot, tier_stats = evaluate_estimator_under_occlusion(test_img_dir, model, sc_mode)
        gain = (h_acc - b_acc) * 100
        results.append({
            "name": sc_name,
            "baseline_acc": b_acc * 100,
            "hierarchical_acc": h_acc * 100,
            "gain": gain,
            "tiers": dict(tier_stats)
        })
        print(f"  • Total frame dievaluasi : {tot}")
        print(f"  • Baseline Pose Acc      : {b_acc * 100:.2f}%")
        print(f"  • Hierarchical Pose Acc  : {h_acc * 100:.2f}% (Peningkatan: {gain:+.2f}%)")
        print(f"  • Distribusi Tier Aktif  : {dict(tier_stats)}")
        
    print("\n" + "=" * 65)
    print("📊 TABEL PERBANDINGAN KETAHANAN OKLUSI (TEST SET):")
    print("=" * 65)
    print(f"{'Skenario Halangan Objek':<40} | {'Baseline':<10} | {'Hierarchical':<14} | {'Gain':<8}")
    print("-" * 65)
    for r in results:
        print(f"{r['name']:<40} | {r['baseline_acc']:6.2f}%    | {r['hierarchical_acc']:6.2f}%       | {r['gain']:+5.2f}%")
    print("=" * 65)
    
    # Simpan Visualisasi Perbandingan
    output_dir = Path("ml/training/curves")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    labels = ["Full View", "Hip Occlusion", "Lower-Body Occluded"]
    b_scores = [r["baseline_acc"] for r in results]
    h_scores = [r["hierarchical_acc"] for r in results]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(9, 5))
    rects1 = ax.bar(x - width/2, b_scores, width, label='Baseline Pose (EXP-009)', color='#e74c3c')
    rects2 = ax.bar(x + width/2, h_scores, width, label='Hierarchical Multi-Joint (EXP-011)', color='#2ecc71')
    
    ax.set_ylabel('Akurasi Klasifikasi Postur (%)', fontsize=11)
    ax.set_title('Ketahanan Model terhadap Oklusi Objek Furnitur (EXP-011)', fontsize=12, weight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.legend(fontsize=10)
    ax.grid(axis='y', alpha=0.3)
    
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.1f}%',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, weight='bold')
                        
    autolabel(rects1)
    autolabel(rects2)
    
    plt.tight_layout()
    chart_path = output_dir / "exp011_occlusion_robustness.png"
    plt.savefig(chart_path, dpi=200)
    print(f"\n✅ Grafik perbandingan oklusi tersimpan di: {chart_path}")
    print("✨ EXP-011 SELESAI DENGAN SUKSES!")

if __name__ == "__main__":
    main()
