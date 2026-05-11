import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: process.env.DOCKER_BUILD ? './dist' : '../featcat/server/static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          // d3 split out of `charts` so the lazy-loaded Graph tab on the
          // Similarity page actually defers its weight — pages that only
          // use recharts (e.g. Monitoring) no longer drag d3 in too.
          'charts': ['recharts'],
          'd3': ['d3'],
          'motion': ['motion'],
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': process.env.VITE_API_PROXY ?? 'http://localhost:8000',
    },
  },
})
