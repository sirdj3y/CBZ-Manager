import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const authenticated = ref(false)
  const username = ref('')
  const isAdmin = ref(false)
  const mustChangePassword = ref(false)
  const permissions = ref([])
  // 0 = pas de photo de profil, sinon cache-buster pour l'URL de l'avatar (voir
  // routers/auth.py — incrémenté à chaque upload/suppression).
  const avatarVersion = ref(0)
  // Distingue "pas encore vérifié" de "vérifié et non connecté" — le garde de route
  // n'a besoin d'appeler /me qu'une seule fois par chargement d'app.
  const checked = ref(false)
  // Modale "changer le mot de passe" — état partagé ici (plutôt qu'un composable dédié)
  // car AppLayout et la page Mon compte ont chacun leur propre instance de la modale mais
  // doivent piloter la même ouverture/fermeture ; les deux importent déjà ce store.
  const changePasswordOpen = ref(false)

  // Un admin passe toujours, indépendamment de son profil (généralement absent) — même
  // logique que require_permission côté serveur (backend/dependencies.py).
  function hasPermission(key) {
    return isAdmin.value || permissions.value.includes(key)
  }

  // Exposé — les appels qui renvoient déjà un AuthStatus à jour (changement d'identifiants,
  // upload/suppression d'avatar) l'appliquent directement, sans round-trip /me superflu.
  function applyStatus(data) {
    authenticated.value = data.authenticated
    username.value = data.username || ''
    isAdmin.value = data.is_admin || false
    mustChangePassword.value = data.must_change_password || false
    permissions.value = data.permissions || []
    avatarVersion.value = data.avatar_version || 0
  }

  async function checkAuth() {
    try {
      const { data } = await authApi.me()
      applyStatus(data)
    } catch {
      authenticated.value = false
    } finally {
      checked.value = true
    }
  }

  async function login(u, p) {
    const { data } = await authApi.login(u, p)
    applyStatus(data)
    checked.value = true
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch { /* ignoré — on déconnecte localement dans tous les cas */ }
    authenticated.value = false
    username.value = ''
    isAdmin.value = false
    mustChangePassword.value = false
    permissions.value = []
    avatarVersion.value = 0
  }

  return {
    authenticated, username, isAdmin, mustChangePassword, permissions, avatarVersion, checked,
    changePasswordOpen, hasPermission, applyStatus, checkAuth, login, logout,
  }
})
