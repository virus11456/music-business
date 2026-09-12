import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { fileURLToPath } from 'node:url';

const buildId=process.env.VERCEL_GIT_COMMIT_SHA||String(Date.now());
const apiOrigin=(process.env.VITE_API_ORIGIN||'https://srv1542946.hstgr.cloud').replace(/\/$/,'');
if(apiOrigin){const u=new URL(apiOrigin);if(u.protocol!=='https:'||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('VITE_API_ORIGIN must be an HTTPS origin');}

// Frontend-only Vercel build. No local database or backend secrets are bundled.
export default defineConfig({
  plugins: [react(),{name:'build-version',generateBundle(){this.emitFile({type:'asset',fileName:'version.json',source:JSON.stringify({buildId})});}}],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  css: { postcss: { plugins: [tailwindcss()] } },
  define: { __HOSTED_FRONTEND__: 'true', __BUILD_ID__: JSON.stringify(buildId), __API_ORIGIN__: JSON.stringify(apiOrigin) },
  build: { outDir: 'dist-vercel', emptyOutDir: true },
});
