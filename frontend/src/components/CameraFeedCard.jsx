/**
 * CameraFeedCard.jsx
 * ==================
 * Kartu status per kamera di dashboard.
 *
 * Menampilkan: camera ID, postur terdeteksi, fall state,
 * durasi falling (jika ada), confidence, dan FPS.
 *
 * Kartu berubah style saat ada danger state (glow merah + animasi).
 */

import StatusBadge from "./StatusBadge";

/** Mapping posture class ke style variant (UR Fall labels) */
const POSTURE_STYLE = {
  normal: { badge: "safe", icon: "🚶", label: "Normal" },
  transitional: { badge: "warning", icon: "⚡", label: "Transitional" },
  lying_on_ground: { badge: "danger", icon: "🚨", label: "Lying on Ground" },
};

/** Mapping fall state ke style variant */
const STATE_STYLE = {
  monitoring: { badge: "safe", label: "Monitoring" },
  possible_fall: { badge: "warning", label: "Possible Fall" },
  confirmed_fall: { badge: "danger", label: "CONFIRMED FALL" },
};

export default function CameraFeedCard({ camera }) {
  const {
    camera_id,
    current_posture,
    fall_state = "monitoring",
    fall_duration = 0,
    confidence = 0,
    fps = 0,
    is_active = true,
  } = camera;

  const isDanger = fall_state === "confirmed_fall";
  const postureInfo = POSTURE_STYLE[current_posture] || { badge: "safe", icon: "❓" };
  const stateInfo = STATE_STYLE[fall_state] || STATE_STYLE.monitoring;

  return (
    <div className={`card ${isDanger ? "card--danger" : ""}`}>
      {/* Header */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "var(--space-md)",
      }}>
        <h3 style={{ fontSize: "var(--font-size-base)", fontWeight: 600 }}>
          📷 {camera_id}
        </h3>
        <StatusBadge
          status={is_active ? "safe" : "danger"}
          label={is_active ? "Active" : "Offline"}
        />
      </div>

      {/* Posture Display */}
      <div style={{
        textAlign: "center",
        padding: "var(--space-lg) 0",
        borderRadius: "var(--radius-md)",
        background: "var(--color-surface-1)",
        marginBottom: "var(--space-md)",
      }}>
        <div style={{ fontSize: "2.5rem", marginBottom: "var(--space-sm)" }}>
          {postureInfo.icon}
        </div>
        <StatusBadge
          status={postureInfo.badge}
          label={current_posture || "No detection"}
        />
      </div>

      {/* Fall State */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "var(--space-sm)",
      }}>
        <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
          Fall State
        </span>
        <StatusBadge status={stateInfo.badge} label={stateInfo.label} />
      </div>

      {/* Fall Duration (hanya tampilkan jika ada falling) */}
      {fall_state !== "monitoring" && (
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-sm)",
        }}>
          <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
            Duration
          </span>
          <span style={{
            fontWeight: 700,
            fontSize: "var(--font-size-lg)",
            color: isDanger ? "var(--color-danger)" : "var(--color-warning)",
          }}>
            {fall_duration.toFixed(1)}s
          </span>
        </div>
      )}

      {/* Stats Row */}
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        paddingTop: "var(--space-sm)",
        borderTop: "1px solid rgba(203, 166, 247, 0.05)",
        marginTop: "var(--space-sm)",
      }}>
        <span style={{ color: "var(--color-text-subtle)", fontSize: "var(--font-size-xs)" }}>
          Confidence: {(confidence * 100).toFixed(0)}%
        </span>
        <span style={{ color: "var(--color-text-subtle)", fontSize: "var(--font-size-xs)" }}>
          {fps.toFixed(1)} FPS
        </span>
      </div>
    </div>
  );
}
