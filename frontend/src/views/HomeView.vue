<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SeriesCard from '../components/library/SeriesCard.vue'
import SeriesMetadataModal from '../components/metadata/SeriesMetadataModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import CoverPickerModal from '../components/library/CoverPickerModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { useLibraryStore } from '../stores/library'
import { libraryApi } from '../api/library'
import { tomesApi } from '../api/tomes'
import { useNotificationStore } from '../stores/notifications'
import { CountUp } from 'countup.js'

const router = useRouter()
const library = useLibraryStore()
const notif = useNotificationStore()
const inProgress = ref([])

// Hover states pour les overlays
const hoveredTome = ref(null)
const hoveredSeriesAdded = ref(null)
const hoveredSeriesUpdated = ref(null)
const openMenuId = ref(null)
const moreRefs = ref({})

function onClickOutside(e) {
  if (!openMenuId.value) return
  const refs = Object.values(moreRefs.value)
  if (!refs.some(el => el?.contains?.(e.target))) {
    openMenuId.value = null
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))

const seriesNumRef = ref(null)
const booksNumRef = ref(null)
let seriesCounter = null
let booksCounter = null

function initCounters() {
  const seriesVal = library.series.length
  const booksVal = library.series.reduce((s, x) => s + (x.tome_count || 0), 0)
  if (seriesNumRef.value && seriesVal > 0) {
    seriesCounter = new CountUp(seriesNumRef.value, seriesVal, { duration: 1.2, useEasing: true })
    seriesCounter.start()
  } else if (seriesNumRef.value) {
    seriesNumRef.value.textContent = '0'
  }
  if (booksNumRef.value && booksVal > 0) {
    booksCounter = new CountUp(booksNumRef.value, booksVal, { duration: 1.4, useEasing: true })
    booksCounter.start()
  } else if (booksNumRef.value) {
    booksNumRef.value.textContent = '0'
  }
}

