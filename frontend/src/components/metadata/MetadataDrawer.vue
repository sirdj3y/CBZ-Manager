<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import MetadataForm from './MetadataForm.vue'
import ScraperModal from './ScraperModal.vue'
import StarRating from '../ui/StarRating.vue'
import TagInput from '../ui/TagInput.vue'
import { tomesApi } from '../../api/tomes'
import { useNotificationStore } from '../../stores/notifications'
import { useRouter } from 'vue-router'

const props = defineProps({
  tome: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const notif = useNotificationStore()
const router = useRouter()
const metadata = ref({})
const original = ref({})
const saving = ref(false)
const showScraper = ref(false)
const confirmDelete = ref(false)
const deleting = ref(false)

// Annotations utilisateur
const userRating = ref(props.tome.user_rating || 0)
const userNotes = ref(props.tome.user_notes || '')
const userTags = ref([...(props.tome.user_tags || [])])

const canEdit = props.tome.file_format === 'cbz'
const fileInfo = ref(null)

onMounted(async () => {
  const [metaRes, infoRes] = await Promise.all([
    tomesApi.getMetadata(props.tome.id),
    tomesApi.getFileInfo(props.tome.id),
  ])
  metadata.value = { ...metaRes.data }
  original.value = { ...metaRes.data }
  fileInfo.value = infoRes.data
  window.addEventListener('keydown', onKey)
})

function fmtSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' Go'
}

onUnmounted(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape') {
    if (showScraper.value) { showScraper.value = false; return }
    emit('close')
  }
}

function cancel() { metadata.value = { ...original.value }; emit('close') }

async function save() {
  saving.value = true
  try {
    // Sauvegarde métadonnées ComicInfo (CBZ seulement)
    if (canEdit) {
      const { data } = await tomesApi.updateMetadata(props.tome.id, metadata.value)
      metadata.value = { ...data }
      original.value = { ...data }
    }
    // Sauvegarde annotations (tous formats)
    await tomesApi.updateUserData(props.tome.id, {
      user_rating: userRating.value || null,
      user_notes: userNotes.value || null,
      user_tags: userTags.value,
    })
    notif.success('Sauvegardé')
    emit('saved')
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la sauvegarde')
  } finally {
    saving.value = false
  }
}

