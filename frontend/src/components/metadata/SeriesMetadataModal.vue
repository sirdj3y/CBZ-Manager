<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { tomesApi } from '../../api/tomes'
import { libraryApi } from '../../api/library'
import { useNotificationStore } from '../../stores/notifications'

const props = defineProps({
  series: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved', 'deleted'])

const notif = useNotificationStore()
const form = ref({ Series: '', Publisher: '', Writer: '', Penciller: '' })
const saving = ref(false)
const confirmDelete = ref(false)
const deleting = ref(false)

onMounted(async () => {
  if (props.series.tomes?.length) {
    try {
      const { data } = await tomesApi.getMetadata(props.series.tomes[0].id)
      form.value.Series    = data.Series    || props.series.name
      form.value.Publisher = data.Publisher || ''
      form.value.Writer    = data.Writer    || ''
      form.value.Penciller = data.Penciller || ''
    } catch {
      form.value.Series = props.series.name
    }
  } else {
    form.value.Series = props.series.name
  }
  window.addEventListener('keydown', onKey)
})

onUnmounted(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}

async function deleteSeries() {
  deleting.value = true
  try {
    await libraryApi.deleteSeries(props.series.id)
    notif.success('Série supprimée')
    emit('deleted', props.series.id)
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

async function save() {
  if (!props.series.tomes?.length) {
    notif.error('Aucun album dans cette série')
    return
  }
  saving.value = true
  const patch = {}
  if (form.value.Series.trim())    patch.Series    = form.value.Series.trim()
  if (form.value.Publisher.trim()) patch.Publisher = form.value.Publisher.trim()
  if (form.value.Writer.trim())    patch.Writer    = form.value.Writer.trim()
  if (form.value.Penciller.trim()) patch.Penciller = form.value.Penciller.trim()

  let errors = 0
  try {
    const { data } = await libraryApi.updateSeriesMetadata(props.series.id, patch)
    errors = data.errors || 0
  } catch {
    errors = 1
  }
  saving.value = false
  if (errors) {
    notif.error(`${errors} album(s) non mis à jour (erreur)`)
  } else {
    notif.success('Métadonnées de la série mises à jour')
  }
  emit('saved')
  emit('close')
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
            <p class="modal-title">{{ series.name }}</p>
            <p class="modal-subtitle">Métadonnées de la série</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <p class="modal-hint">Appliqué à tous les tomes CBZ de la série.</p>

          <div class="field">
            <label class="form-label">Série</label>
            <input v-model="form.Series" type="text" class="form-control" placeholder="Nom de la série" />
          </div>
          <div class="field">
            <label class="form-label">Éditeur</label>
            <input v-model="form.Publisher" type="text" class="form-control" placeholder="ex: Dargaud" />
          </div>
          <div class="field">
            <label class="form-label">Scénariste</label>
            <input v-model="form.Writer" type="text" class="form-control" placeholder="ex: Goscinny" />
          </div>
          <div class="field">
            <label class="form-label">Dessinateur</label>
            <input v-model="form.Penciller" type="text" class="form-control" placeholder="ex: Uderzo" />
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="btn btn-ghost btn-sm btn-danger-ghost" @click="confirmDelete = true">Supprimer la série</button>
          <div style="flex:1"></div>
          <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="save" :disabled="saving" class="btn btn-primary btn-sm">
            {{ saving ? 'Sauvegarde…' : 'Appliquer' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Popup confirmation suppression -->
    <div v-if="confirmDelete" class="confirm-backdrop" @click.self="confirmDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer la série ?</p>
        <p class="confirm-desc"><strong>{{ series.name }}</strong> et tous ses fichiers seront supprimés définitivement.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteSeries" :disabled="deleting">
            {{ deleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; z-index: 200;
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
  max-width: 420px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-header-info { flex: 1; min-width: 0; }
.modal-title {
  font-size: 0.9rem; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.modal-subtitle { font-size: 0.75rem; color: var(--muted); margin-top: 2px; }

.modal-body {
  flex: 1; overflow-y: auto;
  padding: 16px; display: flex; flex-direction: column; gap: 14px;
}

.modal-hint {
  font-size: 0.8125rem; color: var(--muted);
  background: var(--light); border-radius: var(--radius-sm);
  padding: 8px 10px;
}
.field { display: flex; flex-direction: column; gap: 4px; }

.modal-footer {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

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
