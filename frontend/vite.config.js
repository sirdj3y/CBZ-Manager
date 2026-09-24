import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'

const version = readFileSync(new URL('../VERSION', import.meta.url), 'utf-8').trim()

export default defineConfig({
  // Tailwind ne sert qu'au bac à sable shadcn-vue (src/labs/shadcn/) : son CSS n'est importé que
  // par cette page, sans la remise à zéro globale (preflight) — le reste de l'app est inchangé.
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    // Vite 8 minifie le CSS avec Lightning CSS par défaut, qui réécrit "max-width: 640px" en
    // syntaxe moderne "width <= 640px" (CSS Media Queries niveau 4) quand aucune cible n'est
    // fournie — non supportée avant Safari 16.4 (mars 2023). Sur un iPhone plus ancien, les
    // media queries concernées sont donc silencieusement ignorées dans leur intégralité (aucune
    // erreur, juste pas appliquées), cassant toute la mise en page responsive. La cible lue par
    // l'étape de minification est build.cssTarget (pas css.lightningcss.targets, qui ne sert
    // qu'à l'étape de transform désactivée par défaut) : on force donc Safari/iOS 12 ici pour
    // garder la syntaxe classique min-width/max-width, compatible avec tous les iPhone.
    cssTarget: ['safari12', 'ios12'],
  },
  server: {
    port: 5173,
    proxy: {
      // Le backend de dev tourne sur le port 8000 (voir CLAUDE.md : `uvicorn backend.main:app
      // --reload --port 8000`), jamais sur 5173 (celui de CE serveur Vite lui-même) — ce
      // dernier se relayait donc sur son propre port, en boucle, plutôt que de rejoindre
      // FastAPI. Redéfinissable via VITE_BACKEND_PORT si le backend tourne ailleurs.
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || 8000}`,
        changeOrigin: true,
      },
    },
  },
})
