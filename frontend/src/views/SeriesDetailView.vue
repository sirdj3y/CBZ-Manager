<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import SeriesMetadataModal from '../components/metadata/SeriesMetadataModal.vue'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import CoverPickerModal from '../components/library/CoverPickerModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { libraryApi } from '../api/library'
import { tomesApi } from '../api/tomes'
import { useNotificationStore } from '../stores/notifications'
import { useLibraryStore } from '../stores/library'

const notif = useNotificationStore()
const libraryStore = useLibraryStore()

const route = useRoute()
const router = useRouter()
const series = ref(null)
const seriesMeta = ref(null)
const loading = ref(true)

const seriesList = computed(() => libraryStore.series || [])
const currentIndex = computed(() => seriesList.value.findIndex(s => s.id === series.value?.id))
const prevSeries = computed(() => currentIndex.value > 0 ? seriesList.value[currentIndex.value - 1] : null)
const nextSeries = computed(() => currentIndex.value < seriesList.value.length - 1 ? seriesList.value[currentIndex.value + 1] : null)

function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  if (/^\d+$/.test(s)) return s.padStart(2, '0')
  return s
}

function parseTomeNumber(n) {
  if (!n) return { hs: true, val: Infinity, raw: '' }
  const s = String(n).trim()
  const isHS = /^hs/i.test(s)
  const num = parseFloat(s.replace(/[^0-9.]/gi, ''))
  return { hs: isHS, val: isNaN(num) ? Infinity : num, raw: s }
}

const sortedTomes = computed(() => {
  if (!series.value?.tomes) return []
  return [...series.value.tomes].sort((a, b) => {
    const pa = parseTomeNumber(a.number)
    const pb = parseTomeNumber(b.number)
    if (pa.hs !== pb.hs) return pa.hs ? 1 : -1
    if (pa.val !== pb.val) return pa.val - pb.val
    return pa.raw.localeCompare(pb.raw, 'fr', { numeric: true })
  })
})

const showConverter = ref(false)
const showSeriesMeta = ref(false)
const showTomeMeta = ref(false)
const showRename = ref(false)
const convertTomeId = ref(null)
const selectedTome = ref(null)

