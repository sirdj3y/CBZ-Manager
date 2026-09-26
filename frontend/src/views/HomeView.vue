<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SeriesCard from '../components/library/SeriesCard.vue'
import SeriesActionsMenu from '../components/library/SeriesActionsMenu.vue'
import SeriesMetadataModal from '../components/metadata/SeriesMetadataModal.vue'
import SeriesEnrichModal from '../components/metadata/SeriesEnrichModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import CoverPickerModal from '../components/library/CoverPickerModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { useLibraryStore } from '../stores/library'
import { libraryApi } from '../api/library'
import { tomesApi } from '../api/tomes'
import { useNotificationStore } from '../stores/notifications'
import { useAuthStore } from '../stores/auth'
import { sortTomesByNumber } from '../utils/tomeSort'
import defaultHeroBg from '../assets/home-hero-default-bg.webp'
import heroAccolade from '../assets/hero-accolade.png'
import heroCoverFrame from '../assets/hero-book-frame.png'
import heroCoverSheen from '../assets/hero-book-sheen.png'
import Hint from '../components/ui/Hint.vue'

const router = useRouter()
const library = useLibraryStore()
const notif = useNotificationStore()
const authStore = useAuthStore()
const canSeriesMenu = computed(() => ['library.metadata_edit', 'library.rename', 'library.convert', 'library.download', 'library.delete']
  .some(p => authStore.hasPermission(p)))
const inProgress = ref([])
const recentAlbums = ref([])

// Hover states pour les overlays
const hoveredTome = ref(null)
const hoveredSeries = ref(null)
const hoveredDiscover = ref(null)
// Menu "⋯" ouvert (clé "d_<id>" ou "s_<id>" selon la rangée) — garde la carte en état survolé
// tant que le menu est ouvert. Voir SeriesActionsMenu.
const openMenuId = ref(null)
function setMenuOpen(key, open) {
  if (open) openMenuId.value = key
  else if (openMenuId.value === key) openMenuId.value = null
}

const selectedSeries = ref(null)
const showSeriesMeta = ref(false)
const showEnrich = ref(false)
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
async function handleEnrich(series) {
  await loadSeriesDetail(series)
  showEnrich.value = true
}
async function handleRename(series) {
  await loadSeriesDetail(series)
  showRename.value = true
}
async function handleConvert(series) {
  await loadSeriesDetail(series)
  showConverter.value = true
}
async function handleDownload(series) {
  await loadSeriesDetail(series)
  const ids = sortTomesByNumber(selectedSeries.value.tomes).map(t => t.id)
  if (ids.length) window.location.href = tomesApi.downloadBulkUrl(ids)
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
  tomesApi.getRecent().then(({ data }) => { recentAlbums.value = data; startHeroAutoplay() })
  if (library.series.length === 0) {
    library.fetchSeries()
  } else {
    nextTick(() => { pickDiscoverSeries() })
  }
  if (library.authors.authors.length === 0 && library.authors.publishers.length === 0) {
    library.fetchAuthors()
  }
})
onUnmounted(() => { stopHeroAutoplay() })

watch(() => library.series.length, (newVal, oldVal) => {
  if (oldVal === 0 && newVal > 0) {
    nextTick(() => { pickDiscoverSeries() })
  }
})

// Contrairement à recentSeries (computed sur library.series, donc déjà réactif), recentAlbums
// vient d'un endpoint dédié chargé une seule fois — sans ce watcher, la section "Albums
// récents" restait figée sur son état pré-scan si l'utilisateur restait sur la page Accueil
// pendant un scan.
watch(() => library.scanProgress.status, (status) => {
  if (status === 'done') {
    tomesApi.getRecent().then(({ data }) => { recentAlbums.value = data; heroIndex.value = 0; startHeroAutoplay() })
  }
})

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

// Fusion de "Séries ajoutées récemment" et "Séries mises à jour récemment" — les deux
// triaient en pratique la même liste, juste sur un champ de date différent, et se
// recoupaient presque toujours (un ajout récent est aussi une mise à jour récente).
// Repris tel quel comme section "Résultats" pendant une recherche (comportement existant).
const recentSeries = computed(() => {
  if (library.search.trim()) return library.filteredSeries
  return [...library.series]
    .sort((a, b) => {
      const ta = Math.max(new Date(a.created_at ?? 0).getTime(), new Date(a.updated_at ?? 0).getTime())
      const tb = Math.max(new Date(b.created_at ?? 0).getTime(), new Date(b.updated_at ?? 0).getTime())
      return tb - ta
    })
    .slice(0, 20)
})

// "Redécouvrir" — sélection aléatoire parmi les séries qui ne sont pas déjà mises en avant
// ci-dessus, tirée une fois au chargement de la page (pas à chaque changement réactif de la
// bibliothèque, pour ne pas rebattre les cartes sous les yeux de l'utilisateur en pleine
// navigation) : renouvelle le contenu visible d'une visite à l'autre.
const discoverSeries = ref([])
function pickDiscoverSeries() {
  const shown = new Set(recentSeries.value.map(s => s.id))
  let pool = library.series.filter(s => !shown.has(s.id))
  // Petite bibliothèque (moins d'une vingtaine de séries) : "Séries récentes" couvre déjà
  // tout ou presque, exclure ce qui y figure viderait le tirage — on retombe sur l'ensemble
  // complet plutôt que de masquer la section.
  if (pool.length < 6) pool = library.series
  const shuffled = [...pool]
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
  }
  discoverSeries.value = shuffled.slice(0, 16)
}

