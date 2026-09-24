<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { settingsApi } from '../../api/settings'

const props = defineProps({
  initialPath: { type: String, default: '' }
})
const emit = defineEmits(['select', 'cancel'])

const currentPath = ref('')
const selectedPath = ref('')
const mediaRootName = ref('')
const folders = ref([])
const loading = ref(false)
const error = ref(null)

const pathSegments = computed(() => currentPath.value ? currentPath.value.split('/') : [])
const displayPath = computed(() => {
  if (!selectedPath.value) return mediaRootName.value || '(racine)'
  return mediaRootName.value ? `${mediaRootName.value}/${selectedPath.value}` : selectedPath.value
})

async function loadFolders(path) {
  loading.value = true
  error.value = null
  try {
    const { data } = await settingsApi.browse(path)
    folders.value = data.folders
    currentPath.value = data.current_path
    if (data.media_root_name) mediaRootName.value = data.media_root_name
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erreur lors de la navigation'
    folders.value = []
  } finally {
    loading.value = false
  }
}

function navigateTo(path) {
  selectedPath.value = path
  loadFolders(path)
}

function selectFolder(folder) {
  selectedPath.value = folder.path
}

function confirmSelection() {
  emit('select', selectedPath.value)
}

function onKey(e) { if (e.key === 'Escape') emit('cancel') }
onUnmounted(() => window.removeEventListener('keydown', onKey))

onMounted(() => {
  window.addEventListener('keydown', onKey)
  const startPath = props.initialPath || ''
  selectedPath.value = startPath
  loadFolders(startPath)
})
</script>

<template>
  <div class="fb-overlay" @click.self="$emit('cancel')">
    <div class="fb-modal">
      <div class="fb-header">
        <span>Sélectionner un dossier</span>
        <button class="btn btn-ghost btn-sm" @click="$emit('cancel')">✕</button>
      </div>

      <!-- Breadcrumb -->
      <div class="fb-breadcrumb">
        <span class="fb-crumb" :class="{ 'fb-crumb-active': currentPath === '' }" @click="navigateTo('')">Racine</span>
        <template v-for="(segment, index) in pathSegments" :key="index">
          <span class="fb-sep">/</span>
          <span
            class="fb-crumb"
            :class="{ 'fb-crumb-active': index === pathSegments.length - 1 }"
            @click="navigateTo(pathSegments.slice(0, index + 1).join('/'))"
          >{{ segment }}</span>
        </template>
      </div>

      <!-- Sélection courante -->
      <div class="fb-selected">
        <span class="fb-selected-label">Sélection :</span>
        <code class="fb-selected-path">{{ displayPath }}</code>
      </div>

      <!-- Liste -->
      <div class="fb-content">
        <div v-if="loading" class="fb-state">Chargement…</div>
        <div v-else-if="error" class="fb-state fb-error">
          {{ error }}
          <button class="btn btn-ghost btn-sm" @click="loadFolders(currentPath)">Réessayer</button>
        </div>
        <div v-else-if="folders.length === 0" class="fb-state">Aucun sous-dossier</div>
        <ul v-else class="fb-list">
          <li
            v-for="folder in folders"
            :key="folder.path"
            class="fb-item"
            :class="{ 'fb-item-selected': selectedPath === folder.path }"
            @click="selectFolder(folder)"
            @dblclick="navigateTo(folder.path)"
          >
            <span class="fb-icon">📁</span>
            <span class="fb-name">{{ folder.name }}</span>
            <span v-if="folder.has_children" class="fb-arrow" @click.stop="navigateTo(folder.path)">›</span>
          </li>
        </ul>
      </div>

      <!-- Actions -->
      <div class="fb-actions">
        <button class="btn btn-ghost btn-sm" @click="$emit('cancel')">Annuler</button>
        <button class="btn btn-primary btn-sm" @click="confirmSelection">Sélectionner</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fb-overlay {
  position: fixed; inset: 0; z-index: 600;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.fb-modal {
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%; max-width: 520px;
  max-height: 80vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.fb-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem; font-weight: 600; flex-shrink: 0;
}
.fb-breadcrumb {
  display: flex; align-items: center; flex-wrap: wrap; gap: 2px;
  padding: 8px 16px;
  background: var(--light);
  border-bottom: 1px solid var(--border);
  font-size: 0.82rem; flex-shrink: 0;
}
.fb-crumb {
  cursor: pointer; color: var(--vermilion);
  padding: 2px 4px; border-radius: 3px;
}
.fb-crumb:hover { text-decoration: underline; }
.fb-crumb-active { color: var(--text); font-weight: 600; cursor: default; }
.fb-crumb-active:hover { text-decoration: none; }
.fb-sep { color: var(--muted); margin: 0 1px; }

.fb-selected {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 0.82rem; flex-shrink: 0;
}
.fb-selected-label { color: var(--muted); white-space: nowrap; }
.fb-selected-path { color: var(--primary); word-break: break-all; font-size: 0.82rem; }

.fb-content { flex: 1; overflow-y: auto; min-height: 160px; }
.fb-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 20px; color: var(--muted); font-size: 0.875rem; gap: 10px;
}
.fb-error { color: var(--danger); }

.fb-list { list-style: none; margin: 0; padding: 4px 0; }
.fb-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 16px; cursor: pointer;
  font-size: 0.875rem; color: var(--text);
  transition: background 0.1s;
}
.fb-item:hover { background: var(--light); }
.fb-item-selected { background: var(--primary-focus); }
.fb-icon { font-size: 1rem; flex-shrink: 0; }
.fb-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fb-arrow {
  font-size: 1.1rem; color: var(--muted);
  padding: 2px 6px; border-radius: 3px;
}
.fb-arrow:hover { background: var(--border); color: var(--text); }

.fb-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border); flex-shrink: 0;
}
</style>
