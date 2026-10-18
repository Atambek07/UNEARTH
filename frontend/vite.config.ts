import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Dev-сервер проксирует /api на локальный FastAPI (localhost:8000).
// Для продакшен-сборки можно задать VITE_API_URL (см. src/api/client.ts).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
