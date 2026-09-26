import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './style.css'
// Après style.css : composants shadcn-vue (Tailwind sans preflight, voir ce fichier).
import './components/shadcn/shadcn.css'
import { useThemeStore } from './stores/theme'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Appliquer le thème AVANT le premier rendu pour éviter le flash
const themeStore = useThemeStore(pinia)
themeStore.init()

app.mount('#app')