// Bannière d'accueil — met en avant les derniers albums ajoutés à la bibliothèque plutôt
// qu'une image piochée au hasard : plus concret ("regarde, ça vient d'arriver") qu'un simple
// habillage décoratif. Présentée en slider (quelques nouveautés, pas toute la liste) plutôt
// qu'un unique élément figé : défilement automatique + flèches au survol pour naviguer
// manuellement. Une série qui n'a encore que ce seul album est présentée comme "nouvelle
// série" plutôt que "nouvel album" (distinction reprise de la maquette fournie).
// Dédupliqué par série (un seul slide par série, son tome le plus récent) : recentAlbums est
// trié par date de création décroissante côté backend, donc le premier tome rencontré par
// série lors du parcours est bien le plus récent. Sans ça, l'import d'une série entière (ex.
// 20 albums d'un coup) noyait le slider de doublons de la même série au lieu de montrer des
// nouveautés variées.
const heroItems = computed(() => {
  const seen = new Set()
  const deduped = []
  for (const t of recentAlbums.value) {
    if (seen.has(t.series_id)) continue
    seen.add(t.series_id)
    deduped.push(t)
  }
  return deduped.slice(0, 8)
})
const heroIndex = ref(0)
watch(heroItems, (items) => { if (heroIndex.value >= items.length) heroIndex.value = 0 })

let heroTimer = null
function startHeroAutoplay() {
  stopHeroAutoplay()
  if (heroItems.value.length < 2) return
  heroTimer = setInterval(() => {
    heroIndex.value = (heroIndex.value + 1) % heroItems.value.length
  }, 6000)
}
function stopHeroAutoplay() {
  if (heroTimer) { clearInterval(heroTimer); heroTimer = null }
}
function heroNext() { if (heroItems.value.length) heroIndex.value = (heroIndex.value + 1) % heroItems.value.length }
function heroPrev() { if (heroItems.value.length) heroIndex.value = (heroIndex.value - 1 + heroItems.value.length) % heroItems.value.length }

const featuredTome = computed(() => heroItems.value[heroIndex.value] || null)
const featuredSeries = computed(() => featuredTome.value
  ? library.series.find(s => s.id === featuredTome.value.series_id) || null
  : null)
const isNewSeries = computed(() => featuredSeries.value?.tome_count === 1)

// Filet anti-image-cassée (voir SeriesDetailView.vue::heroBgError) : un fond dont le fichier
// a disparu du disque retombe sur l'image de secours plutôt qu'un cadre cassé.
const heroBannerError = ref(false)
watch(featuredSeries, () => { heroBannerError.value = false })
const heroBannerUrl = computed(() => featuredSeries.value?.hero_background_version > 0 && !heroBannerError.value
  ? libraryApi.heroImageUrl(featuredSeries.value.id, 'background', featuredSeries.value.hero_background_version)
  : null)
// Repli sur une illustration fixe (pas de dégradé cette fois) quand la série n'a pas encore
// de fond fourni — voir divers/Assets/default-bg.webp. Toujours affiché en fond (.home-hero-bg,
// image locale déjà dans le bundle donc jamais de délai perceptible) : le fond spécifique à la
// série, lui, doit être téléchargé sur le réseau et se pose PAR-DESSUS en fondu une fois chargé
// (voir .home-hero-bg-img/heroBannerLoaded) — sans ce calque séparé, le changement d'URL de
// arrière-plan CSS remplaçait le défaut par du vide le temps du téléchargement, perçu comme un
// bref flash "fond par défaut puis fond réel" plutôt qu'une transition volontaire.
const heroBannerLoaded = ref(false)
watch(heroBannerUrl, () => { heroBannerLoaded.value = false })

function onHeroBgError() { heroBannerError.value = true }

// "Vos séries" — séries avec un logo "fiche" fourni (hero_logo_version, voir
// SeriesMetadataModal.vue), en rangée défilable manuellement — même gabarit que les autres
// sections de l'accueil (.scroll-row), plutôt qu'un bandeau à part qui ne ressemblait à rien
// d'autre sur la page. Triées par nom pour un ordre stable d'un chargement à l'autre.
const seriesWithLogo = computed(() => [...library.series]
  .filter(s => s.hero_logo_version > 0)
  .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })))
// Filet anti-image-cassée (voir SeriesDetailView.vue::heroLogoError) : un logo dont le
// fichier a disparu du disque retombe sur le nom de la série plutôt qu'un cadre cassé.
const brokenLogoIds = ref(new Set())
function onLogoError(id) { brokenLogoIds.value = new Set(brokenLogoIds.value).add(id) }

