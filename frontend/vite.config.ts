import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { visualizer } from 'rollup-plugin-visualizer'
import viteCompression from 'vite-plugin-compression'
import AutoImport from 'unplugin-auto-import/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ command, mode }) => {
  const isAnalyze = mode === 'analyze'

  // 开发代理目标：本地直跑 Vite 时默认 localhost:8000；
  // Docker 开发环境（docker-compose.yml）中注入 VITE_PROXY_TARGET=http://backend:8000
  const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

  return {
    base: command === 'build' ? '/static/' : '/',
    plugins: [
      vue(),
      vuetify({
        autoImport: true,
        styles: {
          configFile: 'src/styles/settings.scss',
        },
      }),
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia', '@vueuse/core'],
        dts: 'src/auto-imports.d.ts',
      }),
      viteCompression({ verbose: true, disable: false, threshold: 10240, algorithm: 'gzip', ext: '.gz' }),
      viteCompression({ verbose: true, disable: false, threshold: 10240, algorithm: 'brotliCompress', ext: '.br' }),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.ico', 'favicon-32x32.png', 'apple-touch-icon.png', 'favicon.svg'],
        manifest: {
          name: 'SYTMDB',
          short_name: 'SYTMDB',
          description: 'SYTMDB - 支持 Bangumi、Emby 集成',
          theme_color: '#a855f7',
          background_color: '#0a0a1a',
          display: 'standalone',
          orientation: 'portrait',
          scope: '/',
          start_url: '/',
          icons: [
            { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            { src: '/pwa-maskable-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
            { src: '/pwa-maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/.*/i,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'api-cache',
                expiration: {
                  maxEntries: 100,
                  maxAgeSeconds: 60 * 60 * 24 * 7,
                },
                cacheableResponse: {
                  statuses: [0, 200],
                },
              },
            },
          ],
        },
      }),
      isAnalyze && visualizer({ open: true, gzipSize: true, filename: 'dist/stats.html' }),
    ],
    define: {
      __APP_VERSION__: JSON.stringify('3.0.0'), // 改版本号只需改 package.json 的 version 字段
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
        '/media-content': { target: proxyTarget, changeOrigin: true },
        '/ws': { target: proxyTarget, ws: true, changeOrigin: true },
        '/static': { target: proxyTarget, changeOrigin: true },
        '/tmdb-mock': { target: proxyTarget, changeOrigin: true },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/vuetify') || id.includes('node_modules/.vite/deps/vuetify')) return 'vuetify'
            if (id.includes('node_modules/three')) return 'three'
            if (id.includes('node_modules/vue') || id.includes('node_modules/vue-router') || id.includes('node_modules/pinia')) return 'vue-vendor'
          },
        },
      },
      minify: true,
      // 禁用 CSS 压缩 — esbuild 会将 backdrop-filter 和 -webkit-backdrop-filter
      // 视为同一属性去重，删除标准的 backdrop-filter，导致 Firefox 等浏览器毛玻璃效果失效
      // gzip/brotli 压缩仍由 vite-plugin-compression 处理，体积影响极小
      cssMinify: false,
    },
  }
})
