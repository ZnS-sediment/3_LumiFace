import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
const apiTarget = process.env.LUMIFACE_API_URL || 'http://127.0.0.1:8000'
export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, strictPort: true, proxy: { '/api': apiTarget } },
  preview: { port: 5173, strictPort: true, proxy: { '/api': apiTarget } },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router'],
          element: ['element-plus'],
        },
      },
    },
  },
})
