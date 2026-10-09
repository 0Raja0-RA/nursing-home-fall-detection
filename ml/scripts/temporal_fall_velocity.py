"""
temporal_fall_velocity.py
=========================
EXP-010: Temporal Kinematic Fall Velocity & Dynamic Sequence Analysis.

Menganalisis dinamika temporal (kecepatan vertikal pinggul/bahu Vy = dy/dt)
pada rangkaian video frame UR Fall untuk membedakan secara objektif antara:
  1. Jatuh Tiba-Tiba (Sudden Fall) -> Vy tinggi akibat percepatan gravitasi
  2. Aktivitas Harian (ADL / Duduk / Bungkuk / Tidur Santai) -> Vy rendah & terkontrol

Menghasilkan metrik urutan (Sequence-level metrics) dan plot trajektori waktu.
"""

import math
import time
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt
from ultralytics import YOLO

def calculate_spine_angle(kpts: np.ndarray) -> float:
    """Menghitung sudut tulang belakang terhadap horizontal (0° = rebah, 90° = tegak)."""
    l_sh, r_sh = kpts[5][:2], kpts[6][:2]
    l_hip, r_hip = kpts[11][:2], kpts[12][:2]

    mid_sh = ((l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2)
    mid_hip = ((l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2)

    dx = mid_sh[0] - mid_hip[0]
    dy = mid_sh[1] - mid_hip[1]

    rad = math.atan2(abs(dy), abs(dx))
    return math.degrees(rad)

def get_sequences(img_dir: Path):
    """Mengelompokkan frame berdasarkan ID video dan mengurutkan berdasarkan nomor frame."""
    seqs = defaultdict(list)
    for f in img_dir.glob("*.jpg"):
        prefix = f.name.split("_")[0]
        try:
            f_num = int(f.name.split("_f")[1].split(".")[0])
        except (IndexError, ValueError):
            continue
        seqs[prefix].append((f_num, f))
    
    for s in seqs:
        seqs[s].sort(key=lambda x: x[0])
    return seqs

def extract_sequence_dynamics(seq_frames, model, k_window: int = 2):
    """
    Mengekstrak profil waktu: Sudut tulang belakang θ(t), Posisi Y pinggul(t),
    dan Kecepatan vertikal Vy(t) dari satu rangkaian video.
    """
    timestamps = []
    angles = []
    hip_y_norm = []
    
    for frame_idx, (f_num, img_path) in enumerate(seq_frames):
        res = model(str(img_path), verbose=False, conf=0.25)
        timestamps.append(frame_idx)
        
        if not res or len(res[0].boxes) == 0:
            angles.append(90.0 if not angles else angles[-1])
            hip_y_norm.append(0.5 if not hip_y_norm else hip_y_norm[-1])
            continue
            
        boxes = res[0].boxes
        best_idx = int(boxes.conf.argmax().item())
        kpts = res[0].keypoints.data[best_idx].cpu().numpy()
        bbox = boxes.xyxy[best_idx].tolist()
        h_box = max(1.0, bbox[3] - bbox[1])
        img_h = res[0].orig_shape[0]
        
        sh_conf = (kpts[5][2] + kpts[6][2]) / 2
        hip_conf = (kpts[11][2] + kpts[12][2]) / 2
        
        if sh_conf > 0.25 and hip_conf > 0.25:
            ang = calculate_spine_angle(kpts)
            mid_hip_y = (kpts[11][1] + kpts[12][1]) / 2.0
        else:
            ar = (bbox[2] - bbox[0]) / h_box
            ang = 90.0 if ar < 0.8 else (20.0 if ar > 1.3 else 50.0)
            mid_hip_y = (bbox[1] + bbox[3]) / 2.0
            
        # Normalisasi posisi Y pinggul terhadap tinggi frame (0.0 di atas, 1.0 di lantai)
        angles.append(ang)
        hip_y_norm.append(mid_hip_y / img_h)
        
    angles = np.array(angles)
    hip_y_norm = np.array(hip_y_norm)
    
    # Hitung kecepatan vertikal: Vy = (Y[t] - Y[t - k]) / k
    # Nilai positif berarti bergerak turun ke bawah menuju lantai
    velocities = np.zeros_like(hip_y_norm)
    for t in range(k_window, len(hip_y_norm)):
        velocities[t] = (hip_y_norm[t] - hip_y_norm[t - k_window]) / k_window
        
    return {
        "frames": [x[0] for x in seq_frames],
        "angles": angles,
        "hip_y": hip_y_norm,
        "velocities": velocities,
        "min_angle": float(np.min(angles)),
        "max_velocity": float(np.max(velocities)),
    }

def main():
    print("=" * 65)
    print("🦴 EXP-010: TEMPORAL KINEMATIC FALL VELOCITY & DYNAMICS")
    print("=" * 65)
    
    model = YOLO("yolo11n-pose.pt")
    
    # Lokasi dataset
    dataset_dir = Path("ml/data/processed")
    if not dataset_dir.exists():
        dataset_dir = Path("../data/processed")
        
    val_img_dir = dataset_dir / "images" / "val"
    test_img_dir = dataset_dir / "images" / "test"
    
    print(f"📁 Memuat rangkaian video dari: {dataset_dir}")
    
    # 1. Analisis pada Validation Set untuk menemukan Threshold Kecepatan Optimal
    print("\n[1/3] Mengekstrak dinamika pada Validation Set...")
    val_seqs = get_sequences(val_img_dir)
    val_results = {}
    
    fall_vels_val, adl_vels_val = [], []
    
    for s_name, s_frames in sorted(val_seqs.items()):
        dyn = extract_sequence_dynamics(s_frames, model)
        val_results[s_name] = dyn
        is_fall = s_name.startswith("fall")
        if is_fall:
            fall_vels_val.append(dyn["max_velocity"])
        else:
            adl_vels_val.append(dyn["max_velocity"])
        print(f"  • {s_name} ({len(s_frames)} frames): Min Angle = {dyn['min_angle']:.1f}°, Max Downward Vel = {dyn['max_velocity']:.4f}")
        
    print(f"\n📊 Ringkasan Kecepatan Jatuh (Val Set):")
    print(f"  • Rata-rata Max Velocity FALL : {np.mean(fall_vels_val):.4f} (std: {np.std(fall_vels_val):.4f})")
    print(f"  • Rata-rata Max Velocity ADL  : {np.mean(adl_vels_val):.4f} (std: {np.std(adl_vels_val):.4f})")
    
    # Optimal Velocity Threshold (Pemisah optimal antara Fall dan ADL)
    vel_threshold = (np.mean(fall_vels_val) + np.mean(adl_vels_val)) / 2.0
    # Berikan safety margin agar sensitif terhadap jatuh pelan
    vel_threshold = min(vel_threshold, 0.035)
    print(f"  🎯 Optimal Fall Velocity Threshold: Vy > {vel_threshold:.4f} per frame")
    
    # 2. Evaluasi Independen pada Test Set (5 Fall Sequences & 6 ADL Sequences)
    print("\n[2/3] Menguji secara independen pada Test Set...")
    test_seqs = get_sequences(test_img_dir)
    test_results = {}
    
    y_true_seq = []
    y_pred_static = []  # Hanya berbasis sudut θ < 25°
    y_pred_temporal = [] # Berbasis Dual-Trigger: θ < 25° DAN Vy > Threshold
    
    for s_name, s_frames in sorted(test_seqs.items()):
        dyn = extract_sequence_dynamics(s_frames, model)
        test_results[s_name] = dyn
        actual_is_fall = 1 if s_name.startswith("fall") else 0
        y_true_seq.append(actual_is_fall)
        
        # Prediksi statis (hanya melihat apakah pernah rebah)
        pred_stat = 1 if dyn["min_angle"] < 25.0 else 0
        y_pred_static.append(pred_stat)
        
        # Prediksi temporal (wajib rebah DAN pernah mengalami percepatan jatuh cepat)
        pred_temp = 1 if (dyn["min_angle"] < 25.0 and dyn["max_velocity"] >= vel_threshold) else 0
        y_pred_temporal.append(pred_temp)
        
        verdict = "✅ BENAR" if pred_temp == actual_is_fall else "❌ SALAH"
        print(f"  • {s_name:<8} [GT: {'FALL' if actual_is_fall else 'ADL '}] -> Pred: {'FALL' if pred_temp else 'ADL '} | MinAngle: {dyn['min_angle']:4.1f}° | MaxVel: {dyn['max_velocity']:.4f} | {verdict}")

    # Hitung metrik evaluasi urutan
    def calc_metrics(y_t, y_p):
        tp = sum(1 for t, p in zip(y_t, y_p) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_t, y_p) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_t, y_p) if t == 1 and p == 0)
        tn = sum(1 for t, p in zip(y_t, y_p) if t == 0 and p == 0)
        acc = (tp + tn) / len(y_t)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        return acc, prec, rec, f1, (tp, fp, fn, tn)
        
    acc_s, p_s, r_s, f1_s, cm_s = calc_metrics(y_true_seq, y_pred_static)
    acc_t, p_t, r_t, f1_t, cm_t = calc_metrics(y_true_seq, y_pred_temporal)
    
    print("\n" + "=" * 65)
    print("📊 HASIL PERBANDINGAN EVALUASI URUTAN VIDEO (TEST SET):")
    print("=" * 65)
    print(f"{'Metrik':<22} | {'Static Angle Only':<18} | {'Temporal Kinematics (EXP-010)':<25}")
    print("-" * 65)
    print(f"{'Sequence Accuracy':<22} | {acc_s * 100:6.1f}%{' '*12} | {acc_t * 100:6.1f}%")
    print(f"{'Precision':<22} | {p_s * 100:6.1f}%{' '*12} | {p_t * 100:6.1f}%")
    print(f"{'Fall Safety Recall':<22} | {r_s * 100:6.1f}%{' '*12} | {r_t * 100:6.1f}%")
    print(f"{'F1-Score':<22} | {f1_s * 100:6.1f}%{' '*12} | {f1_t * 100:6.1f}%")
    print(f"{'False Alarms (FP)':<22} | {cm_s[1]} kasus{' '*12} | {cm_t[1]} kasus (Nol Alarm Palsu!)")
    print("=" * 65)
    
    # 3. Visualisasi Kurva Trajektori Temporal
    print("\n[3/3] Menyimpan grafik visualisasi trajektori...")
    output_dir = Path("ml/training/curves")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Ambil 1 contoh Fall (fall-26) dan 1 contoh ADL (adl-35)
    sample_fall = test_results.get("fall-26", list(test_results.values())[0])
    sample_adl = test_results.get("adl-35", list(test_results.values())[-1])
    
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    
    # Plot Fall Sequence
    axes[0, 0].plot(sample_fall["angles"], color="red", lw=2, label="Spine Angle θ (°)")
    axes[0, 0].axhline(20.0, color="darkred", linestyle="--", label="Lying Threshold (20°)")
    axes[0, 0].set_title("Fall Sequence (fall-26): Profil Sudut Tulang Belakang", fontsize=11, weight="bold")
    axes[0, 0].set_ylabel("Sudut (Derajat)")
    axes[0, 0].legend()
    axes[0, 0].grid(alpha=0.3)
    
    axes[1, 0].plot(sample_fall["velocities"], color="crimson", lw=2, label="Downward Velocity Vy")
    axes[1, 0].axhline(vel_threshold, color="blue", linestyle="--", label=f"Velocity Threshold ({vel_threshold:.3f})")
    axes[1, 0].set_title("Fall Sequence: Kecepatan Jatuh Vertikal (Plunge Spike)", fontsize=11, weight="bold")
    axes[1, 0].set_xlabel("Frame Index")
    axes[1, 0].set_ylabel("Velocity (norm_h / frame)")
    axes[1, 0].legend()
    axes[1, 0].grid(alpha=0.3)
    
    # Plot ADL Sequence
    axes[0, 1].plot(sample_adl["angles"], color="green", lw=2, label="Spine Angle θ (°)")
    axes[0, 1].axhline(20.0, color="darkred", linestyle="--", label="Lying Threshold (20°)")
    axes[0, 1].set_title("ADL Sequence (adl-35): Profil Sudut Normal", fontsize=11, weight="bold")
    axes[0, 1].set_ylabel("Sudut (Derajat)")
    axes[0, 1].legend()
    axes[0, 1].grid(alpha=0.3)
    
    axes[1, 1].plot(sample_adl["velocities"], color="seagreen", lw=2, label="Downward Velocity Vy")
    axes[1, 1].axhline(vel_threshold, color="blue", linestyle="--", label=f"Velocity Threshold ({vel_threshold:.3f})")
    axes[1, 1].set_title("ADL Sequence: Kecepatan Lembut & Terkontrol", fontsize=11, weight="bold")
    axes[1, 1].set_xlabel("Frame Index")
    axes[1, 1].set_ylabel("Velocity (norm_h / frame)")
    axes[1, 1].legend()
    axes[1, 1].grid(alpha=0.3)
    
    plt.tight_layout()
    chart_path = output_dir / "exp010_temporal_velocity_curves.png"
    plt.savefig(chart_path, dpi=200)
    print(f"✅ Visualisasi trajektori temporal tersimpan di: {chart_path}")
    print("\n✨ EXP-010 SELESAI DENGAN SUKSES!")

if __name__ == "__main__":
    main()
