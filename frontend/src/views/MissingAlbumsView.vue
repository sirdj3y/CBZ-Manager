<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import MissingAlbumUploadModal from '../components/missingAlbums/MissingAlbumUploadModal.vue'
import { missingAlbumsApi } from '../api/missingAlbums'
import { normalizeSearch, sortTitle } from '../utils/text'
import { useMissingAlbumsStore } from '../stores/missingAlbums'
import Hint from '../components/ui/Hint.vue'

const missingAlbumsStore = useMissingAlbumsStore()

const loading = ref(true)
const missing = ref([])
const notFound = ref([])
const trackedSeries = ref([])
const ignoredAlbums = ref([])
const activeTab = ref('missing') // 'missing' | 'manage'
const search = ref('')

// Dernier scan persisté (affiché quand aucun scan n'est en cours dans cette session) — la
// progression d'un scan EN COURS vient elle de missingAlbumsStore.scanProgress, partagée avec
// le menu "Scanner" global d'AppLayout, pour rester à jour même si ce scan a été déclenché
// depuis une autre page.
const lastScan = ref({ status: 'never', processed: 0, total: 0, error_msg: null })
const loadError = ref(false)
const startError = ref(null)

// Bedetheque n'a souvent pas de titre distinct par tome (mangas notamment) : le champ
// vaut littéralement "Tome N", ce qui fait doublon avec le numéro déjà affiché à côté.
function displayTitle(album) {
  const t = (album.title || '').trim()
  if (!t) return ''
  if (normalizeSearch(t) === normalizeSearch(`Tome ${album.number}`)) return ''
  return t
}

const filteredMissing = computed(() => {
  const q = normalizeSearch(search.value.trim())
  if (!q) return missing.value
  return missing.value.filter(a => normalizeSearch(a.series_name).includes(q))
})

const SORT_OPTIONS = [
  { key: 'name-asc', label: 'Nom de série (A → Z)' },
  { key: 'name-desc', label: 'Nom de série (Z → A)' },
  { key: 'count-desc', label: "Nombre d'albums manquants" },
]
const sortBy = ref('name-asc')

const groupedMissing = computed(() => {
  const groups = new Map()
  for (const album of filteredMissing.value) {
    if (!groups.has(album.series_id)) groups.set(album.series_id, { series_id: album.series_id, series_name: album.series_name, albums: [] })
    groups.get(album.series_id).albums.push(album)
  }
  const list = [...groups.values()]
  const byName = (a, b) => sortTitle(a.series_name).localeCompare(sortTitle(b.series_name), undefined, { sensitivity: 'base' })
  if (sortBy.value === 'name-desc') list.sort((a, b) => byName(b, a))
  else if (sortBy.value === 'count-desc') list.sort((a, b) => b.albums.length - a.albums.length || byName(a, b))
  else list.sort(byName)
  return list
})

const missingCount = computed(() => missing.value.length)

// ── Gérer le suivi : gestionnaire d'exceptions plutôt qu'un tableau des 79 séries ──
const excludeSearch = ref('')
const excludedSeries = computed(() =>
  trackedSeries.value.filter(s => !s.track_new_albums).sort((a, b) => sortTitle(a.name).localeCompare(sortTitle(b.name), undefined, { sensitivity: 'base' }))
)
const excludeSuggestions = computed(() => {
  const q = normalizeSearch(excludeSearch.value.trim())
  if (!q) return []
  return trackedSeries.value.filter(s => s.track_new_albums && normalizeSearch(s.name).includes(q)).slice(0, 8)
})
function excludeSeries(series) {
  toggleTrack(series)
  excludeSearch.value = ''
}

function formatDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const lastScanLabel = computed(() => {
  const sp = missingAlbumsStore.scanProgress
  if (sp.status === 'running' || sp.status === 'pending') {
    return `Analyse en cours… ${sp.processed}/${sp.total} série(s)`
  }
  if (lastScan.value.status === 'never') return "Aucun scan effectué pour l'instant"
  if (lastScan.value.status === 'error') return `Dernier scan en erreur : ${lastScan.value.error_msg || ''}`
  return `Dernier scan : ${formatDate(lastScan.value.finished_at) || 'terminé'}`
})

