/**
 * AlertBanner.jsx
 * ===============
 * Banner notifikasi yang muncul di atas dashboard saat ada
 * fall confirmed. Dengan animasi slide-in dan auto-dismiss.
 */

import { MdWarning, MdClose } from "react-icons/md";

export default function AlertBanner({ alert, onDismiss }) {
  if (!alert) return null;

  return (
    <div
      style={{
        background: "var(--gradient-danger)",
        color: "white",
        padding: "var(--space-md) var(--space-xl)",
        borderRadius: "var(--radius-md)",
        marginBottom: "var(--space-lg)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        boxShadow: "var(--shadow-glow-danger)",
        animation: "slideIn 0.3s ease-out",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
        <MdWarning size={28} />
        <div>
          <strong style={{ fontSize: "var(--font-size-lg)" }}>
            🚨 Fall Detected!
          </strong>
          <p style={{ fontSize: "var(--font-size-sm)", opacity: 0.9, marginTop: 2 }}>
            Kamera {alert.camera_id} — Durasi: {alert.fall_duration?.toFixed(1)}s
            {alert.message && ` — ${alert.message}`}
          </p>
        </div>
      </div>

      <button
        onClick={onDismiss}
        style={{
          background: "rgba(255,255,255,0.2)",
          border: "none",
          borderRadius: "var(--radius-sm)",
          color: "white",
          padding: "var(--space-xs)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          transition: "background var(--transition-fast)",
        }}
        onMouseEnter={(e) => (e.target.style.background = "rgba(255,255,255,0.3)")}
        onMouseLeave={(e) => (e.target.style.background = "rgba(255,255,255,0.2)")}
      >
        <MdClose size={20} />
      </button>

      <style>{`
        @keyframes slideIn {
          from { transform: translateY(-20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
