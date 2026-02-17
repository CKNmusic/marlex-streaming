import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const normalizeAppSegment = (value: string) => value.trim().replace(/^\/+|\/+$/g, '');

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const host = env.HOST || env.host || '0.0.0.0';
  const rawPort = env.PORT || env.port || '3000';
  const parsedPort = Number.parseInt(rawPort, 10);
  const port = Number.isFinite(parsedPort) ? parsedPort : 3000;
  const app = normalizeAppSegment(env.APP || env.app || env.VITE_APP_NAME || 'surgwaze');
  const base = app ? `/${app}/` : '/';

  return {
    plugins: [react()],
    base,
    server: {
      host,
      port,
      strictPort: true,
      allowedHosts: true,
    },
    preview: {
      host,
      port,
      strictPort: true,
    },
  };
});
