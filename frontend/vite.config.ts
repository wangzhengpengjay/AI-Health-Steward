import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Dev-server proxy target for the backend API.
//
// Default is localhost so `npm run dev` works when the backend runs directly on
// the host (the previous hardcoded 'http://backend:8000' only resolved inside
// the docker-compose network, so host-side development failed with a DNS error).
// docker-compose.yml sets VITE_PROXY_TARGET=http://backend:8000 for the
// containerised frontend.
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