// "Genres" — les plus représentés dans la bibliothèque, comptés par nombre de séries (pas de
// nouvel appel réseau : SeriesOut.genres est déjà chargé avec le reste de library.series,
// voir GlobalSearchModal.vue pour un autre usage de ce champ). Clic → BooksView filtré, même
// mécanique que les chips genre de TomeDetailView.vue.
const topGenres = computed(() => {
  const counts = new Map()
  for (const s of library.series) {
    for (const g of s.genres || []) {
      counts.set(g, (counts.get(g) || 0) + 1)
    }
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
})

// Cards stats sous le hero — auteurs/éditeurs viennent de library.authors (chargé ci-dessus
// si pas déjà en cache par la page Auteurs), le reste est déjà disponible via library.series.
const totalAlbums = computed(() => library.series.reduce((s, x) => s + (x.tome_count || 0), 0))
</script>

<template>
  <AppLayout>
    <main class="home-content">

      <!-- Bannière "Nouveauté" — slider sur les derniers albums ajoutés (voir script), fond
           tiré de la série en cours (ou image de secours), sans fondu par-dessus cette fois :
           la cover de l'album vient à la place masquer la coupure entre le texte et le fond. -->
      <section
        v-if="featuredTome"
        class="home-hero"
        @mouseenter="stopHeroAutoplay"
        @mouseleave="startHeroAutoplay"
      >
        <div class="home-hero-bg-clip">
          <!-- Fond par défaut (image locale du bundle, jamais de délai réseau) — reste
               visible tant que le fond spécifique à la série n'est pas chargé. -->
          <div class="home-hero-bg" :style="{ backgroundImage: `url(${defaultHeroBg})` }"></div>
          <!-- Fond spécifique à la série, en fondu par-dessus une fois chargé (voir
               heroBannerLoaded) plutôt qu'un remplacement brutal de background-image CSS, qui
               laissait un vide/flash le temps du téléchargement. -->
          <img
            v-if="heroBannerUrl"
            :key="heroBannerUrl"
            :src="heroBannerUrl"
            alt=""
            aria-hidden="true"
            class="home-hero-bg-img"
            :class="{ 'home-hero-bg-img-loaded': heroBannerLoaded }"
            @load="heroBannerLoaded = true"
            @error="onHeroBgError"
          >
          <div class="home-hero-bg-fade"></div>
          <!-- Trame de points façon impression BD — même overlay que SeriesDetailView.vue
               (voir hero-bd-replication.md), point vermillon 45% dans color-mix,
               mix-blend-mode:multiply pour foncer le fond dessous plutôt que le voiler. -->
          <div class="home-hero-halftone"></div>
        </div>
        <!-- Montage "livre 3D" — 3 calques superposés en CSS (cadre statique + vraie cover +
             léger dégradé d'ombrage) plutôt qu'une image composée à la volée côté backend :
             la cover reste le petit JPEG déjà en cache (voir cover_cache.py), le cadre et le
             dégradé sont deux assets fixes chargés une seule fois par le navigateur — un
             cover-mockup généré par tome pesait 2 à 4 Mo pièce, ici on reste sous le Mo au
             total pour toute la session. Placée avant .home-hero-inner dans le DOM : .home-hero
             est un flex row, l'ordre du DOM fixe l'ordre visuel gauche→droite. -->
        <div v-if="featuredTome.cover_url" :key="featuredTome.id" class="home-hero-cover">
          <img class="hero-cover-art" :src="featuredTome.cover_url" :alt="featuredTome.title" />
          <img class="hero-cover-sheen" :src="heroCoverSheen" alt="" aria-hidden="true" />
          <img class="hero-cover-frame" :src="heroCoverFrame" alt="" aria-hidden="true" />
        </div>
        <div class="home-hero-inner">
          <span class="home-hero-badge">★ {{ isNewSeries ? 'Nouvelle série' : 'Nouvel album' }}</span>
          <h1 class="home-hero-title">{{ featuredSeries?.name || featuredTome.series_name }}</h1>
          <div class="home-hero-accolade" aria-hidden="true"></div>
          <p class="home-hero-album-title">{{ featuredTome.title || ('Tome ' + featuredTome.number) }}</p>
          <p class="home-hero-subtitle">Le nouveau tome de {{ featuredSeries?.name || featuredTome.series_name }} est disponible dans votre bibliothèque !</p>
          <div class="home-hero-actions">
            <button type="button" class="btn btn-primary" @click="router.push(`/tomes/${featuredTome.id}`)">Voir l'album →</button>
            <button type="button" class="btn btn-secondary" @click="router.push(`/series/${featuredTome.series_id}`)">Voir la série</button>
          </div>
        </div>
        <template v-if="heroItems.length > 1">
          <button type="button" class="hero-arrow hero-arrow-left" aria-label="Nouveauté précédente" @click="heroPrev">
            <SvgIcon name="chevron-down" />
          </button>
          <button type="button" class="hero-arrow hero-arrow-right" aria-label="Nouveauté suivante" @click="heroNext">
            <SvgIcon name="chevron-down" />
          </button>
          <!-- Pastilles ancrées en bas au centre de tout le slider (pas seulement sous le bloc
               texte) — sorties de .home-hero-inner pour se positionner par rapport à .home-hero. -->
          <div class="hero-dots">
            <span v-for="(t, i) in heroItems" :key="t.id" :class="['hero-dot', { active: i === heroIndex }]" @click="heroIndex = i"></span>
          </div>
        </template>
      </section>

      <!-- Stats globales — sous le hero plutôt qu'au-dessus (essayé là-haut avant l'arrivée
           du slider, retiré faute de place ; ici elles ne sont plus en concurrence avec lui).
           Barre unique à séparateurs internes plutôt que 4 cartes séparées, sans icône —
           idée reprise d'une maquette de comparaison, plus compact/épuré. -->
      <div class="home-stats-bar">
        <div class="home-stat-seg" @click="router.push('/books')">
          <div class="home-stat-num">{{ totalAlbums }}</div>
          <div class="home-stat-label">Albums</div>
        </div>
        <div class="home-stat-seg" @click="router.push('/series')">
          <div class="home-stat-num">{{ library.series.length }}</div>
          <div class="home-stat-label">Séries</div>
        </div>
        <div class="home-stat-seg" @click="router.push('/authors')">
          <div class="home-stat-num">{{ library.authors.authors.length }}</div>
          <div class="home-stat-label">Auteurs</div>
        </div>
        <div class="home-stat-seg" @click="router.push('/authors')">
          <div class="home-stat-num">{{ library.authors.publishers.length }}</div>
          <div class="home-stat-label">Éditeurs</div>
        </div>
      </div>

      <!-- Résultats de recherche -->
      <div v-if="library.search.trim() && !library.filteredSeries.length" class="empty-state">
        <SvgIcon name="search" class="empty-icon" />
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
            <div class="section-title-group">
              <h2 class="section-title">Poursuivre la lecture</h2>
              <span class="section-subtitle">{{ inProgress.length }} en cours</span>
            </div>
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
                <div class="continue-cover-clip">
                  <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="continue-cover-img" />
                  <div v-else class="continue-cover-placeholder">📖</div>
                  <div v-if="hoveredTome === t.id" class="continue-read-overlay">
                    <SvgIcon name="read" class="continue-read-icon" />
                  </div>
                  <div class="continue-progress-bar">
                    <div class="continue-progress-fill" :style="{ width: t.progress_pct + '%' }"></div>
                  </div>
                </div>
              </div>
              <div class="continue-info">
                <p class="continue-title">{{ t.title || t.filename }}</p>
                <p class="continue-pct">{{ t.progress_pct }}%</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Vos séries — même gabarit que les autres rangées (.scroll-row, défilement
             manuel) plutôt qu'un bandeau à part : essayé en bandeau défilant tout seul
             (auto-scroll) puis à côté des stats, dans les deux cas jugé pas à sa place —
             en rangée classique, elle se fond avec le reste de la page. -->
        <section v-if="!library.search.trim() && seriesWithLogo.length" class="section">
          <div class="section-header">
            <div class="section-title-group">
              <h2 class="section-title">Vos séries</h2>
            </div>
            <span class="section-link" @click="router.push('/series')">Tout voir</span>
          </div>
          <div class="scroll-row">
            <router-link
              v-for="s in seriesWithLogo"
              :key="s.id"
              :to="`/series/${s.id}`"
              class="logo-card"
              :title="s.name"
            >
              <img v-if="!brokenLogoIds.has(s.id)" :src="libraryApi.heroImageUrl(s.id, 'logo', s.hero_logo_version)" :alt="s.name" @error="onLogoError(s.id)">
              <span v-else class="logo-card-fallback">{{ s.name }}</span>
            </router-link>
          </div>
        </section>

        <!-- Albums ajoutés récemment -->
        <section v-if="recentAlbums.length" class="section">
          <div class="section-header">
            <div class="section-title-group">
              <h2 class="section-title">Albums ajoutés récemment</h2>
            </div>
            <span class="section-link" @click="router.push('/books')">Tout voir</span>
          </div>
          <div class="scroll-row">
            <div
              v-for="t in recentAlbums"
              :key="t.id"
              class="scroll-card scroll-card-tome"
              @click="router.push(`/tomes/${t.id}`)"
            >
              <div class="scroll-cover">
                <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📖</div>
              </div>
              <div class="scroll-tome-info">
                <p class="scroll-label">{{ t.title || t.filename }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Sélection — tirage aléatoire, différent à chaque visite (voir pickDiscoverSeries) -->
        <section v-if="!library.search.trim() && discoverSeries.length" class="section">
          <div class="section-header">
            <div class="section-title-group">
              <h2 class="section-title">Sélection</h2>
              <span class="section-subtitle">séries de votre bibliothèque</span>
            </div>
            <span class="section-link" @click="router.push('/series')">Tout voir</span>
          </div>
          <div class="scroll-row">
            <div
              v-for="s in discoverSeries"
              :key="s.id"
              :class="['scroll-card scroll-card-series', { 'menu-open': openMenuId === 'd_' + s.id }]"
              @click="router.push(`/series/${s.id}`)"
              @mouseenter="hoveredDiscover = s.id"
              @mouseleave="hoveredDiscover = null"
            >
              <div class="scroll-cover">
                <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📚</div>
                <div v-if="hoveredDiscover === s.id || openMenuId === 'd_' + s.id" class="scroll-cover-dim"></div>
                <span class="series-badge-card">{{ s.tome_count }}</span>
                <div v-if="hoveredDiscover === s.id || openMenuId === 'd_' + s.id" class="scroll-overlay" @click.stop>
                  <Hint v-if="authStore.hasPermission('library.metadata_edit')" label="Modifier les métadonnées">
                    <button class="overlay-btn" @click="handleEdit(s)">
                      <SvgIcon name="edit" style="font-size:20px" />
                    </button>
                  </Hint>
                  <div class="overlay-spacer"></div>
                  <SeriesActionsMenu
                    v-if="canSeriesMenu" :series="s"
                    :open="openMenuId === 'd_' + s.id" @update:open="setMenuOpen('d_' + s.id, $event)"
                    @edit="handleEdit" @enrich="handleEnrich" @rename="handleRename" @convert="handleConvert"
                    @download="handleDownload" @set-cover="handleSetCover" @toggle-hidden="handleToggleHidden" @delete="handleDelete"
                  >
                    <button class="overlay-btn" :class="{ 'overlay-btn-active': openMenuId === 'd_' + s.id }">
                      <SvgIcon name="more-vertical" style="font-size:20px" />
                    </button>
                  </SeriesActionsMenu>
                </div>
              </div>
              <div class="scroll-series-info">
                <p class="scroll-series-name">{{ s.name }}</p>
                <p class="scroll-series-count">{{ s.tome_count }} album{{ s.tome_count !== 1 ? 's' : '' }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Résultats de recherche par série (voir recentSeries) — n'est plus affichée comme
             rangée de navigation "Séries récentes" hors recherche : redondante avec "Albums
             ajoutés récemment" juste au-dessus, qui couvre déjà ce besoin. -->
        <section v-if="library.search.trim() && recentSeries.length" class="section">
          <div class="section-header">
            <h2 class="section-title">Résultats</h2>
          </div>
          <div class="scroll-row">
            <div
              v-for="s in recentSeries"
              :key="s.id"
              :class="['scroll-card scroll-card-series', { 'menu-open': openMenuId === 's_' + s.id }]"
              @click="router.push(`/series/${s.id}`)"
              @mouseenter="hoveredSeries = s.id"
              @mouseleave="hoveredSeries = null"
            >
              <div class="scroll-cover">
                <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="scroll-cover-img" />
                <div v-else class="scroll-cover-placeholder">📚</div>
                <div v-if="hoveredSeries === s.id || openMenuId === 's_' + s.id" class="scroll-cover-dim"></div>
                <span class="series-badge-card">{{ s.tome_count }}</span>
                <div v-if="hoveredSeries === s.id || openMenuId === 's_' + s.id" class="scroll-overlay" @click.stop>
                  <Hint v-if="authStore.hasPermission('library.metadata_edit')" label="Modifier les métadonnées">
                    <button class="overlay-btn" @click="handleEdit(s)">
                      <SvgIcon name="edit" style="font-size:20px" />
                    </button>
                  </Hint>
                  <div class="overlay-spacer"></div>
                  <SeriesActionsMenu
                    v-if="canSeriesMenu" :series="s"
                    :open="openMenuId === 's_' + s.id" @update:open="setMenuOpen('s_' + s.id, $event)"
                    @edit="handleEdit" @enrich="handleEnrich" @rename="handleRename" @convert="handleConvert"
                    @download="handleDownload" @set-cover="handleSetCover" @toggle-hidden="handleToggleHidden" @delete="handleDelete"
                  >
                    <button class="overlay-btn" :class="{ 'overlay-btn-active': openMenuId === 's_' + s.id }">
                      <SvgIcon name="more-vertical" style="font-size:20px" />
                    </button>
                  </SeriesActionsMenu>
                </div>
              </div>
              <div class="scroll-series-info">
                <p class="scroll-series-name">{{ s.name }}</p>
                <p class="scroll-series-count">{{ s.tome_count }} album{{ s.tome_count !== 1 ? 's' : '' }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Genres — les plus représentés dans la bibliothèque (voir topGenres), en badges
             plutôt qu'en cards (essayé, moins adapté à du texte seul sans image). -->
        <section v-if="!library.search.trim() && topGenres.length" class="section">
          <div class="section-header">
            <div class="section-title-group">
              <h2 class="section-title">Genres</h2>
              <span class="section-subtitle">{{ topGenres.length }} genre{{ topGenres.length !== 1 ? 's' : '' }}</span>
            </div>
          </div>
          <div class="scroll-row genre-badges">
            <span
              v-for="g in topGenres"
              :key="g.name"
              class="genre-badge"
              @click="router.push({ path: '/series', query: { genre: g.name } })"
            >{{ g.name }} <span class="genre-badge-count">{{ g.count }}</span></span>
          </div>
        </section>
      </template>
    </main>


    <SeriesMetadataModal v-if="showSeriesMeta && selectedSeries" :series="selectedSeries" @close="showSeriesMeta = false" @saved="library.fetchSeries()" @deleted="(id) => { library.series = library.series.filter(s => s.id !== id); showSeriesMeta = false }" @enrich="showSeriesMeta = false; showEnrich = true" />
    <SeriesEnrichModal v-if="showEnrich && selectedSeries" :series="selectedSeries" @close="showEnrich = false" @saved="library.fetchSeries()" />
    <RenameModal v-if="showRename && selectedSeries" :tomes="sortTomesByNumber(selectedSeries.tomes)" :series-name="selectedSeries.name" @close="showRename = false" @done="showRename = false" />
    <ConverterModal v-if="showConverter && selectedSeries" :tomes="sortTomesByNumber(selectedSeries.tomes)" @close="showConverter = false" @done="showConverter = false" />
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

/* Bannière "Nouveauté" — cover et texte groupés côte à côte dans un flex row (au lieu d'une
   cover centrée en absolute + texte plaqué à gauche, essayé avant) : la cover reste ancrée
   près du bord gauche, le texte la suit directement, la moitié droite du fond reste visible
   sans être recouverte ni assombrie. Les éléments absolus (bg-clip, arrows, dots) ignorent le
   flex comme d'habitude — seuls cover et inner en sont des items. */
.home-hero {
  position: relative;
  border-radius: 16px; box-shadow: var(--shadow-lg);
  background: var(--light);
  overflow: hidden;
  min-height: 360px;
  display: flex; align-items: center; gap: 32px;
  padding: 0 40px 0 64px;
}
.home-hero-bg-clip { position: absolute; inset: 0; border-radius: 16px; overflow: hidden; }
/* Toute la carte couverte, sans déformer l'image (cover recadre au besoin, contrairement à
   100% 100% essayé juste avant qui l'étirait). Flou essayé puis retiré : plus nécessaire
   maintenant que les fonds sont préparés en 1600×400 (voir échange avec l'utilisateur), le
   voile noir ci-dessous suffit pour la lisibilité du texte. */
.home-hero-bg { position: absolute; inset: 0; background-size: cover; background-position: center; background-repeat: no-repeat; }
/* Fondu du fond spécifique à la série par-dessus le défaut (voir heroBannerLoaded) — même
   cadrage que .home-hero-bg (object-fit/position miroir de background-size/position). */
.home-hero-bg-img {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover; object-position: center;
  opacity: 0;
  transition: opacity 0.4s ease;
}
.home-hero-bg-img-loaded { opacity: 1; }
.home-hero-inner { position: relative; padding: 36px 40px 36px 0; max-width: 450px; }
.home-hero-badge {
  display: inline-block;
  padding: 3px 9px; margin-bottom: 12px;
  background: var(--vermilion); color: #fff;
  font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  border-radius: 999px;
}
/* Écart de taille/graisse volontairement marqué entre le nom de la série (le vrai titre de
   la bannière) et le titre de l'album (une précision en dessous, pas un second titre à
   poids égal) — cette hiérarchie était trop faible dans la version précédente. */
.home-hero-title {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 2.6rem; line-height: 1.02; color: #fff; margin-bottom: 4px;
}
/* Petite accolade décorative sous le titre (voir divers/accolade.png) — recolorée via
   mask-image plutôt qu'affichée telle quelle (fichier source noir) pour suivre l'accent de
   la bannière et rester cohérente si le thème change. */
.home-hero-accolade {
  width: 48px; height: 15px; margin-bottom: 10px;
  background-color: var(--vermilion);
  -webkit-mask-image: url('../assets/hero-accolade.png'); mask-image: url('../assets/hero-accolade.png');
  -webkit-mask-size: contain; mask-size: contain;
  -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
  -webkit-mask-position: left center; mask-position: left center;
}
.home-hero-album-title { font-size: 0.85rem; font-weight: 500; color: rgba(255,255,255,.9); margin-bottom: 12px; }
.home-hero-subtitle { font-size: 0.875rem; color: rgba(255,255,255,.9); line-height: 1.5; margin-bottom: 22px; }
.home-hero-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

/* Voile "to right" (sombre sous cover+texte à gauche, transparent à droite) — cover et texte
   restent groupés dans la moitié gauche du hero (voir .home-hero flex), la moitié droite du
   fond doit rester nettement visible. Plateau opaque (au lieu d'un dégradé pur dès 0%) pour
   bien assombrir toute la zone sous le texte, fondu resserré (62% plutôt que pleine largeur)
   pour ne pas empiéter sur la partie découverte du fond. */
/* Brun chaud (26,20,14) plutôt que noir pur — idée reprise d'une maquette de comparaison,
   colle mieux à la palette crème/chaude de l'app qu'un noir neutre. */
.home-hero-bg-fade {
  position: absolute; inset: 0;
  background: linear-gradient(to right, rgba(26,20,14,.92) 0%, rgba(26,20,14,.92) 35%, rgba(26,20,14,0) 62%);
}
/* Trame de points (halftone) — voir SeriesDetailView.vue::.series-hero-halftone, mêmes
   réglages (point 1.5px/1.6px, grille 8px, opacity .25 en plus des 45% de color-mix). */
.home-hero-halftone {
  position: absolute; inset: 0;
  pointer-events: none;
  opacity: 0.25;
  mix-blend-mode: multiply;
  background-image: radial-gradient(color-mix(in srgb, var(--vermilion) 45%, transparent) 1.5px, transparent 1.6px);
  background-size: 8px 8px;
}

/* Cover de l'album — montage "livre 3D" en 3 calques CSS plutôt qu'une image composée à la
   volée côté backend (voir historique : ancienne services/hero_mockup.py, un PNG de 2 à 4 Mo
   généré et mis en cache par tome). Le cadre (hero-book-frame.png) et le dégradé d'ombrage
   (hero-book-sheen.png) sont deux assets fixes, calibrés une fois sur le rectangle exact de
   la face du mockup (voir génération : script one-shot, coordonnées en dur ci-dessous) ;
   seule la vraie cover (déjà un petit JPEG mis en cache par ailleurs) change par album.
   Item flex normal (plus en absolute centré) : hauteur fixe + aspect-ratio pour la largeur,
   position:relative pour que ses enfants (frame/art/sheen, en absolute avec des % d'inset)
   continuent de se positionner par rapport à elle. */
.home-hero-cover {
  position: relative; flex: 0 0 auto;
  height: 300px; aspect-ratio: 1862 / 2496;
}
.hero-cover-frame, .hero-cover-art, .hero-cover-sheen { position: absolute; display: block; }
.hero-cover-frame { inset: 0; width: 100%; height: 100%; }
/* Rectangle de la face du mockup, en % de l'image entière (33,42)-(1820,2399) sur 1862x2496. */
.hero-cover-art, .hero-cover-sheen {
  left: 1.77%; top: 1.68%; width: 95.97%; height: 94.43%;
}
.hero-cover-art { object-fit: fill; border-radius: 1%; }
.hero-cover-sheen { mix-blend-mode: multiply; pointer-events: none; border-radius: 1%; }

/* Flèches de navigation — visibles seulement au survol de la bannière (voir @mouseenter sur
   .home-hero), même logique discrète que les overlays des .scroll-card. */
.hero-arrow {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 38px; height: 38px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.85); color: #212121; border: none; cursor: pointer;
  font-size: 18px; opacity: 0; pointer-events: none;
  transition: opacity 0.18s, background 0.18s;
  z-index: 3;
}
.home-hero:hover .hero-arrow { opacity: 1; pointer-events: auto; }
.hero-arrow:hover { background: #fff; }
.hero-arrow-left { left: 14px; }
.hero-arrow-left .svg-icon { transform: rotate(90deg); }
.hero-arrow-right { right: 14px; }
.hero-arrow-right .svg-icon { transform: rotate(-90deg); }

/* Pastilles ancrées en bas au centre de tout le slider (au lieu de sous le bloc texte, à
   gauche), sur le modèle des carrousels classiques. */
.hero-dots {
  position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 6px; z-index: 3;
}
.hero-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,0.5); cursor: pointer;
  transition: background 0.18s, transform 0.18s;
}
.hero-dot:hover { background: rgba(255,255,255,0.8); }
.hero-dot.active { background: #fff; transform: scale(1.3); }

/* Tablette (ex. iPad 10e gen, ~820-1180px selon orientation) : la cover pleine hauteur
   recouvrait le texte, qui n'a pas la place de s'étrécir davantage à côté d'elle sans devenir
   illisible — repli sur le fond seul, comme une bannière plus classique. */
@media (max-width: 1420px) {
  .home-hero-cover { display: none; }
}

@media (max-width: 620px) {
  .home-hero { padding: 0; gap: 0; }
  .home-hero-inner { padding: 26px 22px; max-width: none; }
  /* Recadrage pensé pour desktop — rendrait mal en colonne étroite, même choix que
     series-hero-bg-clip sur mobile. */
  .home-hero-bg-clip { display: none; }
  .hero-arrow { display: none; }
  /* .home-hero-bg-clip masqué juste au-dessus ⇒ plus de fond ni de voile sombre dessous, texte
     posé directement sur le fond clair de .home-hero (var(--light)) : les couleurs claires
     pensées pour un fond assombri (voir plus haut) redeviennent illisibles ici. */
  .home-hero-title { color: var(--text); }
  .home-hero-album-title, .home-hero-subtitle { color: var(--muted); }
}

/* Stats globales — 4 cards en rangée sous le hero (Albums/Séries/Auteurs/Éditeurs). */
.home-stats-bar {
  display: grid; grid-template-columns: repeat(4, 1fr);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden;
}
.home-stat-seg {
  padding: 18px 22px; cursor: pointer;
  border-right: 1px solid var(--border);
  transition: background 0.15s;
}
.home-stat-seg:last-child { border-right: none; }
.home-stat-seg:hover { background: var(--light); }
.home-stat-num { font-size: 1.9rem; font-weight: 600; letter-spacing: -0.02em; color: var(--text); line-height: 1; margin-bottom: 4px; }
.home-stat-label { font-size: 0.8rem; color: var(--muted); font-weight: 500; }
/* En dessous de 900px (tablette/smartphone) : grille 2×2 plutôt que 4 en rangée — un
   smartphone en portrait n'a jamais assez de largeur pour 4 colonnes sans les tasser
   illisiblement. Gardée en 2 colonnes jusqu'aux plus petits écrans (voir palier 480px
   ci-dessous, qui resserre juste le padding/la taille du chiffre) plutôt que de retomber à 1
   seule colonne : 4 lignes empilées prenaient beaucoup de hauteur pour peu d'information. */
@media (max-width: 900px) {
  .home-stats-bar { grid-template-columns: repeat(2, 1fr); }
  .home-stat-seg:nth-child(2) { border-right: none; }
  .home-stat-seg:nth-child(1), .home-stat-seg:nth-child(2) { border-bottom: 1px solid var(--border); }
}
@media (max-width: 480px) {
  .home-stat-seg { padding: 14px 16px; }
  .home-stat-num { font-size: 1.5rem; }
}

/* "Vos séries" — carte par logo dans une .scroll-row classique (même comportement que les
   autres rangées : défilement manuel à la souris/au doigt, pas d'animation automatique).
   Format "paysage" (pas l'aspect-ratio portrait des covers) puisqu'un logo est presque
   toujours plus large que haut. */
.logo-card {
  flex: 0 0 auto; width: 130px; height: 78px;
  display: flex; align-items: center; justify-content: center;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow-sm); padding: 8px 14px;
  transition: box-shadow 0.18s, transform 0.18s;
}
.logo-card:hover { box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg); transform: translateY(-2px); }
.logo-card img { max-width: 100%; max-height: 100%; object-fit: contain; }
/* Filet anti-image-cassée (voir onLogoError) : le nom de la série plutôt qu'un cadre vide
   si le fichier a disparu du disque. */
.logo-card-fallback {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 0.9rem; line-height: 1.15; color: var(--text); text-align: center;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical;
  max-height: 3.6em;
}

/* "Genres" — pastilles arrondies qui s'enroulent sur plusieurs lignes plutôt qu'une rangée
   défilante (essayé en cards façon "Vos séries" d'abord, moins adapté à du texte court sans
   image). Le correctif de bordure haute rognée (voir .scroll-row) est maintenant porté
   directement par .scroll-row, plus besoin de le dupliquer ici. */
.genre-badge {
  flex: 0 0 auto;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 999px;
  font-size: 0.9rem; font-weight: 600; color: var(--text);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s, transform 0.15s;
}
.genre-badge:hover { background: var(--light); border-color: var(--vermilion); color: var(--vermilion); transform: translateY(-1px); }
.genre-badge-count { font-family: var(--font-mono); font-size: 0.75rem; font-weight: 500; color: var(--muted); }
.genre-badge:hover .genre-badge-count { color: var(--vermilion); }

/* Section */
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.section-title { font-size: 1rem; font-weight: 600; display: flex; align-items: center; gap: 6px; }
/* Sous-titre contextuel + lien "Tout voir" — idée reprise d'une maquette de comparaison,
   absents jusqu'ici (juste le titre nu). */
.section-title-group { display: flex; align-items: baseline; gap: 12px; }
.section-subtitle { font-family: var(--font-mono); font-size: 0.72rem; color: var(--muted); }
.section-link { font-size: 0.8125rem; color: var(--vermilion); cursor: pointer; flex-shrink: 0; }
.section-link:hover { text-decoration: underline; }

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

/* Continuer la lecture — overflow:visible sur la card qui porte la bordure/l'ombre (même
   principe que .book-card) : combiner box-shadow + border-radius + overflow:hidden + un
   transform au survol sur le MÊME élément fait rendre le navigateur (WebKit notamment) une
   ombre/bordure carrée et dentelée au lieu de suivre les coins arrondis (bug de compositing
   déclenché par le transform). Le clipping de l'image est délégué à .continue-cover-clip, un
   enfant dédié sans ombre ni transform — jamais les deux sur le même élément. */
.continue-card {
  cursor: pointer;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: visible;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.18s, transform 0.18s;
}
.continue-card:hover { box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg); transform: translateY(-2px); }
.continue-cover {
  aspect-ratio: 0.71; position: relative;
}
.continue-cover-clip {
  position: absolute; inset: 0;
  overflow: hidden; border-radius: var(--radius) var(--radius) 0 0;
  background: var(--light);
}
.continue-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s; }
.continue-card:hover .continue-cover-img { transform: scale(1.04); }
.continue-cover-placeholder {
  width: 100%; height: 100%; display: flex;
  align-items: center; justify-content: center; font-size: 2.5rem; color: var(--placeholder);
}
/* Affinée (4 → 3px) et remplie en rouge (var(--danger)) plutôt que la couleur primaire, pour
   mieux ressortir sur une cover sombre. */
