<script setup>
import { ref } from 'vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import { useNotificationStore } from '../../stores/notifications'

const notif = useNotificationStore()
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
    const { data } = await import('axios').then(m => m.default.post('/api/export/import', formData))
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
    const { settingsApi } = await import('../../api/settings')
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
      <h1 class="settings-heading">Sauvegarde &amp; BDD</h1>
      <section class="card settings-section">
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
.settings-actions { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
.import-result { font-size: 0.82rem; padding: 3px 10px; border-radius: 4px; }
.import-ok { background: var(--success-bg); color: var(--success-text); }
.import-error { background: var(--danger-bg); color: var(--danger-text); }
.danger-zone {
  border: 1px solid var(--danger-bg); border-radius: var(--radius-sm); padding: 16px;
}
.danger-zone-title { font-size: 0.9rem; font-weight: 600; color: var(--danger); margin-bottom: 6px; }
.reset-confirm-label { font-size: 0.82rem; color: var(--danger); }
</style>
