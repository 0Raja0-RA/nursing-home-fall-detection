/**
 * AlertHistory.jsx
 * ================
 * Halaman riwayat alert (notifikasi jatuh).
 *
 * Menampilkan tabel alert dengan pagination dan filter
 * berdasarkan status acknowledged.
 */

import { useState, useEffect, useCallback } from "react";
import StatusBadge from "../components/StatusBadge";
import { getAlerts, acknowledgeAlert } from "../services/api";

export default function AlertHistory() {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState(null); // null = all, true/false
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);

  const PAGE_SIZE = 20;

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAlerts({
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        acknowledged: filter,
      });
      setAlerts(data);
    } catch (err) {
      console.error("Failed to fetch alerts:", err);
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const handleAck = async (alertId) => {
    try {
      await acknowledgeAlert(alertId);
      fetchAlerts(); // Refresh list
    } catch (err) {
      console.error("Failed to acknowledge:", err);
    }
  };

  return (
    <>
      <h2 className="page-title">Alert History</h2>
      <p className="page-subtitle">Riwayat semua notifikasi jatuh yang terdeteksi</p>

      {/* Filter buttons */}
      <div style={{ display: "flex", gap: "var(--space-sm)", marginBottom: "var(--space-lg)" }}>
        <button
          className={`btn ${filter === null ? "btn-primary" : "btn-ghost"}`}
          onClick={() => { setFilter(null); setPage(0); }}
        >
          Semua
        </button>
        <button
          className={`btn ${filter === false ? "btn-danger" : "btn-ghost"}`}
          onClick={() => { setFilter(false); setPage(0); }}
        >
          Belum Ditangani
        </button>
        <button
          className={`btn ${filter === true ? "btn-primary" : "btn-ghost"}`}
          onClick={() => { setFilter(true); setPage(0); }}
        >
          Sudah Ditangani
        </button>
      </div>

      {/* Table */}
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Kamera</th>
              <th>Durasi Jatuh</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Waktu</th>
              <th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} style={{ textAlign: "center", padding: "2rem" }}>
                  Loading...
                </td>
              </tr>
            ) : alerts.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: "center", padding: "2rem", color: "var(--color-text-muted)" }}>
                  Belum ada alert.
                </td>
              </tr>
            ) : (
              alerts.map((alert) => (
                <tr key={alert.id}>
                  <td>#{alert.id}</td>
                  <td>{alert.camera_id}</td>
                  <td>{alert.fall_duration?.toFixed(1)}s</td>
                  <td>
                    <StatusBadge
                      status={alert.severity}
                      label={alert.severity}
                    />
                  </td>
                  <td>
                    <StatusBadge
                      status={alert.acknowledged ? "safe" : "danger"}
                      label={alert.acknowledged ? "Ditangani" : "Pending"}
                    />
                  </td>
                  <td>{new Date(alert.created_at).toLocaleString("id-ID")}</td>
                  <td>
                    {!alert.acknowledged && (
                      <button
                        className="btn btn-primary"
                        onClick={() => handleAck(alert.id)}
                      >
                        Acknowledge
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div style={{ display: "flex", justifyContent: "center", gap: "var(--space-md)", marginTop: "var(--space-lg)" }}>
        <button
          className="btn btn-ghost"
          disabled={page === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          ← Sebelumnya
        </button>
        <span style={{ color: "var(--color-text-muted)", alignSelf: "center", fontSize: "var(--font-size-sm)" }}>
          Halaman {page + 1}
        </span>
        <button
          className="btn btn-ghost"
          disabled={alerts.length < PAGE_SIZE}
          onClick={() => setPage((p) => p + 1)}
        >
          Selanjutnya →
        </button>
      </div>
    </>
  );
}