async function loadResults() {
  const [{ data: listData }, { data: seriesData }, { data: ignoredData }] = await Promise.all([
    missingAlbumsApi.list(),
    missingAlbumsApi.listSeries(),
    missingAlbumsApi.listIgnored(),
  ])
  missing.value = listData.missing
  notFound.value = listData.not_found
  trackedSeries.value = seriesData
  ignoredAlbums.value = ignoredData
  missingAlbumsStore.refreshCount()
}

async function ignoreAlbum(album) {
  missing.value = missing.value.filter(a => a.id !== album.id) // optimiste
  try {
    await missingAlbumsApi.ignore(album.id)
  } finally {
    await loadResults()
  }
}

const uploadAlbum = ref(null)
function openUpload(album) { uploadAlbum.value = album }
async function onAlbumUploaded(albumId) {
  missing.value = missing.value.filter(a => a.id !== albumId) // optimiste
  uploadAlbum.value = null
  await loadResults()
}

const unignoring = reactive(new Set())

async function unignoreAlbum(item) {
  unignoring.add(item.id)
  try {
    // Revérifie la série côté serveur (~2s) avant de recharger, sinon l'album réaffiché
    // n'existe pas encore dans la liste des manquants.
    await missingAlbumsApi.unignore(item.id)
  } finally {
    unignoring.delete(item.id)
    await loadResults()
  }
}

async function loadLastScan() {
  const { data } = await missingAlbumsApi.lastScan()
  lastScan.value = data
}

async function startScan() {
  startError.value = null
  try {
    await missingAlbumsStore.triggerScan()
  } catch (e) {
    startError.value = e.response?.data?.detail || "Impossible de démarrer l'analyse."
  }
}

// Le scan peut avoir été déclenché depuis le menu "Scanner" global (AppLayout) — dès qu'il se
// termine, quelle que soit la page d'où il a été lancé, on rafraîchit les résultats ici.
watch(() => missingAlbumsStore.scanProgress.status, async (status) => {
  if (status === 'done' || status === 'error') {
    await loadLastScan()
    await loadResults()
  }
})

async function toggleTrack(series) {
  const next = !series.track_new_albums
  series.track_new_albums = next // optimiste
  try {
    await missingAlbumsApi.toggleTracking(series.id, next)
    await loadResults()
  } catch {
    series.track_new_albums = !next
  }
}

// Croix à côté du titre d'un groupe — retire la série du suivi (mêmes effets que "Exclure"
// dans le panneau "Gérer le suivi"), sans avoir à y chercher la série par son nom.
function excludeGroupSeries(group) {
  const series = trackedSeries.value.find(s => s.id === group.series_id)
  if (series) toggleTrack(series)
}

