/**
 * main.jsx
 * ========
 * Entry point aplikasi React.
 * Setup React Router dan global providers.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 5000,
          style: {
            background: "#1e1e2e",
            color: "#cdd6f4",
            border: "1px solid rgba(203, 166, 247, 0.3)",
          },
        }}
      />
    </BrowserRouter>
  </React.StrictMode>
);
