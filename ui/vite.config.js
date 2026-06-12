import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Semua request /api/* dan /images/* diteruskan ke Flask
      '/api':    'http://localhost:5000',
      '/images': 'http://localhost:5000',
    },
  },
})
