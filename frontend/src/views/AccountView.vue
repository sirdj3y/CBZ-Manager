<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import UserAvatar from '../components/account/UserAvatar.vue'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useNotificationStore } from '../stores/notifications'
import Hint from '../components/ui/Hint.vue'

const auth = useAuthStore()
const notif = useNotificationStore()

// Mot de passe temporaire/par défaut jamais changé (voir router/index.js, qui piège
// l'utilisateur sur cette page tant que c'est le cas) — ouvre directement la modale plutôt
// que de le laisser deviner pourquoi il est redirigé ici.
onMounted(async () => {
  if (auth.mustChangePassword) auth.changePasswordOpen = true
  try {
    const { data } = await authApi.avatarPresets()
    presets.value = data.presets
  } catch { /* pas bloquant */ }
})

// ── Photo de profil ──
const fileInput = ref(null)
const uploadingAvatar = ref(false)

function pickAvatar() {
  fileInput.value?.click()
}

async function onAvatarSelected(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  uploadingAvatar.value = true
  try {
    const { data } = await authApi.uploadAvatar(file)
    auth.applyStatus(data)
    notif.success('Photo de profil mise à jour')
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'envoi de la photo")
  } finally {
    uploadingAvatar.value = false
  }
}

async function removeAvatar() {
  uploadingAvatar.value = true
  try {
    const { data } = await authApi.removeAvatar()
    auth.applyStatus(data)
    notif.success('Photo de profil supprimée')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    uploadingAvatar.value = false
  }
}

// ── Avatars préréglés — même résultat qu'un upload (recadrage/redimensionnement côté
// serveur), juste sans passer par la sélection de fichier.
const presets = ref([])
const applyingPreset = ref(null)

async function applyPreset(n) {
  applyingPreset.value = n
  try {
    const { data } = await authApi.applyAvatarPreset(n)
    auth.applyStatus(data)
    notif.success('Photo de profil mise à jour')
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'application")
  } finally {
    applyingPreset.value = null
  }
}

// ── Catalogue OPDS ──
const opdsUrl = window.location.origin + '/opds'

async function copyOpdsUrl() {
  try {
    await navigator.clipboard.writeText(opdsUrl)
    notif.success('URL copiée dans le presse-papier')
  } catch {
    notif.error('Impossible de copier — sélectionnez et copiez manuellement')
  }
}

// ── Identifiant ──
const usernameForm = ref({ current_password: '', new_username: '' })
const savingUsername = ref(false)

async function saveUsername() {
  if (!usernameForm.value.current_password) {
    notif.error('Mot de passe actuel requis')
    return
  }
  if (!usernameForm.value.new_username.trim()) {
    notif.error("Nouvel identifiant requis")
    return
  }
  savingUsername.value = true
  try {
    const { data } = await authApi.updateCredentials({
      current_password: usernameForm.value.current_password,
      new_username: usernameForm.value.new_username.trim(),
    })
    auth.applyStatus(data)
    notif.success('Identifiant mis à jour')
    usernameForm.value = { current_password: '', new_username: '' }
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la mise à jour')
  } finally {
    savingUsername.value = false
  }
}
</script>