.continue-progress-bar {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 3px; background: rgba(0,0,0,0.2);
}
.continue-progress-fill {
  height: 100%; background: var(--danger);
  transition: width 0.3s ease;
}
.continue-info { padding: 8px 10px; border-top: 1px solid var(--border); }
.continue-title {
  font-size: 0.8125rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.continue-pct { font-family: var(--font-mono); font-size: 0.75rem; color: var(--muted); }

/* Empty */
.empty-state {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; min-height: 300px; text-align: center;
}
.empty-icon { font-size: 4rem; }
.empty-title { font-size: 1.2rem; font-weight: 600; }
.empty-desc { font-size: 0.875rem; color: var(--muted); max-width: 360px; }

/* Scroll row (horizontal scroll sections) — défilement toujours possible (molette/trackpad/
   glisser), juste sans ascenseur visible en dessous (retour utilisateur : surchargeait
   visuellement ces rangées de cartes). Fondu sur le bord droit (mask-image plutôt qu'un
   calque superposé : pas besoin de connaître la couleur de fond derrière, fonctionne pareil
   en clair/sombre) pour signaler qu'il y a plus à découvrir au-delà de ce qui est visible. */
/* overflow-x:auto force overflow-y:auto (règle CSS) sur ce même élément, qui rogne le pixel
   du haut de la bordure de tout enfant collé au bord (déjà rencontré sur les pastilles
   "Genres", puis sur les cards de card partout ailleurs dans ce fichier) — padding-top +
   margin-top négatif égal en compense l'effet une fois pour toutes ici plutôt que de le
   dupliquer section par section, sans décaler visuellement la rangée dans la page.
   Même souci sur le bord GAUCHE, mais seulement visible sur la toute première carte de
   chaque rangée (scrollLeft ne peut jamais descendre sous 0 : rien à faire défiler avant
   elle, donc rien ne masque le rognage comme le fait le "gap" entre les cartes suivantes) —
   même compensation padding-left/margin-left négatif, même principe. */
.scroll-row {
  display: flex;
  flex-direction: row;
  gap: 12px;
  padding-top: 4px;
  margin-top: -4px;
  padding-left: 4px;
  margin-left: -4px;
  overflow-x: auto;
  scrollbar-width: none;
  mask-image: linear-gradient(to right, black calc(100% - 14px), rgba(0,0,0,0.6) 100%);
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 14px), rgba(0,0,0,0.6) 100%);
}
.scroll-row::-webkit-scrollbar { display: none; }

