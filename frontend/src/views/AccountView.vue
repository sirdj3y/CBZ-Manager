<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import UserAvatar from '../components/account/UserAvatar.vue'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useNotificationStore } from '../stores/notifications'
import Hint from '../components/ui/Hint.vue'
import AppDialog from '../components/ui/AppDialog.vue'
import { passkeysApi } from '../api/passkeys'
import { defaultPasskeyName, isCancelled, passkeyStatus, registerPasskey } from '../utils/passkeys'

const auth = useAuthStore()
const notif = useNotificationStore()

// Mot de passe temporaire/par défaut jamais changé (voir router/index.js, qui piège
// l'utilisateur sur cette page tant que c'est le cas) — ouvre directement la modale plutôt
// que de le laisser deviner pourquoi il est redirigé ici.
onMounted(async () => {
  if (auth.mustChangePassword) auth.changePasswordOpen = true
  loadPasskeys()
  try {
    const { data } = await authApi.avatarPresets()
    presets.value = data.presets
  } catch { /* pas bloquant */ }
})

// ── Passkeys ── (voir utils/passkeys.js)
const pkStatus = ref({ enabled: false, usable: false, origin: null })
const passkeys = ref([])
const pkNameOpen = ref(false)
const pkName = ref('')
const pkBusy = ref(false)
const pkToDelete = ref(null)

async function loadPasskeys() {
  pkStatus.value = await passkeyStatus()
  if (!pkStatus.value.enabled) return
  try {
    passkeys.value = (await passkeysApi.list()).data
  } catch { /* pas bloquant */ }
}
function startAddPasskey() {
  pkName.value = defaultPasskeyName()
  pkNameOpen.value = true
}
async function confirmAddPasskey() {
  pkBusy.value = true
  try {
    const created = await registerPasskey(pkName.value.trim() || defaultPasskeyName())
    passkeys.value.push(created)
    pkNameOpen.value = false
    notif.success('Passkey ajoutée')
  } catch (e) {
    if (!isCancelled(e)) notif.error(e.response?.data?.detail || "Impossible d'ajouter la passkey")
  } finally {
    pkBusy.value = false
  }
}
async function deletePasskey() {
  const p = pkToDelete.value
  try {
    await passkeysApi.remove(p.id)
    passkeys.value = passkeys.value.filter(x => x.id !== p.id)
    notif.success('Passkey supprimée')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    pkToDelete.value = null
  }
}
function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : ''
}

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
    notif.error('Impossible de copier. Sélectionnez le texte et copiez-le manuellement.')
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
        Vous utilisez encore un mot de passe temporaire ou par défaut. Changez-le pour accéder au reste de l'application.
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

      <section v-if="pkStatus.enabled" class="card settings-section">
        <div class="card-body">
          <div class="settings-section-title">Passkeys</div>
          <p class="form-hint" style="margin-top:-6px; margin-bottom: 14px;">
            Connectez-vous avec Face ID, Touch ID, Windows Hello ou votre gestionnaire de mots de passe, sans saisir de mot de passe.
            Votre mot de passe reste utilisable.
          </p>
          <ul v-if="passkeys.length" class="pk-list">
            <li v-for="p in passkeys" :key="p.id" class="pk-item">
              <div class="pk-info">
                <span class="pk-name">{{ p.name }}</span>
                <span class="pk-meta">
                  Ajoutée le {{ fmtDate(p.created_at) }} ·
                  {{ p.last_used_at ? `utilisée le ${fmtDate(p.last_used_at)}` : 'jamais utilisée' }}
                </span>
              </div>
              <Hint label="Supprimer cette passkey">
                <button class="btn btn-ghost btn-icon btn-sm" @click="pkToDelete = p">✕</button>
              </Hint>
            </li>
          </ul>
          <div v-if="pkStatus.usable" class="settings-actions">
            <button class="btn btn-secondary btn-sm" @click="startAddPasskey">Ajouter une passkey</button>
          </div>
          <p v-else class="form-hint">
            Pour ajouter une passkey, ouvrez l'application depuis <a :href="pkStatus.origin + '/account'">{{ pkStatus.origin }}</a>.
          </p>
        </div>
      </section>

      <AppDialog v-if="pkNameOpen" title="Ajouter une passkey" :dismissible="!pkBusy" @close="pkNameOpen = false">
        <form class="pk-dialog" @submit.prevent="confirmAddPasskey">
          <p class="pk-dialog-title">Ajouter une passkey</p>
          <label class="form-label" for="pk-name">Nom de l'appareil</label>
          <input id="pk-name" v-model="pkName" class="form-control" maxlength="60" autofocus />
          <p class="form-hint">Pour la reconnaître dans la liste, par exemple « iPhone » ou « Mac du salon ».</p>
          <div class="pk-dialog-btns">
            <button type="button" class="btn btn-ghost btn-sm" :disabled="pkBusy" @click="pkNameOpen = false">Annuler</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="pkBusy">{{ pkBusy ? 'En attente de l’appareil…' : 'Continuer' }}</button>
          </div>
        </form>
      </AppDialog>

      <AppDialog v-if="pkToDelete" title="Supprimer la passkey ?" @close="pkToDelete = null">
        <div class="pk-dialog">
          <p class="pk-dialog-title">Supprimer la passkey ?</p>
          <p class="form-hint">« {{ pkToDelete.name }} » ne permettra plus de se connecter. Pensez aussi à la retirer du gestionnaire de mots de passe de l'appareil.</p>
          <div class="pk-dialog-btns">
            <button class="btn btn-ghost btn-sm" @click="pkToDelete = null">Annuler</button>
            <button class="btn btn-danger btn-sm" @click="deletePasskey">Supprimer</button>
          </div>
        </div>
      </AppDialog>
    </main>
  </AppLayout>
</template>

<style scoped>
.pk-list { list-style: none; display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.pk-item { display: flex; align-items: center; gap: 10px; padding: 8px 8px 8px 12px; background: var(--light); border-radius: var(--radius-sm); }
.pk-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pk-name { font-size: 0.875rem; font-weight: 600; color: var(--text); }
.pk-meta { font-size: 0.78rem; color: var(--muted); }
.pk-dialog {
  width: 100%; max-width: 400px; padding: 22px;
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column; gap: 8px;
}
.pk-dialog-title { font-size: 1rem; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.pk-dialog-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }
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