const selectedSeries = ref(null)
const showSeriesMeta = ref(false)
const showRename = ref(false)
const showConverter = ref(false)
const showCoverPicker = ref(false)
const confirmDeleteSeries = ref(null)

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
async function handleToggleHidden(series) {
  const { data } = await libraryApi.toggleSeriesHidden(series.id)
  const s = library.series.find(s => s.id === series.id)
  if (s) s.hidden = data.hidden
  notif.success(data.hidden ? 'Série masquée' : 'Série affichée')
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

onMounted(() => {
  tomesApi.getInProgress().then(({ data }) => { inProgress.value = data })
  if (library.series.length === 0) {
    library.fetchSeries()
  } else {
    nextTick(() => initCounters())
  }
})

watch(() => library.series.length, (newVal, oldVal) => {
  if (oldVal === 0 && newVal > 0) {
    nextTick(() => initCounters())
  }
})

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

const recentAlbums = computed(() => {
  if (!library.series.length) return []
  // Trier les séries par date d'ajout puis prendre leurs tomes dans l'ordre
  const sortedSeries = [...library.series]
    .sort((a, b) => new Date(b.created_at ?? b.updated_at ?? 0) - new Date(a.created_at ?? a.updated_at ?? 0))
  return sortedSeries
    .flatMap(s => s.tomes || [])
    .slice(0, 20)
})

const recentSeriesAdded = computed(() => {
  return [...library.series]
    .sort((a, b) => new Date(b.created_at ?? b.updated_at ?? 0) - new Date(a.created_at ?? a.updated_at ?? 0))
    .slice(0, 20)
})

const recentSeriesUpdated = computed(() => {
  if (library.search.trim()) return library.filteredSeries
  return [...library.series]
    .sort((a, b) => new Date(b.updated_at ?? 0) - new Date(a.updated_at ?? 0))
    .slice(0, 20)
})
</script>

<template>
  <AppLayout>
    <main class="home-content">
      <!-- Stats cards -->
      <div class="stats-row">
        <div class="stat-card" @click="router.push('/series')">
          <div class="stat-accent"></div>
          <div ref="seriesNumRef" class="stat-num">0</div>
          <div class="stat-label">Séries</div>
        </div>
        <div class="stat-card" @click="router.push('/books')">
          <div class="stat-accent"></div>
          <div ref="booksNumRef" class="stat-num">0</div>
          <div class="stat-label">Albums</div>
        </div>
      </div>

      <!-- Résultats de recherche -->
      <div v-if="library.search.trim() && !library.filteredSeries.length" class="empty-state">
        <div class="empty-icon">🔍</div>
        <p class="empty-title">Aucun résultat</p>
        <p class="empty-desc">Aucune série ne correspond à « {{ library.search }} ».</p>
      </div>

      <!-- Empty library -->
      <div v-else-if="!library.loading && !library.series.length" class="empty-state">
        <div class="empty-icon">📚</div>
        <p class="empty-title">Bibliothèque vide</p>
        <p class="empty-desc">Configurez votre bibliothèque dans les paramètres puis lancez un scan.</p>
        <button class="btn btn-primary" @click="router.push('/settings')">
          <SvgIcon name="settings" style="font-size:15px;vertical-align:middle;margin-right:5px" />
          Configuration
        </button>
      </div>

      <template v-else>
        <!-- Poursuivre la lecture -->
        <section v-if="inProgress.length" class="section">
          <div class="section-header">
            <h2 class="section-title">Poursuivre la lecture</h2>
          </div>
          <div class="scroll-row">
            <div
              v-for="t in inProgress"
              :key="t.id"
              class="continue-card"
              @click="router.push(`/read/${t.id}`)"
              @mouseenter="hoveredTome = t.id"
              @mouseleave="hoveredTome = null"
            >
              <div class="continue-cover">
                <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="continue-cover-img" />
                <div v-else class="continue-cover-placeholder">📖</div>
                <div v-if="hoveredTome === t.id" class="continue-read-overlay">
                  <SvgIcon name="read" class="continue-read-icon" />
                </div>
                <div class="continue-progress-bar">
                  <div class="continue-progress-fill" :style="{ width: t.progress_pct + '%' }"></div>
                </div>
              </div>
              <div class="continue-info">
                <p class="continue-title">{{ t.title || t.filename }}</p>
                <p class="continue-pct">{{ t.progress_pct }}%</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Albums ajoutés récemment -->
        <section v-if="recentAlbums.length" class="section">
          <div class="section-header">
            <h2 class="section-title">Albums ajoutés récemment</h2>
          </div>
          <div class="scroll-row">
            <div
              v-for="t in recentAlbums"
              :key="t.id"
              class="scroll-card"
              @click="router.push(`/tomes/${t.id}`)"
            >
              <div class="scroll-cover">
                <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📖</div>
              </div>
              <p class="scroll-label">{{ t.title || t.filename }}</p>
            </div>
          </div>
        </section>

        <!-- Séries ajoutées récemment -->
        <section v-if="recentSeriesAdded.length" class="section">
          <div class="section-header">
            <h2 class="section-title">Séries ajoutées récemment</h2>
          </div>
          <div class="scroll-row">
            <div
              v-for="s in recentSeriesAdded"
              :key="s.id"
              class="scroll-card scroll-card-series"
              @click="router.push(`/series/${s.id}`)"
              @mouseenter="hoveredSeriesAdded = s.id"
              @mouseleave="hoveredSeriesAdded = null; openMenuId = null"
            >
              <div class="scroll-cover">
                <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📚</div>
                <div v-if="hoveredSeriesAdded === s.id || openMenuId === s.id" class="scroll-cover-dim"></div>
              </div>
              <span class="series-badge-card">{{ s.tome_count }}</span>
              <div v-if="hoveredSeriesAdded === s.id || openMenuId === s.id" class="scroll-overlay" @click.stop>
                <button class="overlay-btn" title="Modifier les métadonnées" @click="handleEdit(s)">
                  <SvgIcon name="edit" style="font-size:15px" />
                </button>
                <div class="overlay-spacer"></div>
                <div class="more-wrap" :ref="el => { if (el) moreRefs['a_' + s.id] = el }">
                  <button class="overlay-btn" :class="{ 'overlay-btn-active': openMenuId === s.id }" title="Plus d'options" @click.stop="openMenuId = openMenuId === s.id ? null : s.id">
                    <SvgIcon name="more" style="font-size:15px" />
                  </button>
                  <div v-if="openMenuId === s.id" class="more-menu">
                    <button class="more-item" @click="handleEdit(s); openMenuId = null">Éditer les métadonnées</button>
                    <button class="more-item" @click="handleRename(s); openMenuId = null">Renommer les fichiers</button>
                    <button class="more-item" @click="handleConvert(s); openMenuId = null">Convertir les fichiers</button>
                    <button class="more-item" @click="handleSetCover(s); openMenuId = null">Modifier la miniature</button>
                    <div class="more-divider"></div>
                    <button class="more-item" @click="handleToggleHidden(s); openMenuId = null">{{ s.hidden ? 'Afficher la série' : 'Masquer la série' }}</button>
                    <button class="more-item more-item-danger" @click="handleDelete(s); openMenuId = null">Supprimer la série</button>
                  </div>
                </div>
              </div>
              <div class="scroll-series-info">
                <p class="scroll-series-name">{{ s.name }}</p>
                <p class="scroll-series-count">{{ s.tome_count }} album{{ s.tome_count !== 1 ? 's' : '' }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Séries mises à jour récemment -->
        <section v-if="recentSeriesUpdated.length" class="section">
          <div class="section-header">
            <h2 class="section-title">{{ library.search ? 'Résultats' : 'Séries mises à jour récemment' }}</h2>
          </div>
          <div class="scroll-row">
            <div
              v-for="s in recentSeriesUpdated"
              :key="s.id"
              class="scroll-card scroll-card-series"
              @click="router.push(`/series/${s.id}`)"
              @mouseenter="hoveredSeriesUpdated = s.id"
              @mouseleave="hoveredSeriesUpdated = null; openMenuId = null"
            >
              <div class="scroll-cover">
                <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📚</div>
                <div v-if="hoveredSeriesUpdated === s.id || openMenuId === s.id" class="scroll-cover-dim"></div>
              </div>
              <span class="series-badge-card">{{ s.tome_count }}</span>
              <div v-if="hoveredSeriesUpdated === s.id || openMenuId === s.id" class="scroll-overlay" @click.stop>
                <button class="overlay-btn" title="Modifier les métadonnées" @click="handleEdit(s)">
                  <SvgIcon name="edit" style="font-size:15px" />
                </button>
                <div class="overlay-spacer"></div>
                <div class="more-wrap" :ref="el => { if (el) moreRefs['u_' + s.id] = el }">
                  <button class="overlay-btn" :class="{ 'overlay-btn-active': openMenuId === s.id }" title="Plus d'options" @click.stop="openMenuId = openMenuId === s.id ? null : s.id">
                    <SvgIcon name="more" style="font-size:15px" />
                  </button>
                  <div v-if="openMenuId === s.id" class="more-menu">
                    <button class="more-item" @click="handleEdit(s); openMenuId = null">Éditer les métadonnées</button>
                    <button class="more-item" @click="handleRename(s); openMenuId = null">Renommer les fichiers</button>
                    <button class="more-item" @click="handleConvert(s); openMenuId = null">Convertir les fichiers</button>
                    <button class="more-item" @click="handleSetCover(s); openMenuId = null">Modifier la miniature</button>
                    <div class="more-divider"></div>
                    <button class="more-item" @click="handleToggleHidden(s); openMenuId = null">{{ s.hidden ? 'Afficher la série' : 'Masquer la série' }}</button>
                    <button class="more-item more-item-danger" @click="handleDelete(s); openMenuId = null">Supprimer la série</button>
                  </div>
                </div>
              </div>
              <div class="scroll-series-info">
                <p class="scroll-series-name">{{ s.name }}</p>
                <p class="scroll-series-count">{{ s.tome_count }} album{{ s.tome_count !== 1 ? 's' : '' }}</p>
              </div>
            </div>
          </div>
        </section>
      </template>
    </main>

    <SeriesMetadataModal v-if="showSeriesMeta && selectedSeries" :series="selectedSeries" @close="showSeriesMeta = false" @saved="library.fetchSeries()" @deleted="(id) => { library.series = library.series.filter(s => s.id !== id); showSeriesMeta = false }" />
    <RenameModal v-if="showRename && selectedSeries" :tomes="selectedSeries.tomes" :series-name="selectedSeries.name" @close="showRename = false" @done="showRename = false" />
    <ConverterModal v-if="showConverter && selectedSeries" :tomes="selectedSeries.tomes" @close="showConverter = false" @done="showConverter = false" />
    <CoverPickerModal v-if="showCoverPicker && selectedSeries" :series="selectedSeries" @close="showCoverPicker = false" @updated="({ cover_url }) => { const s = library.series.find(s => s.id === selectedSeries.id); if (s) s.cover_url = cover_url }" />

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
.home-content {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Stats */
.stats-row {
  display: flex;
  gap: 14px;
}
.stat-card {
  flex: 0 0 auto;
  min-width: 120px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
  box-shadow: var(--shadow-sm);
}
.stat-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-3px);
  border-color: var(--primary);
}
.stat-accent {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--primary);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.25s ease;
  border-radius: var(--radius) var(--radius) 0 0;
}
.stat-card:hover .stat-accent {
  transform: scaleX(1);
}
.stat-num {
  font-size: 2.2rem;
  font-weight: 700;
  color: var(--primary);
  line-height: 1;
  margin-bottom: 4px;
  transition: color 0.2s;
}
.stat-card:hover .stat-num {
  color: var(--primary-dark, var(--primary));
}
.stat-label { font-size: 0.875rem; color: var(--muted); font-weight: 500; transition: color 0.2s; }
.stat-card:hover .stat-label { color: var(--text); }

