import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/dashboard/',
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://127.0.0.1:8765', '/prices': 'http://127.0.0.1:8765', '/sources': 'http://127.0.0.1:8765', '/updates': 'http://127.0.0.1:8765', '/catalog': 'http://127.0.0.1:8765', '/scenarios': 'http://127.0.0.1:8765', '/analytics': 'http://127.0.0.1:8765' } },
  build: { rollupOptions: { output: { manualChunks: {
    charts: ['recharts'],
    animation: ['motion/react'],
    react: ['react', 'react-dom/client'],
  } } } },
  test: { environment: 'jsdom', setupFiles: ['./tests/setup.ts'], include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'] },
})
