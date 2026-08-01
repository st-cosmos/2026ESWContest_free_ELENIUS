import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 시: vite dev 서버(5173)에서 API 요청을 FastAPI(8000)로 프록시
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/faces": "http://localhost:8000",
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
});
