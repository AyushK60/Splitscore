import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * The dev server binds to loopback only, matching the backend's own default.
 * `/api` is proxied to the FastAPI process so the browser sees a single origin
 * and the frontend never needs to know the backend's port at runtime.
 */
const BACKEND = loadEnv(process.env.NODE_ENV ?? 'development', process.cwd(), '').VITE_API_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
