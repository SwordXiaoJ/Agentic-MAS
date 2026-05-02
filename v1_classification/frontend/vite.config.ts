import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/classify': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        timeout: 120000,
      },
      '/v1': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        timeout: 120000,
      },
    },
  },
})
