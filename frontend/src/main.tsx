import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { Dashboard } from "./components/Dashboard";
import { DeviceConfig } from "./components/DeviceConfig";
import { Layout } from "./components/Layout";
import { NightDetail } from "./components/NightDetail";
import { Upload } from "./components/Upload";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/nights/:id" element={<NightDetail />} />
          <Route path="/device" element={<DeviceConfig />} />
          <Route path="/upload" element={<Upload />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
