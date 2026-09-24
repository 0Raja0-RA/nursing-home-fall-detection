/**
 * api.js
 * ======
 * API client untuk berkomunikasi dengan backend FastAPI.
 * Menggunakan axios dengan base URL yang sudah di-proxy oleh Vite.
 */

import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
  timeout: 10000,
});

// ---- Alerts -----------------------------------------------

/**
 * Ambil daftar alert dengan pagination dan filter.
 * @param {{ skip?: number, limit?: number, acknowledged?: boolean|null }} params
 * @returns {Promise<Array>}
 */
export async function getAlerts(params = {}) {
  const { data } = await api.get("/alerts/", { params });
  return data;
}

/**
 * Acknowledge (tandai sudah ditangani) sebuah alert.
 * @param {number} alertId
 * @returns {Promise<Object>}
 */
export async function acknowledgeAlert(alertId) {
  const { data } = await api.put(`/alerts/${alertId}/ack`);
  return data;
}

// ---- Cameras ----------------------------------------------

/**
 * Ambil daftar semua kamera beserta statusnya.
 * @returns {Promise<Array>}
 */
export async function getCameras() {
  const { data } = await api.get("/cameras/");
  return data;
}

/**
 * Ambil status satu kamera.
 * @param {string} cameraId
 * @returns {Promise<Object>}
 */
export async function getCamera(cameraId) {
  const { data } = await api.get(`/cameras/${cameraId}`);
  return data;
}

// ---- Settings ---------------------------------------------

/**
 * Ambil konfigurasi aktif.
 * @returns {Promise<Object>}
 */
export async function getSettings() {
  const { data } = await api.get("/settings/");
  return data;
}

/**
 * Update threshold durasi falling.
 * @param {number} threshold - Durasi dalam detik (1-60).
 * @returns {Promise<Object>}
 */
export async function updateThreshold(threshold) {
  const { data } = await api.put("/settings/threshold", {
    fall_duration_threshold: threshold,
  });
  return data;
}

export default api;
