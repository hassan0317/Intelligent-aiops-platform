import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// dev proxy so `npm run dev` can reach the API too (prod uses nginx proxy)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8050" } },
});
