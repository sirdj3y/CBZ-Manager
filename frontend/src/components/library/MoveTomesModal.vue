<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { libraryApi } from '../../api/library'
import { tomesApi } from '../../api/tomes'
import { useNotificationStore } from '../../stores/notifications'
import AutocompleteInput from '../ui/AutocompleteInput.vue'
import { sortTitle } from '../../utils/text'

const props = defineProps({
  tomeIds: { type: Array, required: true },
})
const emit = defineEmits(['close', 'moved'])

const notif = useNotificationStore()

const loading = ref(true)
const series = ref([])
const seriesName = ref('')
const moving = ref(false)

const suggestions = computed(() => series.value.map(s => s.name))
const target = computed(() => series.value.find(s => s.name === seriesName.value.trim()) || null)

async function load() {
  loading.value = true
  try {
    const { data } = await libraryApi.getSeries()
    series.value = [...data].sort((a, b) => sortTitle(a.name).localeCompare(sortTitle(b.name), 'fr', { sensitivity: 'base' }))
  } catch {
    notif.error('Impossible de charger la liste des séries')
  } finally {
    loading.value = false
  }
}

async function move() {
  if (!target.value) return
  moving.value = true
  try {
    const { data } = await tomesApi.moveTomes(props.tomeIds, target.value.id)
    if (data.errors?.length) notif.error(`${data.errors.length} erreur(s) — ${data.errors[0]}`)
    else notif.success(`${data.ok} album(s) déplacé(s)`)
    emit('moved', data)
    emit('close')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors du déplacement')
  } finally {
    moving.value = false
  }
}

onMounted(() => {
  load()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'Enter' && target.value && !moving.value) move()
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click="$emit('close')" />
    <div class="modal-wrap">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">Déplacer vers une série</p>
            <p class="modal-subtitle">{{ tomeIds.length }} album{{ tomeIds.length > 1 ? 's' : '' }} sélectionné{{ tomeIds.length > 1 ? 's' : '' }}</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <div class="modal-body">
          <div v-if="loading" class="state-box"><span class="state-pulse">Chargement…</span></div>
          <template v-else>
            <div class="field">
              <label class="form-label">Série de destination</label>
              <AutocompleteInput v-model="seriesName" :suggestions="suggestions" show-all-on-focus placeholder="Rechercher une série…" />
            </div>
            <p v-if="target" class="dest-status">✓ « {{ target.name }} » — {{ target.tome_count }} album{{ target.tome_count > 1 ? 's' : '' }}</p>
          </template>
        </div>

        <div class="modal-footer">
          <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="move" :disabled="!target || moving" class="btn btn-primary btn-sm">
            {{ moving ? 'Déplacement…' : 'Déplacer' }}
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
  width: 100%; max-width: 420px; max-height: 80vh;
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

.modal-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.dest-status { font-size: 0.8rem; color: var(--success-text, var(--success)); margin: 2px 0 0; }

.modal-footer {
  display: flex; align-items: center; justify-content: flex-end; gap: 8px;
  padding: 12px 16px; border-top: 1px solid var(--border);
  flex-shrink: 0; background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

.state-box { display: flex; align-items: center; justify-content: center; min-height: 80px; text-align: center; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }
</style>
