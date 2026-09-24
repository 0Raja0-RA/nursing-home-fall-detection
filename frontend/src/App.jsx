/**
 * App.jsx
 * =======
 * Root component — layout (header + navigation) dan routing.
 */

import { NavLink, Routes, Route, Navigate } from "react-router-dom";
import { MdDashboard, MdNotifications, MdSettings } from "react-icons/md";
import Dashboard from "./pages/Dashboard";
import AlertHistory from "./pages/AlertHistory";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="app-layout">
      {/* ---- Header & Navigation ---- */}
      <header className="app-header">
        <h1>🛡️ Fall Detection Dashboard</h1>
        <nav className="app-nav">
          <NavLink to="/dashboard" className={({ isActive }) => isActive ? "active" : ""}>
            <MdDashboard style={{ verticalAlign: "middle", marginRight: 4 }} />
            Dashboard
          </NavLink>
          <NavLink to="/alerts" className={({ isActive }) => isActive ? "active" : ""}>
            <MdNotifications style={{ verticalAlign: "middle", marginRight: 4 }} />
            Alert History
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => isActive ? "active" : ""}>
            <MdSettings style={{ verticalAlign: "middle", marginRight: 4 }} />
            Settings
          </NavLink>
        </nav>
      </header>

      {/* ---- Main Content ---- */}
      <main className="app-main">
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/alerts" element={<AlertHistory />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}
