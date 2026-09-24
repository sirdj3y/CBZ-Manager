<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../../components/layout/AppLayout.vue'
import FolderBrowser from '../../components/ui/FolderBrowser.vue'
import { settingsApi } from '../../api/settings'
import { libraryApi } from '../../api/library'
import client from '../../api/client'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'
import { useAuthStore } from '../../stores/auth'

const notif = useNotificationStore()
const library = useLibraryStore()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()

// Onglet piloté par la route — même pattern que la page Comptes (Utilisateurs/Profils).
const activeTab = computed(() => route.path === '/settings/data' ? 'data' : 'library')
function setTab(tab) {
  router.push(tab === 'data' ? '/settings/data' : '/settings/library')
}

// ── Onglet Général ───────────────────────────────────────────────────────────
const DEFAULT_RENAME_PATTERN = '{Série} - T{Numéro} - {Titre}'
const lastScan = ref(null)
const settings = ref({ library_subdir: '', media_root_name: '', google_books_configured: false, comicvine_configured: false, rename_pattern: '' })
const form = ref({ library_subdir: '', google_books_api_key: '', comicvine_api_key: '', rename_pattern: '' })
const saving = ref(false)
const savingKeys = ref(false)
const savingRename = ref(false)
const showFolderBrowser = ref(false)

const bdIndex = ref({ built: false, count: 0, built_at: null })
const bdProgress = ref({ status: 'idle', processed: 0, total: 0 })
let bdPollTimer = null

const bdIndexLabel = computed(() => {
  if (bdProgress.value.status === 'running') {
    return `Reconstruction en cours… ${bdProgress.value.processed}/${bdProgress.value.total} lettres`
  }
  if (!bdIndex.value.built) return "Index non construit — la recherche Bedetheque ne fonctionnera pas"
  const d = bdIndex.value.built_at ? new Date(bdIndex.value.built_at * 1000) : null
  const dateStr = d ? d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
  return `${bdIndex.value.count.toLocaleString('fr-FR')} séries indexées — ${dateStr}`
})

const scanStatus = computed(() => {
  const sp = library.scanProgress
  if (sp.status === 'running') return { label: `Scan en cours… ${sp.processed}/${sp.total}`, type: 'running' }
  if (!lastScan.value || lastScan.value.status === 'never') return { label: 'Aucun scan effectué', type: 'never' }
  if (lastScan.value.status === 'error') return { label: 'Dernier scan : erreur', type: 'error' }
  const d = lastScan.value.finished_at ? new Date(lastScan.value.finished_at) : null
  const dateStr = d ? d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
  return { label: `Dernier scan : ${lastScan.value.processed} fichiers — ${dateStr}`, type: 'done' }
})

watch(() => library.scanProgress.status, async (status) => {
  if (status === 'done' || status === 'error') {
    const { data } = await libraryApi.getLastScan()
    lastScan.value = data
  }
})

onMounted(async () => {
  const { data } = await settingsApi.get()
  settings.value = data
  form.value.library_subdir = data.library_subdir
  form.value.rename_pattern = data.rename_pattern
  const { data: scanData } = await libraryApi.getLastScan()
  lastScan.value = scanData
  await refreshBdStatus()
})

onUnmounted(() => {
  if (bdPollTimer) clearInterval(bdPollTimer)
})

async function refreshBdStatus() {
  try {
    const { data } = await settingsApi.bedethequeIndexStatus()
    bdIndex.value = data
  } catch { /* ignoré */ }
}

async function refreshBedethequeIndex() {
  try {
    await settingsApi.refreshBedethequeIndex()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur')
    return
  }
  notif.info('Reconstruction de l\'index Bedetheque lancée — plusieurs minutes')
  bdPollTimer = setInterval(async () => {
    const { data } = await settingsApi.bedethequeIndexProgress()
    bdProgress.value = data
    if (data.status !== 'running') {
      clearInterval(bdPollTimer)
      bdPollTimer = null
      await refreshBdStatus()
      if (data.status === 'done') notif.success('Index Bedetheque à jour')
      if (data.status === 'error') notif.error('Échec de la reconstruction de l\'index')
    }
  }, 2000)
}

async function saveLibrary() {
  saving.value = true
  try {
    await settingsApi.update({ library_subdir: form.value.library_subdir })
    notif.success('Dossier sauvegardé')
    settings.value.library_subdir = form.value.library_subdir
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur')
  } finally {
    saving.value = false
  }
}

