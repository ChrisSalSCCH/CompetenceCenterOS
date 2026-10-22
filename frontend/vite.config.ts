import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import xaioDesignPlugin from './vite-plugin-xaio-design'

export default defineConfig({
  cacheDir: '.vite',
  plugins: [
    react(),
    tailwindcss(), // Tailwind v4 — no postcss.config.js, no tailwind.config.ts
    xaioDesignPlugin() // XAIO Design Mode - adds data-xaio-source attributes
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    dedupe: ['react', 'react-dom'],
  },
  server: {
    port: 3000,
    cors: true, // Enable CORS for html2canvas screenshot capture
    // No proxy here — the workspace-runner handles /api/* proxying
    // to the backend in both local and cloud modes.
  },
  // Build optimizations to reduce render-blocking resources
  build: {
    // Enable minification (esbuild is built-in, no extra deps needed)
    minify: 'esbuild',
    // Code splitting for better caching
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor chunks
          'vendor-react': ['react', 'react-dom'],
          'vendor-router': ['react-router-dom'],
        },
        // Asset file naming with hash for caching
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
    // Generate source maps for debugging (optional in prod)
    sourcemap: false,
    // CSS code splitting
    cssCodeSplit: true,
    // Target modern browsers for smaller bundles
    target: 'es2020',
    // Reduce chunk size warning threshold
    chunkSizeWarningLimit: 500,
  },
  // Pre-bundle every shipped dep at Vite startup so the agent never
  // triggers a mid-session re-optimization (which serves 504 Gateway
  // Timeouts on `.vite/deps/*.js` requests and renders a blank preview
  // until the optimize pass finishes). Listing everything from
  // package.json adds ~3-5 s to first `vite ready` but removes the
  // optimize race entirely once the agent starts importing new deps.
  optimizeDeps: {
    include: [
      // core
      'react',
      'react-dom',
      'react-router-dom',
      // shadcn primitives
      '@radix-ui/react-accordion',
      '@radix-ui/react-alert-dialog',
      '@radix-ui/react-aspect-ratio',
      '@radix-ui/react-avatar',
      '@radix-ui/react-checkbox',
      '@radix-ui/react-collapsible',
      '@radix-ui/react-context-menu',
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-hover-card',
      '@radix-ui/react-label',
      '@radix-ui/react-menubar',
      '@radix-ui/react-navigation-menu',
      '@radix-ui/react-popover',
      '@radix-ui/react-progress',
      '@radix-ui/react-radio-group',
      '@radix-ui/react-scroll-area',
      '@radix-ui/react-select',
      '@radix-ui/react-separator',
      '@radix-ui/react-slider',
      '@radix-ui/react-slot',
      '@radix-ui/react-switch',
      '@radix-ui/react-tabs',
      '@radix-ui/react-toast',
      '@radix-ui/react-toggle',
      '@radix-ui/react-toggle-group',
      '@radix-ui/react-tooltip',
      // styling utilities (used by shadcn `cn()`)
      'class-variance-authority',
      'clsx',
      'tailwind-merge',
      // icons + theming
      'lucide-react',
      'next-themes',
      // data fetching
      'axios',
      // forms
      '@hookform/resolvers',
      'react-hook-form',
      'zod',
      // misc shipped components
      'cmdk',
      'date-fns',
      'embla-carousel-react',
      'framer-motion',
      'input-otp',
      'react-day-picker',
      'react-resizable-panels',
      'recharts',
      'sonner',
      'vaul',
      'zustand',
    ],
  },
})
