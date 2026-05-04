import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],

  build: {
    // Output to dist/ (default); Nginx COPY --from=builder picks this up.
    outDir: 'dist',
    sourcemap: false,
  },

  server: {
    // Proxy /api/ to the local BFF during `npm run dev` (no Docker needed).
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
