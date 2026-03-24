<script setup>
import { ref, computed, onMounted } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import ContentToolbar from '../components/layout/ContentToolbar.vue'
import SeriesCard from '../components/library/SeriesCard.vue'
import SeriesMetadataModal from '../components/metadata/SeriesMetadataModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import CoverPickerModal from '../components/library/CoverPickerModal.vue'
import { useLibraryStore } from '../stores/library'
import { libraryApi } from '../api/library'
import { useNotificationStore } from '../stores/notifications'

const library = useLibraryStore()
const notif = useNotificationStore()

const activeLetter = ref('')
const selectedSeries = ref(null)
const showSeriesMeta = ref(false)
const showRename = ref(false)
const showConverter = ref(false)
const showCoverPicker = ref(false)
const confirmDeleteSeries = ref(null) // series object to delete

onMounted(() => {
  if (library.series.length === 0) library.fetchSeries()
})

const filteredSeries = computed(() => {
  let list = library.filteredSeries

  const norm = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  if (activeLetter.value) {
    if (activeLetter.value === '#') {
      list = list.filter(s => /^[^a-z]/.test(norm(s.name)))
    } else {
      const l = norm(activeLetter.value)
      list = list.filter(s => norm(s.name).startsWith(l))
    }
  }

  return list
})

async function loadSeriesDetail(series) {
  try {
    const { data } = await libraryApi.getSeriesDetail(series.id)
    selectedSeries.value = data
  } catch {
    selectedSeries.value = { ...series, tomes: [] }
  }
}

async function handleEdit(series) {
  await loadSeriesDetail(series)
  showSeriesMeta.value = true
}

async function handleRename(series) {
  await loadSeriesDetail(series)
  showRename.value = true
}

async function handleConvert(series) {
  await loadSeriesDetail(series)
  showConverter.value = true
}

async function handleSetCover(series) {
  await loadSeriesDetail(series)
  showCoverPicker.value = true
}

async function handleDelete(series) {
  confirmDeleteSeries.value = series
}

async function confirmDelete() {
  if (!confirmDeleteSeries.value) return
  try {
    await libraryApi.deleteSeries(confirmDeleteSeries.value.id)
    library.series = library.series.filter(s => s.id !== confirmDeleteSeries.value.id)
    notif.success('Série supprimée')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    confirmDeleteSeries.value = null
  }
}

async function handleToggleHidden(series) {
  const { data } = await libraryApi.toggleSeriesHidden(series.id)
  // Update in-place in the store list
  const s = library.series.find(s => s.id === series.id)
  if (s) s.hidden = data.hidden
  notif.success(data.hidden ? 'Série masquée' : 'Série affichée')
}
</script>

<template>
  <AppLayout>
    <ContentToolbar
      :count="filteredSeries.length"
      active-view="series"
      :active-letter="activeLetter"
      :filter-values="library.filters"
      @letter="(l) => activeLetter = l"
      @filter-change="(f) => library.filters = f"
    />

    <main class="content-area">
      <div v-if="library.loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>

      <div v-else-if="filteredSeries.length === 0 && !library.search && !activeLetter" class="state-box">
        <div class="state-icon">📚</div>
        <p class="state-title">Bibliothèque vide</p>
        <p class="state-desc">Configurez le chemin dans les paramètres et lancez un scan.</p>
      </div>

      <div v-else-if="filteredSeries.length === 0" class="state-box">
        <p class="state-desc">Aucun résultat</p>
      </div>

      <div v-else class="series-grid">
        <SeriesCard
          v-for="s in filteredSeries"
          :key="s.id"
          :series="s"
          @edit="handleEdit"
          @rename="handleRename"
          @convert="handleConvert"
          @set-cover="handleSetCover"
          @toggle-hidden="handleToggleHidden"
          @delete="handleDelete"
        />
      </div>
    </main>

    <SeriesMetadataModal
      v-if="showSeriesMeta && selectedSeries"
      :series="selectedSeries"
      @close="showSeriesMeta = false"
      @saved="library.fetchSeries()"
    />

    <RenameModal
      v-if="showRename && selectedSeries"
      :tomes="selectedSeries.tomes"
      :series-name="selectedSeries.name"
      @close="showRename = false"
      @done="showRename = false"
    />

    <ConverterModal
      v-if="showConverter && selectedSeries"
      :tomes="selectedSeries.tomes"
      @close="showConverter = false"
      @done="showConverter = false"
    />

    <CoverPickerModal
      v-if="showCoverPicker && selectedSeries"
      :series="selectedSeries"
      @close="showCoverPicker = false"
      @updated="({ cover_url, cover_tome_id }) => {
        const s = library.series.find(s => s.id === selectedSeries.id)
        if (s) s.cover_url = cover_url
        selectedSeries.cover_tome_id = cover_tome_id
      }"
    />

    <!-- Confirmation suppression série -->
    <div v-if="confirmDeleteSeries" class="confirm-backdrop" @click.self="confirmDeleteSeries = null">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer la série ?</p>
        <p class="confirm-desc">
          <strong>{{ confirmDeleteSeries.name }}</strong> et tous ses fichiers seront supprimés définitivement.
        </p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDeleteSeries = null">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="confirmDelete">Supprimer définitivement</button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.content-area {
  flex: 1;
  padding: 16px 20px;
}

.series-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .series-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .series-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .series-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .series-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .series-grid { grid-template-columns: repeat(8, 1fr); } }
@media (min-width: 1800px) { .series-grid { grid-template-columns: repeat(8, 1fr); } }

.state-box {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; min-height: 260px; padding: 40px;
}
.state-icon { font-size: 3.5rem; }
.state-title { font-size: 1.1rem; font-weight: 600; }
.state-desc  { font-size: 0.875rem; color: var(--muted); text-align: center; }

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }

.confirm-backdrop {
  position: fixed; inset: 0; z-index: 500;
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
