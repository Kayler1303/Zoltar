import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// Import path for resolving paths
// import path from 'path' // No longer needed if removing explicit css config

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Remove the explicit CSS configuration block
  /*
  css: {
    postcss: {
      config: path.resolve(__dirname, 'postcss.config.js'),
    },
  },
  */
  // Optional: Define environment variables if needed
  // define: {
  //   'process.env': process.env
  // }
})
