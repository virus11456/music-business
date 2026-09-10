import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { fileURLToPath } from 'node:url';

// Frontend-only Vercel build. No local database or backend secrets are bundled.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  css: { postcss: { plugins: [tailwindcss()] } },
  define: { __HOSTED_FRONTEND__: 'true' },
  build: { outDir: 'dist-vercel', emptyOutDir: true },
});
