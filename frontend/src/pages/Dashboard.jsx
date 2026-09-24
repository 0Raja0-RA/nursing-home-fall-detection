/**
 * Dashboard.jsx
 * =============
 * Halaman utama: menampilkan live status semua kamera.
 *
 * Menerima data real-time via WebSocket dan menampilkan
 * CameraFeedCard per kamera dengan status postur & fall state.
 */

import { useState, useEffect } from "react";
import CameraFeedCard from "../components/CameraFeedCard";
import AlertBanner from "../components/AlertBanner";
import { useWebSocket } from "../hooks/useWebSocket";
import { getCameras } from "../services/api";

export default function Dashboard() {
  const [cameras, setCameras] = useState([]);
  const [activeAlert, setActiveAlert] = useState(null);

  // Fetch initial camera list
  useEffect(() => {
    getCameras()
      .then(setCameras)
      .catch((err) => console.error("Failed to fetch cameras:", err));
  }, []);

  // Listen to WebSocket updates
  useWebSocket({
    onStatusUpdate: (data) => {
      setCameras((prev) =>
        prev.map((cam) =>
          cam.camera_id === data.camera_id ? { ...cam, ...data } : cam
        )
      );
    },
    onAlert: (data) => {
      setActiveAlert(data);
      // Auto-dismiss setelah 15 detik
      setTimeout(() => setActiveAlert(null), 15000);
    },
  });

  return (
    <>
      {/* Alert Banner — muncul saat ada fall confirmed */}
      {activeAlert && (
        <AlertBanner
          alert={activeAlert}
          onDismiss={() => setActiveAlert(null)}
        />
      )}

      <h2 className="page-title">Live Monitoring</h2>
      <p className="page-subtitle">
        Status real-time semua kamera yang terhubung
      </p>

      {cameras.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <p style={{ color: "var(--color-text-muted)" }}>
            Belum ada kamera yang terhubung. Pastikan backend sudah berjalan.
          </p>
        </div>
      ) : (
        <div className="grid-cameras">
          {cameras.map((cam) => (
            <CameraFeedCard key={cam.camera_id} camera={cam} />
          ))}
        </div>
      )}
    </>
  );
}