/* Section */
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.section-title { font-size: 1rem; font-weight: 600; }

/* Same grid as SeriesView */
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

/* Continuer la lecture */
.continue-card {
  cursor: pointer;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.18s, transform 0.18s;
}
.continue-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
.continue-cover {
  aspect-ratio: 2/3; background: var(--light);
  overflow: hidden; position: relative;
}
.continue-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s; }
.continue-card:hover .continue-cover-img { transform: scale(1.04); }
.continue-cover-placeholder {
  width: 100%; height: 100%; display: flex;
  align-items: center; justify-content: center; font-size: 2.5rem; color: var(--placeholder);
}
.continue-progress-bar {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 4px; background: rgba(0,0,0,0.2);
}
.continue-progress-fill {
  height: 100%; background: var(--primary);
  transition: width 0.3s ease;
}
.continue-info { padding: 8px 10px; border-top: 1px solid var(--border); }
.continue-title {
  font-size: 0.8125rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.continue-pct { font-size: 0.75rem; color: var(--muted); }

/* Empty */
.empty-state {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; min-height: 300px; text-align: center;
}
.empty-icon { font-size: 4rem; }
.empty-title { font-size: 1.2rem; font-weight: 600; }
.empty-desc { font-size: 0.875rem; color: var(--muted); max-width: 360px; }

/* Scroll row (horizontal scroll sections) */
.scroll-row {
  display: flex;
  flex-direction: row;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.scroll-row::-webkit-scrollbar { height: 5px; }
.scroll-row::-webkit-scrollbar-track { background: transparent; }
.scroll-row::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

.scroll-card {
  flex: 0 0 auto;
  width: 160px;
  cursor: pointer;
  transition: transform 0.18s;
  position: relative;
}
.scroll-card:hover { transform: translateY(-2px); }

.scroll-cover {
  width: 100%;
  aspect-ratio: 2/3;
  background: var(--light);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 6px;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.18s;
  position: relative;
}
.scroll-card:hover .scroll-cover { box-shadow: var(--shadow-lg); }
.scroll-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s; }
.scroll-card:hover .scroll-cover-img { transform: scale(1.04); }
.scroll-cover-placeholder {
  width: 100%; height: 100%; display: flex;
  align-items: center; justify-content: center;
  font-size: 2rem; color: var(--placeholder);
}

/* Overlay séries dans scroll-row — positionnés par rapport à .scroll-card */
.scroll-cover-dim {
  position: absolute; inset: 0; z-index: 2;
  background: rgba(0,0,0,0.32);
  pointer-events: none;
}
/* Badge nombre d'albums — positionné par rapport au .scroll-card */
.series-badge-card {
  position: absolute; top: 6px; right: 6px; z-index: 5;
  min-width: 22px; height: 22px; padding: 0 4px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.68rem; font-weight: 700;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
}
/* Card série avec bandeau — fond + border-radius + ombre comme SeriesCard */
.scroll-card-series {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  overflow: visible;
}
.scroll-card-series .scroll-cover {
  margin-bottom: 0;
  border-radius: var(--radius) var(--radius) 0 0;
}
.scroll-series-info {
  padding: 7px 10px 6px;
  border-top: 1px solid var(--border);
}
.scroll-series-name {
  font-size: 0.8125rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.scroll-series-count { font-size: 0.75rem; color: var(--muted); }

/* L'overlay boutons : positionné depuis le bas du .scroll-card-series,
   au-dessus du bandeau info (scroll-series-info ~42px) */
.scroll-overlay {
  position: absolute; left: 0; right: 0;
  bottom: 46px; /* hauteur du bandeau info (padding + 2 lignes texte) */
  height: 36px; z-index: 10;
  display: flex; align-items: center;
  padding: 0 6px;
}
.overlay-spacer { flex: 1; }
.overlay-btn {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--overlay-btn-bg); border: none; cursor: pointer;
  color: var(--text);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, transform 0.12s;
  flex-shrink: 0;
}
.overlay-btn:hover { background: var(--surface); transform: scale(1.1); }
.overlay-btn-active { background: var(--surface); }
.more-wrap { position: relative; }
.more-menu {
  position: absolute; bottom: calc(100% + 4px); right: 0;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  min-width: 190px;
  padding: 4px 0;
  z-index: 300;
}
.more-item {
  display: block; width: 100%; padding: 8px 14px;
  background: none; border: none; cursor: pointer;
  font-size: 0.8125rem; font-family: var(--font); color: var(--text);
  text-align: left; transition: background 0.1s; white-space: nowrap;
}
.more-item:hover { background: var(--light); }
.more-divider { height: 1px; background: var(--border); margin: 4px 0; }
.more-item-danger { color: var(--danger); }
.more-item-danger:hover { background: var(--danger-bg-light); }

/* Icône lecture sur continue-card */
.continue-read-overlay {
  position: absolute; inset: 0; z-index: 3;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.35);
  pointer-events: none;
}
.continue-read-icon { font-size: 40px; color: #fff; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }
.scroll-label {
  font-size: 0.75rem; font-weight: 500; color: var(--text);
  line-height: 1.3;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  text-align: center;
  position: relative; z-index: 1;
}

/* Continue cards inside scroll-row */
.continue-card {
  flex: 0 0 auto;
  width: 160px;
}

/* Confirm delete */
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
