<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { isCancelled, loginWithPasskey, passkeyErrorMessage, passkeyStatus } from '../utils/passkeys'

const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

// Passkey : proposée seulement depuis l'adresse publique (voir utils/passkeys.js) ; ailleurs
// (IP locale du NAS), un lien vers cette adresse si les passkeys sont activées.
const pk = ref({ enabled: false, usable: false, origin: null })
onMounted(async () => { pk.value = await passkeyStatus() })

function goAfterLogin() {
  window.location.href = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
}

async function submitPasskey() {
  loading.value = true
  error.value = ''
  try {
    await loginWithPasskey()
    goAfterLogin()
  } catch (e) {
    if (!isCancelled(e)) error.value = passkeyErrorMessage(e, 'Connexion par passkey impossible')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!username.value.trim() || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    // Rechargement complet plutôt qu'une navigation SPA (router.push) : les stores Pinia
    // (séries, smart lists, auteurs...) ne sont jamais réinitialisés entre deux connexions
    // dans le même onglet — sans ce rechargement, un changement de compte laissait apparaître
    // les données mises en cache de la session précédente (ex. smart lists privées d'un
    // autre utilisateur) jusqu'à ce que chaque store se rafraîchisse séparément.
    goAfterLogin()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erreur de connexion'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-logo">
        <img src="/favicon.png" class="login-logo-img" alt="" />
        <h1 class="login-title">CBZ Manager</h1>
      </div>

      <div class="form-group">
        <label class="form-label">Identifiant</label>
        <input v-model="username" type="text" class="form-control" autocomplete="username" autofocus />
      </div>
      <div class="form-group">
        <label class="form-label">Mot de passe</label>
        <input v-model="password" type="password" class="form-control" autocomplete="current-password" />
      </div>

      <p v-if="error" class="login-error">{{ error }}</p>

      <button type="submit" class="btn btn-primary login-submit" :disabled="loading">
        {{ loading ? 'Connexion…' : 'Se connecter' }}
      </button>

      <template v-if="pk.usable">
        <div class="login-or"><span>ou</span></div>
        <button type="button" class="btn btn-secondary login-submit" :disabled="loading" @click="submitPasskey">
          Se connecter avec une passkey
        </button>
      </template>
      <p v-else-if="pk.enabled && pk.origin" class="login-pk-hint">
        Connexion par passkey disponible sur <a :href="pk.origin + '/login'">{{ pk.origin.replace(/^https?:\/\//, '') }}</a>
      </p>
    </form>
  </div>
</template>

<style scoped>
.login-or { display: flex; align-items: center; gap: 10px; margin: 14px 0; color: var(--muted); font-size: 0.8rem; }
.login-or::before, .login-or::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.login-pk-hint { margin-top: 14px; text-align: center; font-size: 0.78rem; color: var(--muted); }
.login-page {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: var(--light);
  padding: 20px;
}
.login-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 32px;
  width: 100%;
  max-width: 360px;
}
.login-logo {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  margin-bottom: 26px;
}
.login-logo-img { width: 52px; height: 52px; border-radius: 12px; }
.login-title { font-family: var(--font-display); font-weight: 400; text-transform: uppercase; font-size: 1.3rem; color: var(--text); }
.form-group { margin-bottom: 14px; }
.login-error {
  color: var(--danger); font-size: 0.85rem;
  margin: -4px 0 14px;
}
.login-submit { width: 100%; margin-top: 4px; }
</style>