async function deleteTome() {
  deleting.value = true
  try {
    const { data } = await tomesApi.deleteFile(props.tome.id)
    notif.success('Album supprimé')
    emit('deleted', { tome_id: props.tome.id, series_deleted: data.series_deleted, series_id: data.series_id })
    emit('close')
    if (data.series_deleted) router.push('/series')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

function applyScraperResult(result) {
  showScraper.value = false
  if (result.title) metadata.value.Title = result.title
  if (result.authors?.length) metadata.value.Writer = result.authors.join(', ')
  if (result.publisher) metadata.value.Publisher = result.publisher
  if (result.year) metadata.value.Year = result.year
  if (result.pages) metadata.value.PageCount = String(result.pages)
}
</script>

<template>
  <Teleport to="body">
    <!-- Backdrop -->
    <div class="modal-backdrop" @click="$emit('close')" />

    <!-- Modal -->
    <div class="modal-wrap">
      <div class="modal-box">
        <!-- Header -->
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">{{ tome.title || tome.filename }}</p>
            <p class="modal-subtitle">{{ tome.file_format.toUpperCase() }}</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <!-- Scraper bar -->
        <div class="modal-scraper-bar">
          <span class="modal-scraper-hint">Remplir automatiquement les métadonnées</span>
          <button @click="showScraper = true" class="btn btn-secondary btn-sm">🔍 Rechercher</button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <!-- CBR warning -->
          <div v-if="!canEdit" class="alert alert-warning modal-warning">
            ⚠ Les fichiers CBR sont en lecture seule. Convertissez en CBZ pour modifier.
          </div>

          <MetadataForm v-model="metadata" :readonly="!canEdit" />

          <!-- Annotations personnelles — même style que MetadataForm -->
          <div class="meta-form">
            <div class="meta-section-label">Annotations personnelles</div>
            <div class="meta-field">
              <label class="form-label">Note</label>
              <StarRating v-model="userRating" />
            </div>
            <div class="meta-field">
              <label class="form-label">Étiquettes</label>
              <TagInput v-model="userTags" />
            </div>
            <div class="meta-field">
              <label class="form-label">Commentaire</label>
              <textarea v-model="userNotes" class="form-control annotations-textarea" rows="3" placeholder="Notes personnelles…" />
            </div>
          </div>

          <!-- Infos fichier -->
          <div class="file-info-card" v-if="fileInfo">
            <div class="file-info-line">
              <span class="file-info-label">Chemin :</span>
              <span class="file-info-path">{{ fileInfo.filepath }}</span>
            </div>
            <div class="file-info-line">
              <span class="file-info-label">Taille :</span>
              <span class="file-info-value">{{ fmtSize(fileInfo.file_size) }}</span>
            </div>
            <div class="file-info-line">
              <span class="file-info-label">Résolution :</span>
              <span class="file-info-value">{{ fileInfo.image_width && fileInfo.image_height ? `${fileInfo.image_width} × ${fileInfo.image_height} px` : '—' }}</span>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="btn btn-ghost btn-sm btn-danger-ghost" @click="confirmDelete = true">Supprimer</button>
          <div class="modal-footer-spacer" />
          <button @click="cancel" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Sauvegarde…' : 'Sauvegarder' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Popup confirmation suppression -->
    <div v-if="confirmDelete" class="confirm-backdrop" @click.self="confirmDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer l'album ?</p>
        <p class="confirm-desc"><strong>{{ tome.title || tome.filename }}</strong> et son fichier seront supprimés définitivement.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteTome" :disabled="deleting">
            {{ deleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Scraper modal -->
    <ScraperModal
      v-if="showScraper"
      :series="metadata.Series"
      :number="metadata.Number"
      @select="applyScraperResult"
      @close="showScraper = false"
    />
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--overlay-bg);
}

.modal-wrap {
  position: fixed;
  inset: 0;
  z-index: 201;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  pointer-events: none;
}

.modal-box {
  pointer-events: auto;
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-header-info {
  flex: 1;
  min-width: 0;
}

.modal-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modal-subtitle {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 2px;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
}

.modal-scraper-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px;
  background: var(--light);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 12px;
}
.modal-scraper-hint {
  font-size: 0.8rem; color: var(--muted);
}

.modal-warning {
  margin-bottom: 14px;
  font-size: 0.8125rem;
}

.modal-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

.modal-footer-spacer {
  flex: 1;
}

/* Annotations intégrées dans le style MetadataForm */
.meta-form {
  display: flex; flex-direction: column; gap: 12px; padding: 4px 0;
}
.meta-field {
  display: flex; flex-direction: column; gap: 4px;
}
.meta-section-label {
  font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted);
  padding-top: 8px; border-top: 1px solid var(--border);
}
.annotations-textarea {
  resize: vertical; font-family: var(--font);
}

.file-info-card {
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  display: flex; flex-direction: column; gap: 6px;
}
.file-info-line {
  display: flex; gap: 10px; align-items: baseline;
}
.file-info-label {
  font-size: 0.75rem; color: var(--muted);
  min-width: 72px; flex-shrink: 0;
}
.file-info-value { font-size: 0.8rem; color: var(--text); }
.file-info-path { font-family: monospace; font-size: 0.7rem; color: var(--muted); overflow-wrap: break-word; word-break: break-word; }

.btn-danger-ghost { color: var(--danger); }
.btn-danger-ghost:hover { background: var(--danger-bg-light); }

.confirm-backdrop {
  position: fixed; inset: 0; z-index: 300;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.confirm-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  padding: 24px; max-width: 400px; width: 100%;
}
.confirm-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.confirm-desc { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.confirm-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
