/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Dev server proxies /api to the backend so the browser never needs an
 * absolute backend URL and there are no CORS surprises in development.
 * The `test` block configures Vitest (jsdom).
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendTarget = env.VITE_DEV_BACKEND_URL || 'http://127.0.0.1:8000';

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      /* Split the two large, independently-cacheable dependencies out of the
         entry chunk. `three` is only ever requested by the lazy hero scene,
         and `framer-motion` is shared by the app shell and marketing pages,
         so caching them separately keeps entry payload small and lets a
         change to product code avoid re-downloading either library. */
      rollupOptions: {
        output: {
          manualChunks: {
            three: ['three'],
            motion: ['framer-motion'],
            vendor: ['react', 'react-dom', 'react-router-dom', '@supabase/supabase-js'],
          },
        },
      },
      chunkSizeWarningLimit: 620,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
