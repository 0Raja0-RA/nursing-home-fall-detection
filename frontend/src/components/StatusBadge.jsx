/**
 * StatusBadge.jsx
 * ===============
 * Badge kecil untuk menampilkan status (safe/warning/danger).
 * Digunakan di CameraFeedCard dan AlertHistory table.
 */

const STATUS_MAP = {
  safe: "badge--safe",
  warning: "badge--warning",
  danger: "badge--danger",
  critical: "badge--danger",
};

export default function StatusBadge({ status, label }) {
  const className = STATUS_MAP[status] || STATUS_MAP.safe;

  return (
    <span className={`badge ${className}`}>
      {status === "danger" || status === "critical" ? "●" : "●"} {label}
    </span>
  );
}
