import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Phase 0 placeholder shell. No product UI yet.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
