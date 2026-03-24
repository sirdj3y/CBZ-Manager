<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import FolderBrowser from '../../components/ui/FolderBrowser.vue'
import { settingsApi } from '../../api/settings'
import { libraryApi } from '../../api/library'
import { useNotificationStore } from '../../stores/notifications'
import { useLibraryStore } from '../../stores/library'

const notif = useNotificationStore()
const library = useLibraryStore()
const lastScan = ref(null)
const settings = ref({ library_subdir: '', media_root_name: '', google_books_configured: false, comicvine_configured: false })
const form = ref({ library_subdir: '', google_books_api_key: '', comicvine_api_key: '' })
const saving = ref(false)
const savingKeys = ref(false)
const showFolderBrowser = ref(false)

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
  const { data: scanData } = await libraryApi.getLastScan()
  lastScan.value = scanData
})

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
</script>

<template>
  <AppLayout>
    <main class="settings-main">
      <h1 class="settings-heading">Bibliothèque</h1>
      <section class="card settings-section">
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

        </div>
      </section>
    </main>
  </AppLayout>
</template>

<style scoped>
.settings-main {
  flex: 1; padding: 24px 20px;
  max-width: 680px; margin: 0 auto; width: 100%;
}
.settings-heading {
  font-size: 1.4rem; font-weight: 700;
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
.settings-actions { display: flex; gap: 10px; margin-top: 16px; }

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
</style>