async function launchScan() {
  await library.triggerScan()
  notif.info('Scan lancé…')
}

async function saveApiKeys() {
  savingKeys.value = true
  try {
    const payload = {}
    if (form.value.google_books_api_key) payload.google_books_api_key = form.value.google_books_api_key
    if (form.value.comicvine_api_key) payload.comicvine_api_key = form.value.comicvine_api_key
    const { data } = await settingsApi.update(payload)
    settings.value = data
    form.value.google_books_api_key = ''
    form.value.comicvine_api_key = ''
    notif.success('Clés API sauvegardées')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur')
  } finally {
    savingKeys.value = false
  }
}

async function saveRenamePattern() {
  savingRename.value = true
  try {
    const { data } = await settingsApi.update({ rename_pattern: form.value.rename_pattern })
    settings.value = data
    notif.success('Modèle de renommage sauvegardé')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur')
  } finally {
    savingRename.value = false
  }
}

function resetRenamePattern() {
  form.value.rename_pattern = DEFAULT_RENAME_PATTERN
}

// ── Onglet Sauvegarde & BDD ──────────────────────────────────────────────────
const importResult = ref(null)
const showResetConfirm = ref(false)
const resetting = ref(false)

async function importBackup(event) {
  const file = event.target.files[0]
  if (!file) return
  importResult.value = null
  const formData = new FormData()
  formData.append('file', file)
  try {
    const { data } = await client.post('/api/export/import', formData)
    importResult.value = {
      error: false,
      message: `${data.updated} tomes restaurés, ${data.not_found} introuvables.`,
    }
    notif.success(`Restauration terminée : ${data.updated} tomes mis à jour`)
  } catch (e) {
    importResult.value = { error: true, message: e.response?.data?.detail || 'Erreur lors de l\'import' }
    notif.error('Erreur lors de l\'import')
  }
  event.target.value = ''
}

async function resetDatabase() {
  resetting.value = true
  try {
    await settingsApi.resetDb()
    notif.success('Base de données réinitialisée. Rechargement…')
    setTimeout(() => window.location.reload(), 1500)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la réinitialisation')
  } finally {
    resetting.value = false
    showResetConfirm.value = false
  }
}
</script>

