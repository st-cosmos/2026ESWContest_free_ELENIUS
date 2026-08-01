import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 시: vite dev 서버(5273)에서 API 요청을 데모 서버(8100)로 프록시
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      "/api": "http://localhost:8100",
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
});