async function loadSeries(id) {
  loading.value = true
  try {
    const { data } = await libraryApi.getSeriesDetail(id)
    series.value = data
    if (data.tomes?.length) {
      try {
        const { data: meta } = await tomesApi.getMetadata(data.tomes[0].id)
        seriesMeta.value = meta
      } catch { /* ignore */ }
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (!libraryStore.series.length) await libraryStore.fetchSeries()
  await loadSeries(route.params.id)
})

watch(() => route.params.id, (id) => { if (id) loadSeries(id) })

function onEditTome(tome) {
  selectedTome.value = tome
  showTomeMeta.value = true
}

function onConvert(tome) {
  convertTomeId.value = tome.id
  showConverter.value = true
}

async function onRenameDone() {
  const { data } = await libraryApi.getSeriesDetail(route.params.id)
  series.value = data
}

async function toggleSeriesHidden() {
  const { data } = await libraryApi.toggleSeriesHidden(series.value.id)
  series.value.hidden = data.hidden
  notif.success(data.hidden ? 'Série masquée' : 'Série affichée')
  libraryStore.fetchSeries()
}

const showCoverPicker = ref(false)

function onCoverUpdated({ cover_url, cover_tome_id }) {
  series.value.cover_url = cover_url
  series.value.cover_tome_id = cover_tome_id
  // Mettre à jour le store pour que la page Séries reflète le changement
  const s = libraryStore.series.find(s => s.id === series.value.id)
  if (s) s.cover_url = cover_url
}
</script>

<template>
  <AppLayout>
    <div v-if="loading" class="loading-state">
      <span class="loading-pulse">Chargement…</span>
    </div>

    <main v-else-if="series" class="detail-main">
      <!-- Breadcrumb -->
      <nav class="breadcrumb">
        <button @click="router.push('/series')" class="breadcrumb-link">Séries</button>
        <span class="breadcrumb-sep">/</span>
        <span class="breadcrumb-current">{{ series.name }}</span>
        <div class="breadcrumb-nav">
          <button class="breadcrumb-chevron" :disabled="!prevSeries" @click="router.push(`/series/${prevSeries.id}`)" :title="prevSeries?.name">‹</button>
          <button class="breadcrumb-chevron" :disabled="!nextSeries" @click="router.push(`/series/${nextSeries.id}`)" :title="nextSeries?.name">›</button>
        </div>
      </nav>

      <!-- Series header -->
      <div class="series-header card">
        <div class="card-body series-header-inner">
          <div class="series-cover-wrap" @click="showCoverPicker = true" title="Cliquer pour changer la cover">
            <img v-if="series.cover_url" :src="series.cover_url" :alt="series.name" class="series-cover-img" />
            <div v-else class="series-cover-placeholder">📚</div>
            <div class="series-cover-overlay">
              <SvgIcon name="edit" style="font-size:18px; color:#fff" />
            </div>
          </div>
          <div class="series-meta">
            <h1 class="series-title">{{ series.name }}</h1>
            <p class="series-count">{{ series.tome_count }} tome{{ series.tome_count !== 1 ? 's' : '' }}</p>

            <!-- Series metadata chips -->
            <div v-if="seriesMeta" class="series-meta-rows">
              <div v-if="seriesMeta.Writer" class="series-meta-row">
                <span class="series-meta-label">Scénariste</span>
                <button class="series-meta-link" @click="router.push(`/series?writer=${encodeURIComponent(seriesMeta.Writer)}`)">{{ seriesMeta.Writer }}</button>
              </div>
              <div v-if="seriesMeta.Penciller" class="series-meta-row">
                <span class="series-meta-label">Dessinateur</span>
                <button class="series-meta-link" @click="router.push(`/series?penciller=${encodeURIComponent(seriesMeta.Penciller)}`)">{{ seriesMeta.Penciller }}</button>
              </div>
              <div v-if="seriesMeta.Publisher" class="series-meta-row">
                <span class="series-meta-label">Éditeur</span>
                <button class="series-meta-link" @click="router.push(`/series?publisher=${encodeURIComponent(seriesMeta.Publisher)}`)">{{ seriesMeta.Publisher }}</button>
              </div>
            </div>

            <div class="series-action-btns">
              <button class="btn btn-secondary btn-sm" @click="showSeriesMeta = true">
                <SvgIcon name="edit" class="btn-icon-svg" /> Éditer
              </button>
              <button class="btn btn-secondary btn-sm" @click="showRename = true">
                <SvgIcon name="rename" class="btn-icon-svg" /> Renommer
              </button>
              <button class="btn btn-secondary btn-sm" @click="showConverter = true">
                <SvgIcon name="convert" class="btn-icon-svg" /> Convertir
              </button>
              <button class="btn btn-secondary btn-sm" @click="toggleSeriesHidden" :class="{ 'btn-hidden-active': series.hidden }">
                <SvgIcon :name="series.hidden ? 'eye' : 'hide'" :key="series.hidden ? 'eye' : 'hide'" class="btn-icon-svg" /> {{ series.hidden ? 'Afficher' : 'Masquer' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Tomes grid -->
      <div class="tomes-grid">
        <div
          v-for="tome in sortedTomes"
          :key="tome.id"
          class="tome-card"
          :title="tome.title || tome.filename"
        >
          <!-- Cover — click → tome detail page -->
          <div class="tome-cover" @click="router.push(`/tomes/${tome.id}`)" :class="{ 'tome-cover-hidden': tome.hidden }">
            <img
              v-if="tome.cover_url"
              :src="tome.cover_url"
              :alt="tome.title"
              class="tome-cover-img"
              loading="lazy"
              @error="$event.target.style.display='none'"
            />
            <div v-else class="tome-cover-placeholder">📖</div>

            <!-- Number badge -->
            <span v-if="tome.number" class="tome-badge">T{{ fmtNumber(tome.number) }}</span>

            <!-- Hover overlay -->
            <div class="tome-overlay" @click.stop="router.push(`/read/${tome.id}`)">
              <SvgIcon name="read" class="tome-read-icon" />
              <button class="overlay-btn tome-edit-btn" title="Modifier" @click.stop="onEditTome(tome)">
                <SvgIcon name="edit" style="font-size:15px" />
              </button>
            </div>
          </div>

          <!-- Info — click → tome detail page -->
          <div class="tome-info" @click="router.push(`/tomes/${tome.id}`)">
            <p class="tome-title">{{ tome.title || tome.filename }}</p>
            <p class="tome-meta">
              <span :class="['fmt-badge', `fmt-${tome.file_format}`]">{{ tome.file_format.toUpperCase() }}</span>
              <span v-if="tome.page_count" class="tome-pages">{{ tome.page_count }} pages</span>
            </p>
          </div>
        </div>
      </div>
    </main>

    <!-- Series metadata modal -->
    <SeriesMetadataModal
      v-if="showSeriesMeta"
      :series="series"
      @close="showSeriesMeta = false"
      @saved="null"
      @deleted="libraryStore.fetchSeries().then(() => router.push('/series'))"
    />

    <!-- Tome metadata modal -->
    <MetadataDrawer
      v-if="showTomeMeta && selectedTome"
      :tome="selectedTome"
      @close="showTomeMeta = false"
      @deleted="({ series_deleted }) => { if (series_deleted) libraryStore.fetchSeries().then(() => router.push('/series')); else libraryApi.getSeriesDetail(route.params.id).then(({ data }) => { series.value = data }) }"
    />

    <!-- Converter modal -->
    <ConverterModal
      v-if="showConverter"
      :tomes="convertTomeId ? series.tomes.filter(t => t.id === convertTomeId) : series.tomes"
      @close="showConverter = false; convertTomeId = null"
      @done="showConverter = false; convertTomeId = null"
    />

    <!-- Rename modal -->
    <RenameModal
      v-if="showRename && series"
      :tomes="series.tomes"
      :series-name="series.name"
      @close="showRename = false"
      @done="onRenameDone"
    />

    <CoverPickerModal
      v-if="showCoverPicker && series"
      :series="series"
      @close="showCoverPicker = false"
      @updated="onCoverUpdated"
    />
  </AppLayout>
</template>

<style scoped>
.loading-state {
  display: flex; align-items: center; justify-content: center;
  min-height: 240px; color: var(--muted); font-size: 0.9rem;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.loading-pulse { animation: pulse 1.4s ease-in-out infinite; }

.detail-main {
  flex: 1;
  padding: 20px;
}

/* Breadcrumb */
.breadcrumb {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.875rem; color: var(--muted); margin-bottom: 16px;
}
.breadcrumb-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--primary); font-size: 0.875rem; font-family: var(--font);
}
.breadcrumb-link:hover { text-decoration: underline; }
.breadcrumb-sep { color: var(--placeholder); }
.breadcrumb-current { color: var(--text); font-weight: 500; }
.breadcrumb-nav { margin-left: auto; display: flex; gap: 4px; }
.breadcrumb-chevron {
  background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
  width: 28px; height: 28px; cursor: pointer; font-size: 1.1rem; line-height: 1;
  color: var(--text); display: flex; align-items: center; justify-content: center;
  transition: background 0.12s;
}
.breadcrumb-chevron:hover:not(:disabled) { background: var(--light); }
.breadcrumb-chevron:disabled { opacity: 0.3; cursor: default; }

/* Series header */
.series-header { margin-bottom: 20px; }
.series-header-inner { display: flex; gap: 20px; align-items: flex-start; }
.series-cover-wrap {
  width: 100px; flex-shrink: 0;
  border-radius: var(--radius-sm); overflow: hidden;
  border: 1px solid var(--border);
  position: relative; cursor: pointer;
}
.series-cover-overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.35);
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: center; justify-content: center;
}
.series-cover-wrap:hover .series-cover-overlay { opacity: 1; }
.series-cover-img { width: 100%; aspect-ratio: 2/3; object-fit: cover; display: block; }
.series-cover-placeholder {
  width: 100%; aspect-ratio: 2/3;
  display: flex; align-items: center; justify-content: center;
  font-size: 2.5rem; background: var(--light);
}
.series-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 4px; }
.series-count { font-size: 0.875rem; color: var(--muted); margin-bottom: 10px; }

