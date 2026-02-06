import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  // BASE_PATH env sets the subpath prefix (e.g. "/bitaxe/").
  // Defaults to "/" for root-level deployments.
  base: process.env.BASE_PATH || '/',
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../src/web/static',
    emptyOutDir: true,
  },
})