.scroll-card {
  flex: 0 0 auto;
  width: 160px;
  cursor: pointer;
  transition: transform 0.18s;
  position: relative;
  z-index: 1;
}
/* Juste assez pour passer au-dessus des cards voisines (z-index:1) — jamais au-dessus de
   la barre du haut (z-index:40, sticky) sous peine de la traverser au survol. L'anneau de
   survol est posé ici, sur .scroll-card (toujours combiné à .scroll-card-series/-tome, qui
   portent la bordure/le fond/le border-radius et restent en overflow:visible) plutôt que sur
   .scroll-cover : combiner box-shadow + border-radius + overflow:hidden + un transform sur le
   MÊME élément fait rendre certains navigateurs (WebKit notamment) une ombre/bordure carrée et
   dentelée au lieu de suivre les coins arrondis (bug de compositing déclenché par le
   transform) — même principe que .book-card/.continue-card. */
.scroll-card:hover { transform: translateY(-2px); z-index: 2; box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg); }
.scroll-card.menu-open { z-index: 6; }

/* .scroll-cover clippe l'image (et l'overlay/badge/dim qui la recouvrent) à ses coins arrondis
   — jamais d'ombre ni de transform sur cet élément, seulement sur la card externe ci-dessus. */
.scroll-cover {
  width: 100%;
  aspect-ratio: 0.71;
  background: var(--light);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 6px;
  position: relative;
}
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
  background: rgba(0,0,0,0.45);
  pointer-events: none;
}
/* Badge nombre d'albums — positionné par rapport au .scroll-card */
.series-badge-card {
  position: absolute; top: 6px; right: 6px; z-index: 5;
  min-width: 22px; height: 22px; padding: 0 4px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-family: var(--font-mono); font-size: 0.68rem; font-weight: 700;
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
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.scroll-series-count { font-size: 0.75rem; color: var(--muted); }

/* L'overlay boutons : positionné depuis le bas du .scroll-card-series,
   au-dessus du bandeau info (scroll-series-info ~42px) */
/* Déplacé dans .scroll-cover (avant : enfant direct de .scroll-card, bottom:46px calé "à la
   main" sur la hauteur supposée du bandeau info) — un nom de série sur une seule ligne rend
   ce bandeau plus court que l'estimation, donc les icônes dépassaient de la cover. Ancré au
   bas de .scroll-cover directement (position:relative), plus de calcul à recaler. */
.scroll-overlay {
  position: absolute; left: 0; right: 0; bottom: 0;
  height: 36px; z-index: 10;
  display: flex; align-items: center;
  padding: 0 6px;
}
.overlay-spacer { flex: 1; }
/* Icône lecture sur continue-card */
.continue-read-overlay {
  position: absolute; inset: 0; z-index: 3;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.35);
  pointer-events: none;
}
.continue-read-icon { font-size: 40px; color: #fff; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }
/* "Albums ajoutés récemment" — même chrome de carte que .book-card/.tome-card (fond blanc,
   bordure, bandeau titre séparé par un filet) plutôt qu'une cover nue + légende flottante,
   pour rester visuellement cohérent avec les grilles d'albums du reste de l'app. */
.scroll-card-tome {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  overflow: visible;
}
.scroll-card-tome .scroll-cover {
  margin-bottom: 0;
  border-radius: var(--radius) var(--radius) 0 0;
}
.scroll-tome-info { padding: 7px 9px; border-top: 1px solid var(--border); }
.scroll-label {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
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

