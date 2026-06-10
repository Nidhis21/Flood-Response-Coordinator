import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file from parent directory
  const env = loadEnv(mode, '../', '')
  console.log('Vite Config - Loaded MAPBOX_TOKEN:', env.MAPBOX_TOKEN ? 'FOUND (starts with ' + env.MAPBOX_TOKEN.substring(0, 8) + '...)' : 'NOT FOUND')
  
  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.MAPBOX_TOKEN': JSON.stringify(env.MAPBOX_TOKEN),
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
      'import.meta.env.VITE_MAPBOX_TOKEN': JSON.stringify(env.MAPBOX_TOKEN),
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
        },
      },
    },
  }
})
