import { defineConfig } from 'vite';
import { fileURLToPath, URL } from 'node:url';

// Content is imported from the backend's data directory at BUILD time, not
// fetched at runtime. Three things fall out of that:
//
//   - the page paints with real copy on first frame, no loading state
//   - the site stays fully functional with the backend switched off
//   - it can be hosted as static files on a free CDN, with only the live
//     demos needing the Python process
//
// The API still serves the same JSON, so there is one source of truth either
// way — the frontend just reads it earlier.
export default defineConfig({
  resolve: {
    alias: {
      '@data': fileURLToPath(new URL('../backend/app/data', import.meta.url)),
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Only demo calls go over the wire in dev.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    target: 'es2020',
    sourcemap: false,
  },
});
