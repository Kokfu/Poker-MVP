import { defineConfig } from 'vite'; import react from '@vitejs/plugin-react';
// API_PROXY lets a local (non-Docker) run point at a local backend; Docker keeps the service name.
export default defineConfig({plugins:[react()],server:{proxy:{'/api':process.env.API_PROXY ?? 'http://backend:8000'}}});
