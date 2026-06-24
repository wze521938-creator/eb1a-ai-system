import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:5000", "/upload_case": "http://localhost:5000", "/run_pipeline": "http://localhost:5000", "/case": "http://localhost:5000" } },
});
