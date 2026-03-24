<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import StarRating from '../components/ui/StarRating.vue'
import { tomesApi } from '../api/tomes'
import { libraryApi } from '../api/library'

const route = useRoute()
const router = useRouter()

const tome = ref(null)
const metadata = ref(null)
const seriesName = ref('')
const seriesTomes = ref([])
const loading = ref(true)
const showEdit = ref(false)
const showConverter = ref(false)
const showRename = ref(false)

function parseTomeNumber(n) {
  if (!n) return { hs: true, val: Infinity }
  const s = String(n).trim()
  const isHS = /^hs/i.test(s)
  const num = parseFloat(s.replace(/[^0-9.]/gi, ''))
  return { hs: isHS, val: isNaN(num) ? Infinity : num }
}

const sortedSeriesTomes = computed(() =>
  [...seriesTomes.value].sort((a, b) => {
    const pa = parseTomeNumber(a.number)
    const pb = parseTomeNumber(b.number)
    if (pa.hs !== pb.hs) return pa.hs ? 1 : -1
    return pa.val - pb.val
  })
)

const currentIndex = computed(() => sortedSeriesTomes.value.findIndex(t => t.id === tome.value?.id))
const prevTome = computed(() => currentIndex.value > 0 ? sortedSeriesTomes.value[currentIndex.value - 1] : null)
const nextTome = computed(() => currentIndex.value < sortedSeriesTomes.value.length - 1 ? sortedSeriesTomes.value[currentIndex.value + 1] : null)

async function loadTome(id) {
  loading.value = true
  try {
    const [tomeRes, metaRes] = await Promise.all([
      tomesApi.getTome(id),
      tomesApi.getMetadata(id),
    ])
    tome.value = tomeRes.data
    metadata.value = metaRes.data

    if (tome.value.series_id) {
      try {
        const { data } = await libraryApi.getSeriesDetail(tome.value.series_id)
        seriesName.value = data.name
        seriesTomes.value = data.tomes || []
      } catch { /* ignore */ }
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => loadTome(route.params.id))
watch(() => route.params.id, (id) => { if (id) loadTome(id) })

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })
}

function onMetadataSaved() {
  Promise.all([
    tomesApi.getTome(route.params.id),
    tomesApi.getMetadata(route.params.id),
  ]).then(([tomeRes, metaRes]) => {
    tome.value = tomeRes.data
    metadata.value = metaRes.data
  })
}

function filterByField(field, value) {
  router.push({ path: '/books', query: { [field]: value } })
}
</script>