.series-meta-rows { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.series-meta-row { display: flex; gap: 8px; font-size: 0.8125rem; }
.series-meta-label { color: var(--muted); width: 90px; flex-shrink: 0; }
.series-meta-value { color: var(--text); }
.series-meta-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--primary); font-size: 0.8125rem; font-family: var(--font);
  text-align: left;
}
.series-meta-link:hover { text-decoration: underline; }

.series-action-btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.btn-icon-svg { font-size: 13px; vertical-align: middle; margin-right: 3px; }

/* Tomes grid */
.tomes-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .tomes-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .tomes-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .tomes-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .tomes-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .tomes-grid { grid-template-columns: repeat(8, 1fr); } }

/* Tome card */
.tome-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
}
.tome-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }

.tome-cover {
  aspect-ratio: 2/3;
  background: var(--light);
  position: relative; overflow: hidden; cursor: pointer;
}
.tome-cover-img {
  width: 100%; height: 100%; object-fit: cover; display: block;
  transition: transform 0.3s;
}
.tome-card:hover .tome-cover-img { transform: scale(1.04); }
.tome-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 2rem; color: var(--placeholder);
}

.tome-badge {
  position: absolute; top: 6px; right: 6px; z-index: 2;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: var(--text);
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}

.tome-overlay {
  position: absolute; inset: 0; z-index: 3;
  background: rgba(0,0,0,0.32);
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.tome-card:hover .tome-overlay { opacity: 1; }
.tome-read-icon {
  font-size: 48px; color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}
.tome-edit-btn {
  position: absolute; bottom: 8px; left: 8px;
}

.overlay-btn {
  width: 30px; height: 30px; border-radius: 50%;
  background: var(--overlay-btn-bg); border: none; cursor: pointer;
  font-size: 0.9rem; color: var(--text);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, transform 0.12s;
  flex-shrink: 0;
}
.overlay-btn:hover { background: var(--surface); transform: scale(1.1); }
.overlay-btn-active { background: rgba(100,120,180,0.9) !important; color: #fff !important; }

.btn-hidden-active { border-color: #5c7099; color: #5c7099; background: #eef0f8; }

.tome-info {
  padding: 7px 9px; border-top: 1px solid var(--border); cursor: pointer;
}
.tome-title {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 4px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.tome-meta { display: flex; align-items: center; gap: 6px; }
.fmt-badge {
  font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px;
}
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }
.tome-pages { font-size: 0.72rem; color: var(--muted); }
</style>
