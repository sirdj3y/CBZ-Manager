<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { tomesApi } from '../../api/tomes'
import { useLibraryStore } from '../../stores/library'
import { useNotificationStore } from '../../stores/notifications'
import TagInput from '../ui/TagInput.vue'

const props = defineProps({
  tomeIds: { type: Array, required: true },
})
const emit = defineEmits(['close', 'saved'])

const library = useLibraryStore()
const notif = useNotificationStore()

const form = ref({ Publisher: '', Writer: '', Penciller: '', LanguageISO: '' })
const saving = ref(false)

const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

// Badges (TagInput) plutôt qu'un texte comma-séparé libre — même traitement que les popups
// Album/Série (MetadataDrawer.vue/SeriesMetadataModal.vue). form.Penciller/Writer/Publisher
// restent des chaînes (format attendu par l'API), ces fonctions ne font que convertir pour
// l'affichage.
function toTags(str) { return (str || '').split(',').map(s => s.trim()).filter(Boolean) }
function updateTags(key, arr) { form.value[key] = arr.join(', ') }

async function save() {
  const fields = {}
  if (form.value.Publisher.trim())   fields.Publisher   = form.value.Publisher.trim()
  if (form.value.Writer.trim())      fields.Writer      = form.value.Writer.trim()
  if (form.value.Penciller.trim())   fields.Penciller   = form.value.Penciller.trim()
  if (form.value.LanguageISO.trim()) fields.LanguageISO = form.value.LanguageISO.trim()
  if (!Object.keys(fields).length) {
    notif.error('Aucun champ à appliquer')
    return
  }
  saving.value = true
  try {
    const { data } = await tomesApi.updateMetadataBulk(props.tomeIds, fields)
    if (data.errors) notif.error(`${data.errors} erreur(s) pendant l'édition`)
    else notif.success(`${data.ok} album(s) mis à jour`)
    emit('saved')
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'édition")
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (!library.authorNames.writers.length) library.fetchAuthors()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'Enter' && !saving.value) save()
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click="$emit('close')" />
    <div class="modal-wrap">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">Éditer en lot</p>
            <p class="modal-subtitle">{{ tomeIds.length }} album{{ tomeIds.length > 1 ? 's' : '' }} sélectionné{{ tomeIds.length > 1 ? 's' : '' }}</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <div class="modal-body">
          <p class="modal-hint">
            Seuls les champs renseignés ci-dessous seront appliqués, à tous les albums sélectionnés — et remplaceront leur valeur actuelle. Laisser vide un champ ne le modifie pas.
          </p>
          <div class="field">
            <label class="form-label">Scénariste</label>
            <TagInput
              :model-value="toTags(form.Writer)" :suggestions="authorPool"
              placeholder="Ajouter un scénariste…"
              @update:model-value="updateTags('Writer', $event)"
            />
          </div>
          <div class="field">
            <label class="form-label">Dessinateur</label>
            <TagInput
              :model-value="toTags(form.Penciller)" :suggestions="authorPool"
              placeholder="Ajouter un dessinateur…"
              @update:model-value="updateTags('Penciller', $event)"
            />
          </div>
          <div class="field">
            <label class="form-label">Éditeur</label>
            <TagInput
              :model-value="toTags(form.Publisher)" :suggestions="library.authorNames.publishers"
              placeholder="Ajouter un éditeur…"
              @update:model-value="updateTags('Publisher', $event)"
            />
          </div>
          <div class="field">
            <label class="form-label">Langue (ISO)</label>
            <input v-model="form.LanguageISO" type="text" class="form-control" placeholder="ex: fr" />
          </div>
        </div>

        <div class="modal-footer">
          <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Application…' : 'Appliquer' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop { position: fixed; inset: 0; z-index: 200; background: var(--overlay-bg); }
.modal-wrap {
  position: fixed; inset: 0; z-index: 201;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; pointer-events: none;
}
.modal-box {
  pointer-events: auto;
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  width: 100%; max-width: 420px; max-height: 90vh;
  display: flex; flex-direction: column;
}
.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header-info { flex: 1; min-width: 0; }
.modal-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.modal-subtitle { font-size: 0.75rem; color: var(--muted); margin-top: 2px; }

.modal-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.modal-hint {
  font-size: 0.8125rem; color: var(--muted);
  background: var(--light); border-radius: var(--radius-sm);
  padding: 8px 10px; line-height: 1.4;
}
.field { display: flex; flex-direction: column; gap: 3px; }
/* Libellés allégés — même traitement que les popups Album/Série. */
.field .form-label { font-size: 0.72rem; margin-bottom: 0; }

.modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 8px;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}
</style>
