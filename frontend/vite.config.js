import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '127.0.0.1',
    proxy: {
      '/agent': 'http://localhost:8000',
      '/chats': 'http://localhost:8000',
      '/name-chat': 'http://localhost:8000',
      '/tools': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  }
})