onMounted(async () => {
  try {
    await Promise.all([loadResults(), loadLastScan()])
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppLayout>
    <main class="ma-main">
      <div class="ma-header">
        <div>
          <h1 class="ma-title">
            Albums manquants
            <span v-if="missingCount" class="ma-title-badge">{{ missingCount }}</span>
          </h1>
          <p class="ma-subtitle">{{ lastScanLabel }}</p>
        </div>
        <div class="ma-header-actions">
          <button
            class="btn btn-primary btn-sm"
            :disabled="missingAlbumsStore.scanProgress.status === 'running' || missingAlbumsStore.scanProgress.status === 'pending'"
            @click="startScan"
          >
            {{ missingAlbumsStore.scanProgress.status === 'running' || missingAlbumsStore.scanProgress.status === 'pending' ? 'Analyse en cours…' : 'Vérifier les albums manquants' }}
          </button>
          <p v-if="startError" class="ma-start-error">{{ startError }}</p>
        </div>
      </div>

      <div v-if="loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>

      <div v-else-if="loadError" class="state-box">
        <span class="state-text">Impossible de charger les albums manquants.</span>
      </div>

      <template v-else>
        <div class="tabs-row">
          <button @click="activeTab = 'missing'" :class="['tab-btn', { 'tab-btn-active': activeTab === 'missing' }]">Albums manquants</button>
          <button @click="activeTab = 'manage'" :class="['tab-btn', { 'tab-btn-active': activeTab === 'manage' }]">Gérer le suivi</button>
        </div>

        <!-- ── Albums manquants ── -->
        <!-- Onglet "grille de covers" : pas de carte englobante, comme Séries/Albums — les
             covers portent déjà leur propre cadre, doubler avec un fond+bordure autour de
             toute la grille faisait doublon. Le "Gérer le suivi" plus bas, panneau de
             gestion façon page Réglages, garde lui la carte. -->
        <template v-if="activeTab === 'missing'">
          <section class="ma-section">
            <div v-if="missingCount" class="ma-section-header">
              <div class="ma-search-wrap">
                <SvgIcon name="search" class="ma-search-icon" />
                <input
                  v-model="search"
                  type="search"
                  placeholder="Rechercher une série…"
                  class="form-control ma-search"
                />
              </div>
              <div class="ma-sort-wrap">
                <label class="ma-sort-label" for="ma-sort-select">Trier par</label>
                <select id="ma-sort-select" v-model="sortBy" class="form-control ma-sort-select">
                  <option v-for="o in SORT_OPTIONS" :key="o.key" :value="o.key">{{ o.label }}</option>
                </select>
              </div>
            </div>

            <div v-if="!groupedMissing.length" class="state-box ma-empty">
              <p class="state-text">{{ search ? 'Aucune série ne correspond à ce filtre.' : "Aucun album manquant détecté pour l'instant." }}</p>
            </div>

            <div v-else class="ma-groups">
              <div v-for="group in groupedMissing" :key="group.series_name" class="ma-group">
                <div class="ma-group-header">
                  <div class="ma-group-title-wrap">
                    <router-link :to="`/series/${group.series_id}`" class="ma-group-title">{{ group.series_name }}</router-link>
                    <span class="ma-group-count">{{ group.albums.length }} album{{ group.albums.length > 1 ? 's' : '' }} manquant{{ group.albums.length > 1 ? 's' : '' }}</span>
                  </div>
                  <button
                    class="ma-group-exclude-link"
                    type="button"
                    title="Retirer cette série du suivi des albums manquants"
                    @click="excludeGroupSeries(group)"
                  >Ignorer cette série</button>
                </div>
                <div class="ma-grid scroll-row">
                  <a
                    v-for="album in group.albums"
                    :key="album.id"
                    :href="album.bedetheque_url"
                    target="_blank"
                    rel="noopener"
                    class="ma-card"
                  >
                    <div class="ma-cover">
                      <img v-if="album.cover_url" :src="album.cover_url" loading="lazy" alt="" />
                      <div v-else class="ma-cover-placeholder">📖</div>
                      <div class="ma-cover-dim"></div>
                      <SvgIcon name="square-arrow-out-up-right" class="ma-cover-open-icon" />
                      <span class="ma-badge">T{{ album.number }}</span>
                      <Hint label="Ignorer cet album">
                        <button
                          class="ma-ignore-btn"
                          type="button"
                          @click.stop.prevent="ignoreAlbum(album)"
                        >✕</button>
                      </Hint>
                      <Hint label="Ajouter ce fichier depuis mon appareil">
                        <button
                          class="overlay-btn ma-upload-btn"
                          type="button"
                          @click.stop.prevent="openUpload(album)"
                        ><SvgIcon name="square-plus" style="font-size:20px" /></button>
                      </Hint>
                    </div>
                    <div class="ma-card-info">
                      <p v-if="displayTitle(album)" class="ma-card-title">{{ displayTitle(album) }}</p>
                      <p v-if="album.year" class="ma-card-year">{{ album.year }}</p>
                    </div>
                  </a>
                </div>
              </div>
            </div>

            <p v-if="groupedMissing.length" class="ma-footer-summary">
              {{ missingCount }} album{{ missingCount > 1 ? 's' : '' }} manquant{{ missingCount > 1 ? 's' : '' }} dans {{ groupedMissing.length }} série{{ groupedMissing.length > 1 ? 's' : '' }}
            </p>
          </section>

          <!-- ── Séries non trouvées ── -->
          <section v-if="notFound.length" class="ma-section">
            <div class="ma-section-header">
              <h2 class="ma-section-title">Séries non trouvées</h2>
              <span class="ma-section-count">{{ notFound.length }}</span>
            </div>
            <p class="ma-section-hint">Le nom de la série n'a pas pu être rapproché d'une fiche Bedetheque.</p>
            <ul class="ma-notfound-list">
              <li v-for="s in notFound" :key="s.id">
                <router-link :to="`/series/${s.id}`">{{ s.name }}</router-link>
              </li>
            </ul>
          </section>
        </template>

        <!-- ── Gérer le suivi ── -->
        <section v-else class="card ma-section">
          <div class="ma-manage-panel">
            <div>
              <h3 class="ma-subsection-title">Séries exclues</h3>
              <div class="ma-exclude-search">
                <input
                  v-model="excludeSearch"
                  type="text"
                  placeholder="Exclure une série…"
                  class="form-control ma-search-input"
                />
                <div v-if="excludeSuggestions.length" class="ma-exclude-suggestions">
                  <button
                    v-for="s in excludeSuggestions"
                    :key="s.id"
                    class="ma-exclude-suggestion"
                    @click="excludeSeries(s)"
                  >{{ s.name }}</button>
                </div>
              </div>

              <p v-if="!excludedSeries.length" class="ma-section-hint">Aucune série exclue du suivi.</p>
              <div v-else class="ma-excluded-list">
                <div v-for="s in excludedSeries" :key="s.id" class="ma-excluded-row">
                  <span>{{ s.name }}</span>
                  <button class="btn btn-secondary btn-sm" @click="toggleTrack(s)">Réactiver</button>
                </div>
              </div>
            </div>

            <div>
              <h3 class="ma-subsection-title">Albums ignorés</h3>
              <p v-if="!ignoredAlbums.length" class="ma-section-hint">Aucun album ignoré.</p>
              <template v-else>
                <p class="ma-section-hint">Réapparaissent au prochain scan si tu les réaffiches.</p>
                <div class="ma-excluded-list">
                  <div v-for="item in ignoredAlbums" :key="item.id" class="ma-excluded-row">
                    <span>{{ item.series_name }} — T{{ item.number }}<template v-if="displayTitle(item)"> · {{ displayTitle(item) }}</template></span>
                    <button
                      class="btn btn-secondary btn-sm"
                      :disabled="unignoring.has(item.id)"
                      @click="unignoreAlbum(item)"
                    >{{ unignoring.has(item.id) ? '…' : 'Réafficher' }}</button>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </section>
      </template>
    </main>
  </AppLayout>

  <MissingAlbumUploadModal
    v-if="uploadAlbum"
    :album="uploadAlbum"
    @close="uploadAlbum = null"
    @uploaded="onAlbumUploaded"
  />
</template>

<style scoped>
.ma-main {
  flex: 1;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ma-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.ma-header-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.ma-start-error { font-size: 0.75rem; color: var(--danger, #dc2626); max-width: 260px; text-align: right; }
.ma-title { font-family: var(--font-display); font-weight: 400; text-transform: uppercase; font-size: 1.4rem; color: var(--text); }
.ma-title-badge {
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
  font-size: 0.75rem;
  font-weight: 700;
  color: #fff;
  background: var(--vermilion);
  border-radius: 999px;
  padding: 1px 9px;
}
.ma-subtitle { font-size: 0.82rem; color: var(--muted); margin-top: 4px; }

.ma-section { padding: 16px 20px; }
.ma-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.ma-search-wrap { position: relative; flex: 1; min-width: 200px; max-width: 420px; }
.ma-search-icon {
  position: absolute; left: 11px; top: 50%; transform: translateY(-50%);
  color: var(--muted); font-size: 0.9rem; pointer-events: none;
}
.ma-search { width: 100%; padding: 8px 12px 8px 34px; font-size: 0.85rem; }
.ma-sort-wrap { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ma-sort-label { font-size: 0.82rem; color: var(--muted); white-space: nowrap; }
.ma-sort-select { padding: 7px 10px; font-size: 0.82rem; width: auto; }
.ma-section-title { font-size: 1rem; font-weight: 600; color: var(--text); }
.ma-section-count {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  background: var(--light);
  border-radius: 20px;
  padding: 1px 8px;
}
.ma-section-hint { font-size: 0.8rem; color: var(--muted); margin-bottom: 8px; }

/* Onglets soulignés — même style que les pages Comptes/Bibliothèque. */
.tabs-row {
  display: flex; gap: 22px;
  border-bottom: 1px solid var(--border);
}
.tab-btn {
  padding: 0 0 10px;
  background: none; border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-family: var(--font);
  font-size: 0.85rem; font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn-active { color: var(--vermilion); border-bottom-color: var(--vermilion); }

.ma-empty { padding: 24px 0; }
.ma-footer-summary { font-size: 0.82rem; color: var(--muted); margin-top: 14px; }

.ma-groups { display: flex; flex-direction: column; gap: 16px; margin-top: 10px; }
/* Une série = une carte, chaque album en rangée à défilement horizontal (plutôt qu'une
   grille qui s'enroule sur plusieurs lignes) — plus rapide à parcourir série par série. */
.ma-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.ma-group-title-wrap { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ma-group-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ma-group-title:hover { color: var(--vermilion); text-decoration: underline; }
.ma-group-count {
  flex-shrink: 0;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--muted);
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 9px;
  white-space: nowrap;
}
.ma-group-exclude-link {
  flex-shrink: 0;
  background: none; border: none; cursor: pointer;
  font-family: var(--font);
  font-size: 0.8125rem; font-weight: 600; color: var(--muted);
  white-space: nowrap;
  transition: color 0.12s;
}
.ma-group-exclude-link:hover { color: var(--danger); text-decoration: underline; }

.ma-grid {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  scrollbar-width: none;
}
.ma-grid::-webkit-scrollbar { display: none; }

.ma-card {
  flex: 0 0 auto;
  width: 140px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
  display: block;
}
.ma-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
  text-decoration: none;
}

.ma-cover {
  aspect-ratio: 0.71;
  background: var(--light);
  position: relative;
  overflow: hidden;
}
.ma-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ma-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 2rem; color: var(--placeholder);
}
.ma-cover-dim {
  position: absolute; inset: 0; z-index: 1;
  background: rgba(0,0,0,0.45);
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
.ma-card:hover .ma-cover-dim { opacity: 1; }

.ma-cover-open-icon {
  position: absolute; inset: 0; z-index: 1;
  display: flex; align-items: center; justify-content: center;
  font-size: 40px; color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
.ma-card:hover .ma-cover-open-icon { opacity: 1; }

.ma-badge {
  position: absolute; top: 6px; right: 6px; z-index: 2;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}

.ma-ignore-btn {
  position: absolute; top: 6px; left: 6px; z-index: 2;
  width: 22px; height: 22px; border-radius: 50%;
  background: rgba(0,0,0,0.55); color: #fff;
  border: none; cursor: pointer;
  font-size: 0.7rem; line-height: 1;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.15s, background 0.15s;
}
.ma-card:hover .ma-ignore-btn { opacity: 1; }
.ma-ignore-btn:hover { background: var(--danger, #dc2626); }

.ma-upload-btn {
  position: absolute; bottom: 6px; right: 6px; z-index: 2;
  opacity: 0; transition: opacity 0.15s, transform 0.12s, color 0.12s;
}
.ma-card:hover .ma-upload-btn { opacity: 1; }
.ma-upload-btn:hover { color: var(--primary-focus-border); }

.ma-card-info { padding: 7px 9px; border-top: 1px solid var(--border); }
.ma-card-title {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.ma-card-year {
  display: inline-block;
  font-size: 0.65rem; font-weight: 700; color: var(--muted);
  background: var(--light); border: 1px solid var(--border);
  padding: 1px 5px; border-radius: 3px;
}

.ma-notfound-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.ma-notfound-list li { font-size: 0.85rem; padding: 4px 0; border-bottom: 1px solid var(--border); }
.ma-notfound-list a { color: var(--text); text-decoration: none; }
.ma-notfound-list a:hover { color: var(--vermilion); text-decoration: underline; }
.ma-notfound-list li:last-child { border-bottom: none; }

.ma-manage-panel { margin-top: 10px; display: flex; flex-direction: column; gap: 20px; }
.ma-subsection-title { font-size: 0.8rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 8px; }

.ma-exclude-search { position: relative; max-width: 320px; }
.ma-search-input { width: 100%; padding: 6px 10px; font-size: 0.82rem; }
.ma-exclude-suggestions {
  position: absolute;
  top: calc(100% + 2px);
  left: 0; right: 0;
  z-index: 5;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.ma-exclude-suggestion {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  font-size: 0.82rem;
  color: var(--text);
  background: none;
  border: none;
  cursor: pointer;
}
.ma-exclude-suggestion:hover { background: var(--light); }

.ma-excluded-list { display: flex; flex-direction: column; gap: 2px; }
.ma-excluded-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
}
.ma-excluded-row:last-child { border-bottom: none; }

.state-box { display: flex; align-items: center; justify-content: center; min-height: 120px; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }
.state-text { font-size: 0.85rem; color: var(--muted); }
</style>
