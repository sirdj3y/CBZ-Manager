<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

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
    window.location.href = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
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
    </form>
  </div>
</template>

<style scoped>
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
