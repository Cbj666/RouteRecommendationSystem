import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发时把 /api 代理到本地 FastAPI（卡片 2），避免前端写死地址
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 本仓库用原子临时目录写文件（*.tmpdir），Vite 监听会在 Windows 上报 EBUSY；
    // 忽略这些临时目录，dev server 才不会因一次保存而崩溃。
    watch: {
      ignored: ['**/*.tmpdir/**', '**/*.tmpdir'],
    },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
