/**
 * Settings.jsx
 * ============
 * Halaman pengaturan: atur threshold durasi falling,
 * confidence threshold, dan konfigurasi lainnya.
 */

import { useState, useEffect } from "react";
import ThresholdSlider from "../components/ThresholdSlider";
import { getSettings, updateThreshold } from "../services/api";
import toast from "react-hot-toast";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [threshold, setThreshold] = useState(10);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings()
      .then((data) => {
        setSettings(data);
        setThreshold(data.fall_duration_threshold);
      })
      .catch((err) => console.error("Failed to fetch settings:", err));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await updateThreshold(threshold);
      setSettings(updated);
      toast.success(`Threshold updated: ${threshold}s`);
    } catch (err) {
      toast.error("Gagal menyimpan threshold");
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return <p style={{ color: "var(--color-text-muted)" }}>Loading settings...</p>;
  }

  return (
    <>
      <h2 className="page-title">Settings</h2>
      <p className="page-subtitle">Konfigurasi sistem fall detection</p>

      <div style={{ display: "grid", gap: "var(--space-xl)", maxWidth: 600 }}>
        {/* Threshold Slider */}
        <div className="card">
          <h3 style={{ marginBottom: "var(--space-md)", fontSize: "var(--font-size-lg)" }}>
            Fall Duration Threshold
          </h3>
          <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)", marginBottom: "var(--space-lg)" }}>
            Berapa lama (detik) postur "falling" harus berlangsung
            sebelum sistem mengirim notifikasi alert.
          </p>

          <ThresholdSlider
            value={threshold}
            onChange={setThreshold}
            min={1}
            max={60}
            unit="detik"
          />

          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
            style={{ marginTop: "var(--space-lg)" }}
          >
            {saving ? "Menyimpan..." : "Simpan Perubahan"}
          </button>
        </div>

        {/* Info cards */}
        <div className="card">
          <h3 style={{ marginBottom: "var(--space-md)", fontSize: "var(--font-size-lg)" }}>
            Konfigurasi Aktif
          </h3>
          <div style={{ display: "grid", gap: "var(--space-sm)" }}>
            <InfoRow label="Fall Duration Threshold" value={`${settings.fall_duration_threshold}s`} />
            <InfoRow label="Possible Fall Threshold" value={`${settings.possible_fall_threshold}s`} />
            <InfoRow label="Confidence Threshold" value={`${(settings.confidence_threshold * 100).toFixed(0)}%`} />
            <InfoRow label="Camera Source" value={settings.camera_source} />
          </div>
        </div>
      </div>
    </>
  );
}

/** Row komponen kecil untuk info display. */
function InfoRow({ label, value }) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "var(--space-sm) 0",
      borderBottom: "1px solid rgba(203, 166, 247, 0.05)",
    }}>
      <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>{label}</span>
      <span style={{ fontWeight: 600, fontSize: "var(--font-size-sm)" }}>{value}</span>
    </div>
  );
}