<template>
  <AppLayout>
    <main class="settings-main">
      <h1 class="settings-heading">Mon compte</h1>

      <div v-if="auth.mustChangePassword" class="force-password-banner">
        Vous utilisez encore un mot de passe temporaire ou par défaut — changez-le pour accéder au reste de l'application.
      </div>

      <section class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Photo de profil</div>
          <div class="avatar-row">
            <UserAvatar :size="72" />
            <div class="avatar-actions">
              <button class="btn btn-ghost btn-sm" :disabled="uploadingAvatar" @click="pickAvatar">
                {{ uploadingAvatar ? 'Envoi…' : 'Importer une photo' }}
              </button>
              <button v-if="auth.avatarVersion > 0" class="btn btn-ghost btn-sm" :disabled="uploadingAvatar" @click="removeAvatar">
                Supprimer la photo
              </button>
              <input ref="fileInput" type="file" accept="image/*" class="visually-hidden" @change="onAvatarSelected" />
            </div>
          </div>

          <div v-if="presets.length" class="preset-grid">
            <Hint v-for="n in presets" :key="n" label="Utiliser cet avatar">
              <button
                type="button" class="preset-btn"
                :disabled="applyingPreset !== null" @click="applyPreset(n)"
              >
                <img :src="`/api/auth/avatar-presets/${n}`" :alt="`Avatar préréglé ${n}`" loading="lazy" />
              </button>
            </Hint>
          </div>
        </div>
      </section>

      <section v-if="auth.hasPermission('library.read')" class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Applications de lecture (OPDS)</div>
          <p class="form-hint" style="margin-top:-6px; margin-bottom: 14px;">
            Ajoutez cette adresse dans une app de lecture compatible OPDS (Chunky, Panels, Yacreader...) pour parcourir et télécharger la bibliothèque directement depuis l'app, avec votre identifiant et mot de passe habituels.
          </p>
          <div class="opds-url-box">
            <code>{{ opdsUrl }}</code>
            <button class="btn btn-ghost btn-sm" @click="copyOpdsUrl">Copier</button>
          </div>
        </div>
      </section>

      <section class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Identifiant</div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Nouvel identifiant</label>
              <input v-model="usernameForm.new_username" type="text" class="form-control" :placeholder="auth.username" autocomplete="username" />
              <p class="form-hint">Actuel : {{ auth.username }}</p>
            </div>
            <div class="form-group">
              <label class="form-label">Mot de passe actuel</label>
              <input v-model="usernameForm.current_password" type="password" class="form-control" autocomplete="current-password" @keyup.enter="saveUsername" />
            </div>
          </div>
          <div class="settings-actions">
            <button @click="saveUsername" :disabled="savingUsername" class="btn btn-primary btn-sm">
              {{ savingUsername ? 'Enregistrement…' : 'Enregistrer' }}
            </button>
          </div>
        </div>
      </section>

      <section class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Mot de passe</div>
          <p class="form-hint" style="margin-top:-6px; margin-bottom: 14px;">
            Modifiez votre mot de passe.
          </p>
          <div class="settings-actions">
            <button class="btn btn-primary btn-sm" @click="auth.changePasswordOpen = true">Changer le mot de passe</button>
          </div>
        </div>
      </section>
    </main>
  </AppLayout>
</template>

<style scoped>
.settings-main {
  flex: 1; padding: 24px 20px;
  max-width: 1100px; margin: 0 auto; width: 100%;
}
.settings-heading {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 1.4rem;
  margin-bottom: 20px; color: var(--text);
}
.settings-section { margin-bottom: 20px; }
.settings-section-title {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted); margin-bottom: 14px;
}
.form-group { margin-bottom: 14px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-row .form-group { margin-bottom: 14px; }
.form-hint { margin-top: 5px; font-size: 0.8rem; color: var(--muted); }
.settings-actions { display: flex; gap: 10px; margin-top: 4px; }

.force-password-banner {
  padding: 10px 14px; margin-bottom: 20px;
  background: var(--warning-bg, #fffbeb); color: var(--orange-bar, #b45309);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 0.85rem;
}
.opds-url-box {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 12px; background: var(--light); border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.opds-url-box code { font-size: 0.85rem; word-break: break-all; }
.avatar-row { display: flex; align-items: center; gap: 18px; }
.avatar-actions { display: flex; align-items: center; gap: 8px; }

.preset-grid {
  display: grid; grid-template-columns: repeat(5, 56px);
  gap: 18px;
  margin-top: 16px; padding-top: 16px;
  border-top: 1px solid var(--border);
}
.preset-btn {
  padding: 0; border: 2px solid transparent; border-radius: 50%;
  width: 56px; height: 56px; cursor: pointer; background: none;
  transition: border-color 0.15s, opacity 0.15s;
}
.preset-btn:hover:not(:disabled) { border-color: var(--primary); }
.preset-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.preset-btn img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; display: block; }
.visually-hidden {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
</style>