<template>
  <AppLayout>
    <main class="settings-main">
      <h1 class="settings-heading">Bibliothèque</h1>

      <div class="tabs-row">
        <button @click="setTab('library')" :class="['tab-btn', { 'tab-btn-active': activeTab === 'library' }]">Général</button>
        <button v-if="authStore.isAdmin" @click="setTab('data')" :class="['tab-btn', { 'tab-btn-active': activeTab === 'data' }]">Sauvegarde &amp; BDD</button>
      </div>

      <!-- ── Onglet Général ── -->
      <section v-if="activeTab === 'library'" class="card settings-section">
        <div class="card-body">

          <div class="settings-section-title">Bibliothèque</div>

          <div class="form-group">
            <label class="form-label">Dossier de la bibliothèque</label>
            <div class="path-input-group">
              <input
                type="text"
                class="form-control path-input"
                :value="`${settings.media_root_name}/${form.library_subdir}`"
                readonly
              />
              <button class="btn btn-secondary btn-sm path-browse-btn" type="button" @click="showFolderBrowser = true">Parcourir…</button>
            </div>
            <div class="form-hint">Laissez vide pour utiliser la racine du dossier monté.</div>
          </div>

          <div class="scan-row">
            <button @click="launchScan" class="btn btn-primary btn-sm" :disabled="library.scanProgress.status === 'running'">
              {{ library.scanProgress.status === 'running' ? 'Scan en cours…' : 'Scanner la bibliothèque' }}
            </button>
            <div v-if="scanStatus.type === 'running'" class="scan-status scan-status-running">
              <span class="scan-spinner"></span>
              {{ scanStatus.label }}
              <span class="scan-progress-bar">
                <span class="scan-progress-fill" :style="{ width: library.scanProgress.total ? (library.scanProgress.processed / library.scanProgress.total * 100) + '%' : '0%' }"></span>
              </span>
            </div>
            <span v-else-if="scanStatus.type === 'error'" class="scan-inline scan-inline-error">{{ scanStatus.label }}</span>
            <span v-else-if="scanStatus.type === 'done'" class="scan-inline">{{ scanStatus.label }}</span>
            <span v-else class="scan-inline scan-inline-never">{{ scanStatus.label }}</span>
          </div>

          <FolderBrowser
            v-if="showFolderBrowser"
            :initial-path="form.library_subdir"
            @select="(path) => { form.library_subdir = path; showFolderBrowser = false; saveLibrary() }"
            @cancel="showFolderBrowser = false"
          />

          <div class="section-divider" />

          <div class="settings-section-title">Renommage à l'import</div>
          <div class="form-group">
            <label class="form-label">Modèle</label>
            <input v-model="form.rename_pattern" type="text" class="form-control"
              placeholder="ex: {Série} - T{Numéro} - {Titre}" />
            <div class="form-hint">
              Appliqué automatiquement à chaque import. Tokens : <code>{Série}</code> <code>{Numéro}</code>
              <code>{Titre}</code> <code>{Année}</code> <code>{Dessinateur}</code> <code>{Scénariste}</code> <code>{Éditeur}</code>.
              Laissez vide pour ne jamais renommer les fichiers importés.
            </div>
          </div>
          <div class="settings-actions">
            <button @click="saveRenamePattern" :disabled="savingRename" class="btn btn-primary btn-sm">Sauvegarder le modèle</button>
            <button @click="resetRenamePattern" :disabled="savingRename" class="btn btn-secondary btn-sm">Réinitialiser</button>
          </div>

          <div class="section-divider" />

          <div class="settings-section-title">Clés API</div>

          <div class="form-group">
            <label class="form-label">
              Google Books
              <span :class="['api-status', settings.google_books_configured ? 'api-status-ok' : 'api-status-none']">
                {{ settings.google_books_configured ? '✓ Configurée' : 'Non configurée' }}
              </span>
            </label>
            <input v-model="form.google_books_api_key" type="password" class="form-control"
              :placeholder="settings.google_books_configured ? '••••••••••••••••' : 'Nouvelle clé (optionnel)'" />
          </div>
          <div class="form-group">
            <label class="form-label">
              ComicVine
              <span :class="['api-status', settings.comicvine_configured ? 'api-status-ok' : 'api-status-none']">
                {{ settings.comicvine_configured ? '✓ Configurée' : 'Non configurée' }}
              </span>
            </label>
            <input v-model="form.comicvine_api_key" type="password" class="form-control"
              :placeholder="settings.comicvine_configured ? '••••••••••••••••' : 'Nouvelle clé (optionnel)'" />
          </div>
          <div class="settings-actions">
            <button @click="saveApiKeys" :disabled="savingKeys" class="btn btn-primary btn-sm">Sauvegarder les clés</button>
          </div>

          <div class="section-divider" />

          <div class="settings-section-title">Index Bedetheque</div>
          <p class="form-hint" style="margin-top:-6px; margin-bottom: 12px;">
            Utilisé pour retrouver rapidement une série sans dépendre du moteur de recherche du site.
            Ne se met pas à jour automatiquement — à rafraîchir manuellement de temps en temps.
          </p>
          <div class="scan-row">
            <button @click="refreshBedethequeIndex" class="btn btn-secondary btn-sm" :disabled="bdProgress.status === 'running'">
              {{ bdProgress.status === 'running' ? 'Reconstruction…' : "Rafraîchir l'index" }}
            </button>
            <div v-if="bdProgress.status === 'running'" class="scan-status scan-status-running">
              <span class="scan-spinner"></span>
              {{ bdIndexLabel }}
              <span class="scan-progress-bar">
                <span class="scan-progress-fill" :style="{ width: bdProgress.total ? (bdProgress.processed / bdProgress.total * 100) + '%' : '0%' }"></span>
              </span>
            </div>
            <span v-else :class="['scan-inline', { 'scan-inline-never': !bdIndex.built }]">{{ bdIndexLabel }}</span>
          </div>

        </div>
      </section>

      <!-- ── Onglet Sauvegarde & BDD ── -->
      <section v-else class="card settings-section">
        <div class="card-body">

          <div class="settings-section-title">Sauvegarde</div>

          <div class="form-group">
            <label class="form-label">Exporter</label>
            <div class="form-hint">Exporte toutes les métadonnées, annotations et progressions de lecture dans un fichier JSON.</div>
            <div class="settings-actions">
              <a href="/api/export" download class="btn btn-secondary btn-sm">Exporter la sauvegarde</a>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Importer</label>
            <div class="form-hint">Restaure les données depuis un fichier de sauvegarde. Les tomes existants sont mis à jour, les tomes introuvables sont ignorés.</div>
            <div class="settings-actions">
              <label class="btn btn-secondary btn-sm" style="cursor:pointer">
                Choisir un fichier…
                <input type="file" accept=".json" style="display:none" @change="importBackup" />
              </label>
              <span v-if="importResult" :class="['import-result', importResult.error ? 'import-error' : 'import-ok']">
                {{ importResult.message }}
              </span>
            </div>
          </div>

          <div class="section-divider" />

          <div class="settings-section-title">Base de données</div>

          <div class="danger-zone">
            <div class="danger-zone-title">Supprimer la base de données</div>
            <p class="form-hint">Supprime définitivement toutes les données (séries, albums, métadonnées, covers). Le contenu de votre bibliothèque sur le disque n'est pas affecté. Un nouveau scan sera nécessaire.</p>
            <div class="settings-actions" style="margin-top: 10px">
              <button v-if="!showResetConfirm" class="btn btn-danger btn-sm" @click="showResetConfirm = true">
                Supprimer la base de données…
              </button>
              <template v-else>
                <span class="reset-confirm-label">Confirmer la suppression ? Cette action est irréversible.</span>
                <button class="btn btn-danger btn-sm" :disabled="resetting" @click="resetDatabase">
                  {{ resetting ? 'Suppression…' : 'Oui, tout supprimer' }}
                </button>
                <button class="btn btn-secondary btn-sm" @click="showResetConfirm = false">Annuler</button>
              </template>
            </div>
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
.section-divider { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
.form-group { margin-bottom: 14px; }
.form-hint { margin-top: 5px; font-size: 0.8rem; color: var(--muted); }
.form-hint code { background: var(--light); padding: 1px 5px; border-radius: 3px; font-size: 0.8rem; }
.settings-actions { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }

/* Onglets soulignés — même style que la page Comptes. */
.tabs-row {
  display: flex; gap: 22px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}
.tab-btn {
  padding: 0 0 10px;
  background: none; border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-family: var(--font);
  font-size: 0.85rem; font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn-active { color: var(--vermilion); border-bottom-color: var(--vermilion); }

/* Path input group */
.path-input-group {
  display: flex; align-items: stretch; gap: 0;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  overflow: hidden;
}
.path-input {
  flex: 1; border: none; border-radius: 0;
  font-family: monospace; font-size: 0.82rem;
  background: var(--light); color: var(--text);
  padding: 6px 10px; min-width: 0;
  cursor: default;
}
.path-input:focus { outline: none; box-shadow: none; }
.path-browse-btn {
  border-radius: 0; border: none;
  border-left: 1px solid var(--border);
  flex-shrink: 0;
}

/* Scan row */
.scan-row {
  display: flex; align-items: center; gap: 12px;
  margin-top: 12px; flex-wrap: wrap;
}
.scan-status {
  flex: 1; min-width: 0;
  font-size: 0.8rem; padding: 6px 10px;
  border-radius: var(--radius-sm); display: flex; align-items: center; gap: 8px;
  color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent);
}
.scan-inline {
  font-size: 0.8rem; font-style: italic; color: var(--muted);
}
.scan-inline-error { color: var(--danger); }
.scan-inline-never { color: var(--muted); }
.scan-spinner { width: 12px; height: 12px; flex-shrink: 0; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.scan-progress-bar { flex: 1; height: 4px; background: color-mix(in srgb, var(--primary) 20%, transparent); border-radius: 2px; overflow: hidden; }
.scan-progress-fill { height: 100%; background: var(--primary); transition: width 0.3s ease; }

.api-status { font-size: 0.75rem; font-weight: 500; margin-left: 8px; padding: 1px 7px; border-radius: 20px; }
.api-status-ok { background-color: var(--success-bg); color: var(--success-text); }
.api-status-none { background-color: var(--light); color: var(--muted); border: 1px solid var(--border); }

.import-result { font-size: 0.82rem; padding: 3px 10px; border-radius: 4px; }
.import-ok { background: var(--success-bg); color: var(--success-text); }
.import-error { background: var(--danger-bg); color: var(--danger-text); }
.danger-zone {
  border: 1px solid var(--danger-bg); border-radius: var(--radius-sm); padding: 16px;
}
.danger-zone-title { font-size: 0.9rem; font-weight: 600; color: var(--danger); margin-bottom: 6px; }
.reset-confirm-label { font-size: 0.82rem; color: var(--danger); }
</style>