<template>
  <AppLayout>
    <div v-if="loading" class="loading-state">
      <span class="loading-pulse">Chargement…</span>
    </div>

    <main v-else-if="tome" class="detail-main">
      <!-- Breadcrumb -->
      <nav class="breadcrumb">
        <button @click="router.push('/series')" class="breadcrumb-link">Séries</button>
        <span class="breadcrumb-sep">/</span>
        <button
          v-if="tome.series_id"
          @click="router.push(`/series/${tome.series_id}`)"
          class="breadcrumb-link"
        >{{ seriesName || '…' }}</button>
        <span class="breadcrumb-sep">/</span>
        <span class="breadcrumb-current">{{ tome.title || tome.filename }}</span>
        <div class="breadcrumb-nav">
          <button class="breadcrumb-chevron" :disabled="!prevTome" @click="router.push(`/tomes/${prevTome.id}`)" :title="prevTome?.title || prevTome?.filename">‹</button>
          <button class="breadcrumb-chevron" :disabled="!nextTome" @click="router.push(`/tomes/${nextTome.id}`)" :title="nextTome?.title || nextTome?.filename">›</button>
        </div>
      </nav>

      <!-- Main card -->
      <div class="tome-card card">
        <div class="card-body tome-card-inner">
          <!-- Cover -->
          <div class="tome-cover-wrap" @click="router.push(`/read/${tome.id}`)" title="Lire">
            <img
              v-if="tome.cover_url"
              :src="tome.cover_url"
              :alt="tome.title"
              class="tome-cover-img"
            />
            <div v-else class="tome-cover-placeholder">📖</div>
            <div class="tome-cover-read-overlay">
              <SvgIcon name="read" class="cover-read-icon" />
            </div>
          </div>

          <!-- Info -->
          <div class="tome-info">
            <p v-if="seriesName" class="tome-series-name">{{ seriesName }}</p>
            <h1 class="tome-title">{{ tome.title || tome.filename }}</h1>

            <!-- Chips -->
            <div class="tome-chips">
              <span v-if="tome.number" class="chip chip-muted">Album {{ tome.number }}</span>
              <span v-if="tome.page_count" class="chip chip-muted">{{ tome.page_count }} pages</span>
              <span v-if="metadata?.Year" class="chip chip-muted">{{ metadata.Year }}</span>
              <span :class="['chip', `chip-${tome.file_format}`]">{{ tome.file_format.toUpperCase() }}</span>
            </div>

            <!-- Actions -->
            <div class="tome-actions">
              <button class="btn btn-secondary btn-sm" @click="router.push(`/read/${tome.id}`)">
                <SvgIcon name="read" class="btn-icon-svg" /> Lire
              </button>
              <button
                v-if="tome.file_format === 'cbz'"
                class="btn btn-secondary btn-sm"
                @click="showEdit = true"
              ><SvgIcon name="edit" class="btn-icon-svg" /> Éditer</button>
              <button
                v-else-if="tome.file_format !== 'cbz'"
                class="btn btn-secondary btn-sm"
                @click="showConverter = true"
              ><SvgIcon name="convert" class="btn-icon-svg" /> Convertir</button>
              <button class="btn btn-secondary btn-sm" @click="showRename = true">
                <SvgIcon name="rename" class="btn-icon-svg" /> Renommer
              </button>
            </div>

            <!-- Metadata rows -->
            <div class="meta-section">
              <div class="meta-row" v-if="metadata?.Writer">
                <span class="meta-label">Scénariste</span>
                <button class="meta-link" @click="filterByField('writer', metadata.Writer)">{{ metadata.Writer }}</button>
              </div>
              <div class="meta-row" v-if="metadata?.Penciller">
                <span class="meta-label">Dessinateur</span>
                <button class="meta-link" @click="filterByField('penciller', metadata.Penciller)">{{ metadata.Penciller }}</button>
              </div>
              <div class="meta-row" v-if="metadata?.Publisher">
                <span class="meta-label">Éditeur</span>
                <button class="meta-link" @click="filterByField('publisher', metadata.Publisher)">{{ metadata.Publisher }}</button>
              </div>
              <div class="meta-row" v-if="metadata?.Year">
                <span class="meta-label">Année</span>
                <span class="meta-value">{{ metadata.Year }}</span>
              </div>
            </div>

            <!-- File info -->
            <div class="meta-section">
              <div class="meta-row">
                <span class="meta-label">Format</span>
                <span class="meta-value">{{ tome.file_format.toUpperCase() }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Taille</span>
                <span class="meta-value">{{ formatSize(tome.file_size) }}</span>
              </div>
              <div class="meta-row" v-if="tome.filepath">
                <span class="meta-label">Chemin</span>
                <span class="meta-value meta-filepath">{{ tome.filepath }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Ajouté</span>
                <span class="meta-value">{{ formatDate(tome.created_at) }}</span>
              </div>
              <div class="meta-row" v-if="tome.updated_at">
                <span class="meta-label">Modifié</span>
                <span class="meta-value">{{ formatDate(tome.updated_at) }}</span>
              </div>
            </div>

            <!-- Annotations utilisateur -->
            <div class="meta-section">
              <p class="meta-section-title">Annotations personnelles</p>
              <div class="meta-row">
                <span class="meta-label">Note</span>
                <StarRating :model-value="tome.user_rating || 0" readonly />
              </div>
              <div class="meta-row">
                <span class="meta-label">Étiquettes</span>
                <div v-if="tome.user_tags?.length" class="tag-list">
                  <span v-for="tag in tome.user_tags" :key="tag" class="tag-chip-sm"
                    @click="router.push({ path: '/books', query: { tag } })"
                  >{{ tag }}</span>
                </div>
                <span v-else class="meta-value meta-empty">—</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Commentaire</span>
                <span class="meta-value">{{ tome.user_notes || '—' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Edit modal -->
    <MetadataDrawer
      v-if="showEdit && tome"
      :tome="tome"
      @close="showEdit = false"
      @saved="onMetadataSaved"
      @deleted="({ series_deleted }) => router.push(series_deleted ? '/series' : `/series/${tome.series_id}`)"
    />

    <!-- Converter modal -->
    <ConverterModal
      v-if="showConverter && tome"
      :tomes="[tome]"
      @close="showConverter = false"
      @done="showConverter = false"
    />

    <!-- Rename modal -->
    <RenameModal
      v-if="showRename && tome"
      :tomes="[tome]"
      :series-name="seriesName"
      @close="showRename = false"
      @done="onMetadataSaved()"
    />
  </AppLayout>
</template>

<style scoped>
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.loading-state {
  display: flex; align-items: center; justify-content: center;
  min-height: 240px; color: var(--muted); font-size: 0.9rem;
}
.loading-pulse { animation: pulse 1.4s ease-in-out infinite; }

.detail-main {
  flex: 1;
  padding: 20px;
  max-width: 900px;
}

/* Breadcrumb */
.breadcrumb {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.875rem; color: var(--muted); margin-bottom: 16px;
  flex-wrap: wrap;
}
.breadcrumb-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--primary); font-size: 0.875rem; font-family: var(--font);
}
.breadcrumb-link:hover { text-decoration: underline; }
.breadcrumb-sep { color: var(--placeholder); }
.breadcrumb-current {
  color: var(--text); font-weight: 500;
  max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.breadcrumb-nav { margin-left: auto; display: flex; gap: 4px; }
.breadcrumb-chevron {
  background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
  width: 28px; height: 28px; cursor: pointer; font-size: 1.1rem; line-height: 1;
  color: var(--text); display: flex; align-items: center; justify-content: center;
  transition: background 0.12s;
}
.breadcrumb-chevron:hover:not(:disabled) { background: var(--light); }
.breadcrumb-chevron:disabled { opacity: 0.3; cursor: default; }

/* Main card */
.tome-card { margin-bottom: 20px; }
.tome-card-inner {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

/* Cover */
.tome-cover-wrap {
  width: 160px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: box-shadow 0.18s, transform 0.18s;
  position: relative;
}
.tome-cover-wrap:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
.tome-cover-read-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.18s;
}
.tome-cover-wrap:hover .tome-cover-read-overlay { opacity: 1; }
.cover-read-icon {
  font-size: 40px;
  color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}
.tome-cover-img { width: 100%; aspect-ratio: 2/3; object-fit: cover; display: block; }
.tome-cover-placeholder {
  width: 100%; aspect-ratio: 2/3;
  display: flex; align-items: center; justify-content: center;
  font-size: 3rem; background: var(--light);
}

/* Info */
.tome-info { flex: 1; min-width: 0; }
.tome-series-name {
  font-size: 0.8125rem; color: var(--muted); margin-bottom: 4px;
}
.series-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--primary); font-size: 0.8125rem; font-family: var(--font);
}
.series-link:hover { text-decoration: underline; }
.tome-title {
  font-size: 1.4rem; font-weight: 700; color: var(--text);
  margin-bottom: 10px; line-height: 1.3;
}

/* Chips */
.tome-chips {
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px;
}
.chip {
  font-size: 0.72rem; font-weight: 700;
  padding: 2px 8px; border-radius: 4px;
}
.chip-muted   { background: var(--light); color: var(--muted); border: 1px solid var(--border); }
.chip-cbz     { background: var(--success-bg); color: var(--success-text); }
.chip-cbr     { background: var(--warning-bg); color: var(--orange-bar); }
.chip-pdf     { background: var(--info-bg); color: var(--info-text); }

/* Actions */
.tome-actions {
  display: flex; align-items: center; gap: 10px; margin-bottom: 20px;
}
.btn-icon-svg { font-size: 13px; vertical-align: middle; margin-right: 3px; }

/* Metadata rows */
.meta-section {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 12px;
}
.meta-section-title {
  font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
  color: var(--muted); letter-spacing: 0.05em; margin-bottom: 8px;
}
.meta-row {
  display: flex; gap: 12px;
  font-size: 0.8125rem; padding: 4px 0;
  border-bottom: 1px solid var(--light);
}
.meta-label {
  width: 110px; flex-shrink: 0;
  color: var(--muted); font-weight: 500;
}
.meta-value { color: var(--text); flex: 1; min-width: 0; }
.meta-empty { color: var(--muted); }
.meta-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--primary); font-size: 0.8125rem; font-family: var(--font);
  text-align: left; flex: 1;
}
.meta-link:hover { text-decoration: underline; }
.tag-list { display: flex; flex-wrap: wrap; gap: 5px; flex: 1; }
.tag-chip-sm {
  display: inline-flex; align-items: center;
  background: var(--primary-light); color: var(--primary);
  border-radius: 12px; padding: 2px 8px;
  font-size: 0.75rem; font-weight: 600; cursor: pointer;
}
.tag-chip-sm:hover { background: var(--tag-hover-bg); }
.meta-filepath {
  font-size: 0.75rem; font-family: monospace;
  word-break: break-all; color: var(--muted);
}

@media (max-width: 540px) {
  .tome-card-inner { flex-direction: column; }
  .tome-cover-wrap { width: 120px; }
  .tome-title { font-size: 1.1rem; }
}
</style>
