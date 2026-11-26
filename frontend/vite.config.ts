import { defineConfig } from 'vite'; import react from '@vitejs/plugin-react';
import { pokerWebApp } from './pwa-build.mjs';
// API_PROXY lets a local (non-Docker) run point at a local backend; Docker keeps the service name.
export default defineConfig({plugins:[react(),pokerWebApp()],server:{proxy:{'/api':process.env.API_PROXY ?? 'http://backend:8000'}}});
