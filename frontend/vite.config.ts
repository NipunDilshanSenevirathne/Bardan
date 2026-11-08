import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.png', 'icons/*.png', 'img/*-640.webp'],
      manifest: {
        name: 'Bardan: heat protection that gets done',
        short_name: 'Bardan',
        description: 'Worker-first heat protection and kidney care continuity (prototype, synthetic data).',
        theme_color: '#0B1324',
        background_color: '#070B16',
        display: 'standalone',
        start_url: '/app',
        lang: 'en',
        icons: [
          { src: '/icons/logo-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/logo-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        // Precache the app shell, fonts and small images only; full-size photos load on demand.
        globPatterns: ['**/*.{js,css,html,woff2,png,svg}', 'img/*-640.webp'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/v1\//],
        runtimeCaching: [],
      },
    }),
  ],
  server: { port: 5173, proxy: { '/v1': 'http://127.0.0.1:8080' }, fs: { allow: ['..'] } },
  build: { target: 'es2022', chunkSizeWarningLimit: 1200, sourcemap: false },
})
