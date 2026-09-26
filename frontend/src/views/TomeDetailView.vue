<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import MoveTomesModal from '../components/library/MoveTomesModal.vue'
import StarRating from '../components/ui/StarRating.vue'
import { tomesApi } from '../api/tomes'
import { libraryApi } from '../api/library'
import { missingAlbumsApi } from '../api/missingAlbums'
import { useLibraryStore } from '../stores/library'
import { useNotificationStore } from '../stores/notifications'
import { useAuthStore } from '../stores/auth'
import { truncateForReadMore } from '../utils/text'
import { sortTomesByNumber } from '../utils/tomeSort'
import { heroVariantFor, HERO_GRADIENTS_WASH } from '../utils/heroGradient'
import Hint from '../components/ui/Hint.vue'
import AppDialog from '../components/ui/AppDialog.vue'

const route = useRoute()
const router = useRouter()
const notif = useNotificationStore()
const libraryStore = useLibraryStore()
const authStore = useAuthStore()
// library.download retiré : Télécharger a sa propre icône dans la rangée d'actions, plus
// dans ce menu (voir template) — library.convert ajouté : Convertir y a été déplacé (pour
// les formats non-CBZ), auparavant bouton principal à part.
const canMoreMenu = computed(() => ['library.metadata_edit', 'library.rename', 'library.move', 'library.convert', 'library.delete']
  .some(p => authStore.hasPermission(p)))

const tome = ref(null)
const metadata = ref(null)
const lastPage = ref(0)
const seriesName = ref('')
const seriesBedethequeUrl = ref('')
const seriesBedethequeResume = ref('')
const seriesTomes = ref([])
// Albums manquants (suivi Bedetheque) de la série parente — affichés mêlés aux tomes
// possédés dans "Plus dans cette série" (voir siblingDisplayItems), même principe que la
// grille de SeriesDetailView.vue::displayItems.
const missingAlbums = ref([])
// Logo de la série parente — pas de fond photo ici (contrairement à la fiche série) : une
// illustration par ALBUM n'a pas de sens, juste une touche de couleur (voir heroWashStyle)
// et, si fourni sur la série, son logo au-dessus du titre.
const seriesHeroLogoVersion = ref(0)
const loading = ref(true)
const loadError = ref('')
const showEdit = ref(false)
const showConverter = ref(false)
const showRename = ref(false)
const showMove = ref(false)
const openScraperOnOpen = ref(false)

// Menu "⋯" sous la cover (DropdownMenu, voir template).
const showMoreMenu = ref(false)

// Même seuil que le media query mobile (.tome-hero passe en colonne sous 620px) — pilote la
// troncature du résumé (voir resumeDisplay), qui ne s'applique qu'en desktop.
const isDesktop = ref(window.innerWidth > 620)
function updateIsDesktop() { isDesktop.value = window.innerWidth > 620 }
onMounted(() => window.addEventListener('resize', updateIsDesktop))
onUnmounted(() => window.removeEventListener('resize', updateIsDesktop))

function openSearchMetadata() {
  openScraperOnOpen.value = true
  showEdit.value = true
  showMoreMenu.value = false
}

const confirmDelete = ref(false)
const deleting = ref(false)
async function deleteTome() {
  if (!tome.value) return
  deleting.value = true
  try {
    const { data } = await tomesApi.deleteFile(tome.value.id)
    notif.success('Album supprimé')
    await libraryStore.fetchSeries()
    router.push(data.series_deleted ? '/series' : `/series/${tome.value.series_id}`)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deleting.value = false
    confirmDelete.value = false
  }
}

// Même règle que SeriesDetailView.vue (T08 plutôt que T8) — nombre purement numérique
// complété à 2 chiffres, laissé tel quel sinon (ex. "HS", "3.5").
function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  if (/^\d+$/.test(s)) return s.padStart(2, '0')
  return s
}

// Le lien "Lire la suite" (vers la fiche Bedetheque) reste affiché dès qu'une URL existe,
// pas comme rattrapage d'une troncature mais comme lien source.
// Les résumés scrapés avant le correctif du scraper embarquaient parfois le propre lien
// "Lire la suite" de Bedetheque.com en toutes lettres à la fin du texte — retiré ici pour
// les albums déjà enregistrés, en plus du correctif à la source (nouveaux scrapes).
function stripTrailingReadMore(text) {
  if (!text) return text
  return text.replace(/\s*lire\s+la\s+suite\s*$/i, '').trim()
}
// Résumé de la série en repli si l'album n'en a pas — évite une carte vide, même si ça
// décrit la série en général plutôt que cet album précis.
const resumeSource = computed(() => metadata.value?.Summary || seriesBedethequeResume.value || '')
const resumeStripped = computed(() => stripTrailingReadMore(resumeSource.value))
// Tronqué à 300 caractères en desktop (~2 lignes) pour garder "Lire la suite" toujours
// visible à la suite du texte — résumé entier en mobile, où l'espace vertical est moins
// contraint.
const resumeDisplay = computed(() => isDesktop.value ? truncateForReadMore(resumeStripped.value) : resumeStripped.value)
// Genres + étiquettes affichés ensemble dans .hero-chips (voir template).
const hasTagsContent = computed(() => !!tome.value?.user_tags?.length)

// Un album peut avoir plusieurs genres (ex. "Aventure, Humour") — même convention
// multi-valeurs que Writer/Penciller/Publisher.
const genreList = computed(() => (metadata.value?.Genre || '').split(',').map(g => g.trim()).filter(Boolean))

const sortedSeriesTomes = computed(() => sortTomesByNumber(seriesTomes.value))

const currentIndex = computed(() => sortedSeriesTomes.value.findIndex(t => t.id === tome.value?.id))
const prevTome = computed(() => currentIndex.value > 0 ? sortedSeriesTomes.value[currentIndex.value - 1] : null)
const nextTome = computed(() => currentIndex.value < sortedSeriesTomes.value.length - 1 ? sortedSeriesTomes.value[currentIndex.value + 1] : null)

// "Plus dans cette série" — tomes possédés + albums manquants mêlés par numéro, comme la
// grille de SeriesDetailView.vue::displayItems (sortedSeriesTomes ci-dessus reste tomes
// uniquement : utilisé pour la navigation précédent/suivant et le "Tome X / Y" de l'eyebrow,
// où un album manquant n'a pas de sens).
const siblingDisplayItems = computed(() => {
  const tomes = sortedSeriesTomes.value.map(t => ({ ...t, kind: 'tome' }))
  const missing = missingAlbums.value.map(m => ({ ...m, kind: 'missing' }))
  return sortTomesByNumber([...tomes, ...missing])
})

async function loadTome(id) {
  loading.value = true
  loadError.value = ''
  lastPage.value = 0
  // Reset avant rechargement — sinon le logo de l'ex-série reste affiché le temps du
  // chargement, ou reste bloqué si la série de destination échoue à charger (catch juste
  // en dessous).
  seriesHeroLogoVersion.value = 0
  heroLogoError.value = false
  missingAlbums.value = []
  try {
    const [tomeRes, metaRes, progressRes] = await Promise.all([
      tomesApi.getTome(id),
      tomesApi.getMetadata(id),
      tomesApi.getProgress(id).catch(() => null),
    ])
    tome.value = tomeRes.data
    metadata.value = metaRes.data
    lastPage.value = progressRes?.data?.last_page || 0

    if (tome.value.series_id) {
      try {
        const { data } = await libraryApi.getSeriesDetail(tome.value.series_id)
        seriesName.value = data.name
        seriesBedethequeUrl.value = data.bedetheque_url || ''
        seriesBedethequeResume.value = data.bedetheque_resume || ''
        seriesTomes.value = data.tomes || []
        seriesHeroLogoVersion.value = data.hero_logo_version || 0
      } catch { /* ignore */ }
      // Échec silencieux (série non suivie ou sans donnée) — pas une erreur, voir
      // SeriesDetailView.vue::loadSeries pour le même principe.
      try {
        const { data } = await missingAlbumsApi.list()
        missingAlbums.value = data.missing.filter(m => m.series_id === tome.value.series_id)
      } catch {
        missingAlbums.value = []
      }
    }
  } catch (e) {
    tome.value = null
    loadError.value = e.response?.status === 404
      ? "Cet album n'existe plus."
      : "Impossible de charger cet album."
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

// "En cours" — jamais vrai sur un album marqué Lu (voir toggleRead), même si last_page n'est
// techniquement pas à la toute dernière page : Lu prime sur la progression brute, c'est tout
// le sens de la bascule manuelle.
const inProgress = computed(() => {
  const total = tome.value?.page_count
  return !tome.value?.user_is_read && lastPage.value > 0 && total && lastPage.value < total - 1
})
const readProgressPct = computed(() => {
  const total = tome.value?.page_count
  return total ? Math.round((lastPage.value / total) * 100) : 0
})

// Dégradé discret (même variante que la fiche série parente, voir heroGradient.js — d'où
// seriesName plutôt que le titre de l'album) : cohérence visuelle série ↔ tomes sans rien
// avoir à fournir de plus pour l'album lui-même.
const heroWashStyle = computed(() => ({ background: HERO_GRADIENTS_WASH[heroVariantFor(seriesName.value)] }))
// imgError repris de UserAvatar.vue::hasPhoto (voir aussi SeriesDetailView.vue) : le compteur
// de version indique qu'une image a été fournie un jour, pas qu'elle existe encore sur disque
// — retombe sur "pas de logo" plutôt qu'un <img> cassé si le fichier a disparu.
const heroLogoError = ref(false)
watch(() => seriesHeroLogoVersion.value, () => { heroLogoError.value = false })
const heroLogoUrl = computed(() => seriesHeroLogoVersion.value > 0 && tome.value?.series_id && !heroLogoError.value
  ? libraryApi.heroImageUrl(tome.value.series_id, 'logo', seriesHeroLogoVersion.value)
  : null)

// Remplissage en pourcentage plutôt qu'un compte d'étoiles entier — gère nativement les
// demi-étoiles (et n'importe quelle fraction) via un overlay de texte clippé en largeur.
// Même calcul que MetadataDrawer.vue (Note Bedetheque.com), pour un rendu identique.
const bdRatingPct = computed(() => {
  const r = Number(metadata.value?.CommunityRating) || 0
  return Math.max(0, Math.min(100, (r / 5) * 100))
})

// Notation directement depuis la page (auparavant possible seulement via le tiroir
// d'édition) — même clamp/valeur nulle que MetadataDrawer.vue : StarRating émet 0 pour
// "désélectionner", or le backend transforme 0 en 1 (clamp min=1) s'il n'est pas envoyé
// comme null.
async function setUserRating(n) {
  const prev = tome.value.user_rating
  tome.value.user_rating = n
  try {
    await tomesApi.updateUserData(tome.value.id, { user_rating: n || null })
  } catch (e) {
    tome.value.user_rating = prev
    notif.error(e.response?.data?.detail || 'Erreur lors de l\'enregistrement de la note')
  }
}

// Bascule manuelle "Lu" — passe aussi automatiquement à true dès que la lecture atteint 95%
// des pages (routers/tomes.py::save_progress), jamais remis à false tout seul ensuite. Cache
// la barre/le bouton "Reprendre" (voir inProgress) et sort l'album de "Poursuivre la lecture"
// sur l'Accueil (filtré côté backend, /api/tomes/in-progress).
async function toggleRead() {
  const prev = tome.value.user_is_read
  tome.value.user_is_read = !prev
  try {
    await tomesApi.updateUserData(tome.value.id, { is_read: !prev })
    notif.success(!prev ? 'Album marqué comme lu' : 'Album marqué comme non lu')
  } catch (e) {
    tome.value.user_is_read = prev
    notif.error(e.response?.data?.detail || 'Erreur lors de la mise à jour')
  }
}

</script>

<template>
  <AppLayout>
    <div v-if="loading" class="loading-state">
      <span class="loading-pulse">Chargement…</span>
    </div>

    <div v-else-if="loadError" class="error-state">
      <span>{{ loadError }}</span>
      <button class="btn btn-secondary btn-sm" @click="router.push('/series')">Retour aux séries</button>
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
          <Hint :label="prevTome?.title || prevTome?.filename">
            <button class="breadcrumb-chevron" :disabled="!prevTome" @click="router.push(`/tomes/${prevTome.id}`)">‹</button>
          </Hint>
          <Hint :label="nextTome?.title || nextTome?.filename">
            <button class="breadcrumb-chevron" :disabled="!nextTome" @click="router.push(`/tomes/${nextTome.id}`)">›</button>
          </Hint>
        </div>
      </nav>

      <!-- Hero — restructuré selon design-tests/tome-detail-alt.html : cover à taille fixe
           avec progression affichée dessous (au lieu d'étirée sur toute la hauteur), eyebrow
           (logo série + "Tome X sur Y") au-dessus du titre, ligne méta texte (année • pages •
           genre • badge format/taille — genre en texte plutôt qu'en puces cliquables, même
           principe que SeriesDetailView.vue), crédits en 3 colonnes compactes (un album a
           rarement plus d'un nom par rôle, contrairement au cumul sur toute une série), notes
           reléguées sous les actions plutôt qu'à côté du titre. Perd le filtrage direct par
           genre que portaient les anciennes puces (toujours possible depuis la page Albums) et
           le badge de statut de la série parente (déjà visible sur sa propre fiche). -->
      <div class="tome-hero">
        <div class="tome-hero-bg-clip">
          <div class="tome-hero-wash" :style="heroWashStyle"></div>
          <!-- Trame de points façon impression BD — même overlay que SeriesDetailView.vue/
               HomeView.vue (voir hero-bd-replication.md), pour une cohérence des 3 bandeaux
               hero de l'app. -->
          <div class="tome-hero-halftone"></div>
        </div>
        <div class="tome-hero-inner">
          <div class="tome-cover-wrap">
            <div
              class="hero-cover-clip"
              role="button"
              tabindex="0"
              @click="router.push(`/read/${tome.id}`)"
              @keydown.enter="router.push(`/read/${tome.id}`)"
              @keydown.space.prevent="router.push(`/read/${tome.id}`)"
              title="Lire"
            >
              <img
                v-if="tome.cover_url"
                :src="tome.cover_url"
                :alt="tome.title"
                class="hero-cover-img"
              />
              <div v-else class="hero-cover-placeholder">📖</div>
              <div class="hero-cover-read-overlay">
                <SvgIcon name="read" class="cover-read-icon" />
              </div>
            </div>
            <div v-if="inProgress" class="tome-progress">
              <div class="tome-progress-top">
                <span>Page {{ lastPage }} sur {{ tome.page_count }}</span>
                <span>{{ readProgressPct }} %</span>
              </div>
              <div class="tome-progress-track"><div class="tome-progress-fill" :style="{ width: readProgressPct + '%' }"></div></div>
            </div>
          </div>

          <div class="tome-info">
            <div v-if="heroLogoUrl || tome.is_oneshot || tome.number" class="tome-eyebrow">
              <img v-if="heroLogoUrl" :src="heroLogoUrl" :alt="seriesName" class="tome-eyebrow-logo" @error="heroLogoError = true">
              <span v-if="heroLogoUrl" class="tome-eyebrow-sep"></span>
              <span v-if="tome.is_oneshot" class="oneshot-badge">One-shot</span>
              <span v-else-if="tome.number" class="tome-eyebrow-num">Tome {{ fmtNumber(tome.number) }}<template v-if="sortedSeriesTomes.length"> / {{ fmtNumber(sortedSeriesTomes.length) }}</template></span>
            </div>

            <h1 class="hero-title">{{ tome.title || tome.filename }}</h1>

            <div class="tome-meta">
              <template v-if="genreList.length"><span>{{ genreList.join(', ') }}</span><span class="tome-meta-sep">&nbsp;•&nbsp;</span></template>
              <template v-if="metadata?.Year"><span>{{ metadata.Year }}</span><span class="tome-meta-sep">&nbsp;•&nbsp;</span></template>
              <template v-if="tome.page_count"><span>{{ tome.page_count }} pages</span></template>
            </div>

            <div v-if="hasTagsContent" class="hero-chips">
              <span v-for="tag in tome.user_tags" :key="tag" class="chip tag-chip-sm"
                @click="router.push({ path: '/books', query: { tag } })"
              >{{ tag }}</span>
            </div>

            <div v-if="metadata?.Penciller || metadata?.Writer || metadata?.Publisher" class="tome-credits">
              <div v-if="metadata?.Penciller" class="tome-credit-col">
                <span class="tome-credit-label">Dessinateur</span>
                <button class="tome-credit-value" @click="filterByField('penciller', metadata.Penciller)">{{ metadata.Penciller }}</button>
              </div>
              <div v-if="metadata?.Writer" class="tome-credit-col">
                <span class="tome-credit-label">Scénariste</span>
                <button class="tome-credit-value" @click="filterByField('writer', metadata.Writer)">{{ metadata.Writer }}</button>
              </div>
              <div v-if="metadata?.Publisher" class="tome-credit-col">
                <span class="tome-credit-label">Éditeur</span>
                <button class="tome-credit-value" @click="filterByField('publisher', metadata.Publisher)">{{ metadata.Publisher }}</button>
              </div>
            </div>

            <div v-if="resumeSource" class="hero-resume-wrap">
              <p class="hero-resume">{{ resumeDisplay }}<a v-if="metadata.Web || seriesBedethequeUrl" :href="metadata.Web || seriesBedethequeUrl" target="_blank" rel="noopener" class="resume-more-link">Lire la suite</a></p>
            </div>

            <!-- Un seul bouton texte (l'action principale) puis des icônes seules pour le
                 reste — même principe que SeriesDetailView.vue. "Convertir" a rejoint le
                 menu "..." (formats non-CBZ) plutôt que de rester bouton à part. -->
            <div class="hero-actions">
              <button class="hero-btn hero-btn-primary" @click="router.push(`/read/${tome.id}`)">
                <SvgIcon name="read" class="btn-icon-svg" />
                {{ inProgress ? `Reprendre la lecture (${readProgressPct}%)` : 'Lire' }}
              </button>
              <Hint :label="tome.user_is_read ? 'Marquer comme non lu' : 'Marquer comme lu'">
                <button
                  class="hero-btn hero-btn-outline hero-btn-icon"
                  :class="{ 'toolbar-more-btn-active': tome.user_is_read }"
                  @click="toggleRead"
                ><SvgIcon name="square-check" style="font-size:15px" /></button>
              </Hint>
              <Hint v-if="tome.file_format === 'cbz' && authStore.hasPermission('library.metadata_edit')" label="Éditer">
                <button
                  class="hero-btn hero-btn-outline hero-btn-icon"
                  @click="openScraperOnOpen = false; showEdit = true"
                ><SvgIcon name="edit" style="font-size:15px" /></button>
              </Hint>
              <Hint v-if="authStore.hasPermission('library.download')" label="Télécharger">
                <a
                  class="hero-btn hero-btn-outline hero-btn-icon"
                  :href="tomesApi.downloadUrl(tome.id)"
                ><SvgIcon name="download" style="font-size:15px" /></a>
              </Hint>
              <DropdownMenu v-if="canMoreMenu" v-model:open="showMoreMenu" :modal="false">
                <DropdownMenuTrigger as-child>
                  <button title="Plus d'options" aria-label="Plus d'options" class="hero-btn hero-btn-outline hero-btn-icon">
                    <SvgIcon name="more-vertical" style="font-size:13px" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" class="min-w-[200px]">
                  <DropdownMenuItem v-if="authStore.hasPermission('library.metadata_edit')" @select="openSearchMetadata">Rechercher les métadonnées</DropdownMenuItem>
                  <DropdownMenuItem v-if="authStore.hasPermission('library.rename')" @select="showRename = true">Renommer</DropdownMenuItem>
                  <DropdownMenuItem v-if="authStore.hasPermission('library.move')" @select="showMove = true">Déplacer vers une série</DropdownMenuItem>
                  <DropdownMenuItem v-if="tome.file_format !== 'cbz' && authStore.hasPermission('library.convert')" @select="showConverter = true">Convertir</DropdownMenuItem>
                  <template v-if="authStore.hasPermission('library.delete')">
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" @select="confirmDelete = true">Supprimer l'album</DropdownMenuItem>
                  </template>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div class="tome-ratings" v-if="tome.user_rating || metadata?.CommunityRating">
              <div class="tome-rating-block" v-if="tome.user_rating">
                <span class="hero-rating-label">Ma note</span>
                <StarRating :model-value="tome.user_rating" size="1rem" @update:model-value="setUserRating" />
              </div>
              <div class="tome-rating-block" v-if="metadata?.CommunityRating">
                <span class="hero-rating-label">Bedetheque.com</span>
                <span class="bd-stars">
                  <span class="bd-stars-bg">★★★★★</span>
                  <span class="bd-stars-fill" :style="{ width: bdRatingPct + '%' }">★★★★★</span>
                </span>
                <span class="bd-rating-text">{{ Number(metadata.CommunityRating).toFixed(1) }}/5<template v-if="metadata.bedetheque_votes"> ({{ metadata.bedetheque_votes }})</template></span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Genre/étiquettes/série/notes/Publié/Pages/Chemin déjà dans le hero ou supprimés —
           ne montre plus que Ajouté/Modifié/Format/Taille/Résolution. Cartes séparées en
           rangée (.info-cards/.info-card) plutôt qu'une seule bande à colonnes — même
           habillage que les cartes Classification/Public/Note de SeriesDetailView.vue, pour
           une présentation uniforme entre les deux fiches. -->
      <div class="info-cards">
        <div class="info-card">
          <div class="info-card-label">Ajouté</div>
          <div class="info-card-value">{{ formatDate(tome.created_at) }}</div>
        </div>
        <div class="info-card" v-if="tome.updated_at">
          <div class="info-card-label">Modifié</div>
          <div class="info-card-value">{{ formatDate(tome.updated_at) }}</div>
        </div>
        <div class="info-card">
          <div class="info-card-label">Format</div>
          <div class="info-card-value">{{ tome.file_format.toUpperCase() }}</div>
        </div>
        <div class="info-card" v-if="tome.cover_width && tome.cover_height">
          <div class="info-card-label">Résolution</div>
          <div class="info-card-value">{{ tome.cover_width }} × {{ tome.cover_height }}</div>
        </div>
        <!-- Repli sur Taille si la résolution n'est pas encore connue (peuplée seulement au
             premier affichage de la couverture, voir routers/covers.py::get_cover) — évite
             une carte vide pour tous les albums pas encore consultés. -->
        <div class="info-card" v-else>
          <div class="info-card-label">Taille</div>
          <div class="info-card-value">{{ formatSize(tome.file_size) }}</div>
        </div>
      </div>

      <!-- Plus dans cette série — tomes possédés + albums manquants mêlés par numéro (voir
           siblingDisplayItems). Grille de vraies cartes (même principe que .tomes-grid de
           SeriesDetailView.vue) plutôt qu'une rangée de miniatures à défiler — cohérent avec
           le reste de l'app, plus lisible que des vignettes réduites sans cadre. -->
      <div v-if="siblingDisplayItems.length > 1" class="series-siblings">
        <p class="siblings-title">Plus dans « {{ seriesName }} »</p>
        <div class="siblings-grid">
          <template v-for="t in siblingDisplayItems" :key="t.kind + t.id">
            <router-link
              v-if="t.kind === 'tome'"
              :to="`/tomes/${t.id}`"
              :class="['sibling-card', { 'sibling-current': t.id === tome.id }]"
              :title="t.title || t.filename"
            >
              <!-- Cover clippée dans son propre calque (comme .tome-cover-clip sur la page
                   série) — .sibling-card reste overflow:visible, sinon un titre légèrement
                   mal calculé (ex. police pas encore chargée) se fait couper net par la
                   carte elle-même au lieu de l'ellipse "…" du line-clamp. -->
              <div class="sibling-cover">
                <div class="sibling-cover-clip">
                  <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="sibling-cover-img" loading="lazy" />
                  <div v-else class="sibling-cover-placeholder">📖</div>
                </div>
                <span v-if="t.is_oneshot" class="sibling-badge sibling-badge-oneshot">One-shot</span>
                <span v-else-if="t.number" class="sibling-badge">T{{ fmtNumber(t.number) }}</span>
              </div>
              <div class="sibling-info">
                <p class="sibling-title">{{ t.title || t.filename }}</p>
              </div>
            </router-link>
            <!-- Album manquant — juste un repère visuel + lien vers la fiche Bedetheque si
                 connue, même traitement (cover assombrie, badge "Manquant") que la grille de
                 SeriesDetailView.vue. -->
            <a
              v-else
              class="sibling-card sibling-card-missing"
              :href="t.bedetheque_url || null"
              :target="t.bedetheque_url ? '_blank' : null"
              :rel="t.bedetheque_url ? 'noopener' : null"
              :title="(t.title || ('Tome ' + t.number)) + ' — manquant'"
            >
              <div class="sibling-cover">
                <div class="sibling-cover-clip">
                  <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="sibling-cover-img sibling-cover-img-missing" loading="lazy" />
                  <div v-else class="sibling-cover-placeholder">📖</div>
                </div>
                <span v-if="t.number" class="sibling-badge">T{{ fmtNumber(t.number) }}</span>
                <span class="sibling-badge-missing">Manquant</span>
              </div>
              <div class="sibling-info">
                <p class="sibling-title">{{ t.title || ('Tome ' + t.number) }}</p>
              </div>
            </a>
          </template>
        </div>
      </div>
    </main>

    <!-- Edit modal -->
    <MetadataDrawer
      v-if="showEdit && tome"
      :tome="tome"
      :open-scraper="openScraperOnOpen"
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

    <!-- Déplacer vers une autre série -->
    <MoveTomesModal
      v-if="showMove && tome"
      :tome-ids="[tome.id]"
      @close="showMove = false"
      @moved="showMove = false; loadTome(tome.id)"
    />

    <!-- Confirmation suppression -->
    <AppDialog v-if="confirmDelete" title="Supprimer l'album ?" @close="confirmDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer l'album ?</p>
        <p class="confirm-desc">
          <strong>{{ tome.title || tome.filename }}</strong> sera supprimé définitivement du disque.
        </p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteTome" :disabled="deleting">
            {{ deleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </AppDialog>
  </AppLayout>
</template>

<style scoped>
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.loading-state {
  display: flex; align-items: center; justify-content: center;
  min-height: 240px; color: var(--muted); font-size: 0.9rem;
}
.loading-pulse { animation: pulse 1.4s ease-in-out infinite; }

.error-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; min-height: 240px; color: var(--muted); font-size: 0.9rem;
}

.detail-main {
  flex: 1;
  padding: 20px;
}

/* Breadcrumb */
.breadcrumb {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.875rem; color: var(--muted); margin-bottom: 16px;
  flex-wrap: wrap;
}
.breadcrumb-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--vermilion); font-size: 0.875rem; font-family: var(--font);
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

/* Restructuré selon design-tests/tome-detail-alt.html : cover à taille fixe (plus étirée sur
   toute la hauteur) avec progression affichée dessous, eyebrow (logo série + "Tome X sur Y")
   au-dessus du titre, ligne méta texte, crédits en 3 colonnes compactes, notes sous les
   actions. Pas de fond (ni dégradé dérivé de la cover, ni couleur unie) sur la carte
   elle-même — juste la touche de couleur de la série parente (voir heroWashStyle). */
.tome-hero {
  position: relative;
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  /* --light (pas --surface) : même fond que .series-hero sur la page série, pour que
     .hero-btn-outline (fond --surface, blanc) contraste dessus au lieu de s'y fondre. */
  background: var(--light);
  box-shadow: var(--shadow-sm);
}
/* Dégradé discret (jamais de fond photo pour un album, voir heroWashStyle) — clippé dans son
   propre calque plutôt que sur .tome-hero directement : un overflow:hidden ici aurait aussi
   coupé le menu "..." (position:absolute), qui dépasse volontairement de la carte pour
   s'ouvrir par-dessus le contenu en dessous. */
.tome-hero-bg-clip { position: absolute; inset: 0; border-radius: var(--radius-lg); overflow: hidden; }
.tome-hero-wash { position: absolute; inset: 0; opacity: .5; }
/* Trame de points (halftone) — voir SeriesDetailView.vue::.series-hero-halftone, mêmes
   réglages (point 1.5px/1.6px, grille 8px, opacity .25 en plus des 45% de color-mix). */
.tome-hero-halftone {
  position: absolute; inset: 0;
  pointer-events: none;
  opacity: 0.25;
  mix-blend-mode: multiply;
  background-image: radial-gradient(color-mix(in srgb, var(--vermilion) 45%, transparent) 1.5px, transparent 1.6px);
  background-size: 8px 8px;
}
.tome-hero-inner { position: relative; display: flex; gap: 36px; padding: 40px; align-items: flex-start; }

/* Cover à taille fixe (plus stretch pleine hauteur) + progression de lecture dessous. */
/* Agrandie (220 → 270px) pour se rapprocher du bas de la rangée d'actions — reste une
   taille fixe plutôt qu'un calque étiré pour matcher exactement ce bord (voir
   .tome-hero-inner ci-dessous, align-items:flex-start) : un étirement pixel-parfait
   dépendrait de la hauteur du texte (titre/crédits/résumé, variable par album) et
   réintroduirait le conflit qui avait fait déplacer la barre de progression en overlay sur
   la cover avant l'application de la maquette — non souhaité ici, elle reste sous la cover. */
.tome-cover-wrap { flex: none; width: 270px; }
.hero-cover-clip {
  width: 100%; aspect-ratio: 0.71;
  border-radius: var(--radius-sm); overflow: hidden;
  position: relative; cursor: pointer;
  box-shadow: var(--shadow-lg);
  transition: transform 0.18s;
}
.hero-cover-clip:hover { transform: translateY(-2px); }
.hero-cover-read-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.18s;
}
.hero-cover-clip:hover .hero-cover-read-overlay { opacity: 1; }
.cover-read-icon {
  font-size: 40px;
  color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}
.hero-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hero-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 3rem; background: var(--light);
}
/* Progression sous la cover (plus en overlay sur son bas) — texte "Page X sur Y" + pourcentage,
   puis piste. Uniquement en lecture en cours (voir inProgress) ; le pourcentage reste aussi
   dans le libellé du bouton "Reprendre la lecture". */
.tome-progress { margin-top: 12px; }
.tome-progress-top { display: flex; justify-content: space-between; font: 600 0.78rem var(--font); color: var(--text); opacity: .75; margin-bottom: 7px; }
.tome-progress-track { height: 6px; border-radius: 3px; background: rgba(30,42,66,.14); overflow: hidden; }
.tome-progress-fill { height: 100%; border-radius: 3px; background: var(--vermilion); }

.tome-info { position: relative; flex: 1; min-width: 0; }

/* Eyebrow — logo de la série parente (si fourni) + numéro d'album, au-dessus du titre. */
.tome-eyebrow { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.tome-eyebrow-logo { height: 44px; width: auto; max-width: 200px; display: block; }
.tome-eyebrow-sep { width: 1px; height: 14px; background: var(--border); flex-shrink: 0; }
.tome-eyebrow-num { font: 600 0.68rem var(--font); letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }

/* Bebas Neue, capitales — poids 400 uniquement disponible dans cette police. */
.hero-title {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: clamp(1.8rem, 3.2vw, 2.5rem); line-height: 1; letter-spacing: .01em;
  color: var(--text); margin-bottom: 14px;
  text-wrap: balance;
}
.oneshot-badge {
  display: inline-flex; align-items: center;
  padding: 1px 8px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 700;
  color: #fff; background: var(--vermilion);
}

/* Ligne méta texte (genre • année • pages • badge format) — genre en texte plutôt qu'en puces
   cliquables, même principe que .series-count (SeriesDetailView.vue). Flux inline (pas de
   flex/gap) comme .series-count : l'espacement vient uniquement des &nbsp; autour du "•" —
   un gap flex en plus faisait doublon et espaçait trop la ligne. */
/* Un peu moins foncé que var(--text) pur — mélange plutôt qu'une opacité sur toute la ligne,
   qui aurait aussi atténué le séparateur et le badge déjà réglés indépendamment. */
.tome-meta { font-size: 0.875rem; font-weight: 600; color: color-mix(in srgb, var(--text) 85%, var(--muted) 15%); margin-bottom: 16px; }
/* Séparateur discret : poids normal (pas hérité en gras) et opacité réduite, pour rester en
   retrait du texte autour plutôt que ressortir comme un point plein — même traitement que
   .series-info-sep (SeriesDetailView.vue). */
.tome-meta-sep { color: var(--muted); font-weight: 400; opacity: .45; }

/* Crédits en colonnes compactes plutôt qu'en lignes pleine largeur (voir la fiche série) :
   un album précis a rarement plus d'un ou deux noms par rôle, contrairement au cumul sur
   toute une série. */
.tome-credits { display: flex; gap: 32px; flex-wrap: wrap; margin-bottom: 16px; }
.tome-credit-col { min-width: 120px; display: flex; flex-direction: column; gap: 3px; }
/* Libellé/valeur — même recette que .series-meta-label/.series-meta-link (SeriesDetailView.vue) :
   texte tel quel (pas de majuscules forcées, pas d'espacement des lettres), graisse normale
   pour la valeur cliquable. */
.tome-credit-label { font-size: 0.8125rem; color: var(--muted); }
.tome-credit-value {
  background: none; border: none; padding: 0; cursor: pointer; text-align: left;
  font-size: 0.8125rem; font-family: var(--font); font-weight: 700; color: var(--vermilion);
}
.tome-credit-value:hover { text-decoration: underline; }

.tome-ratings { display: flex; flex-wrap: wrap; gap: 12px 28px; margin-top: 6px; }
.tome-rating-block { display: flex; flex-direction: column; gap: 5px; }
.hero-rating-label { font: 600 0.68rem var(--font); letter-spacing: .16em; text-transform: uppercase; color: var(--muted); }

.hero-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.hero-resume-wrap { max-width: 560px; margin-bottom: 16px; }
.hero-resume {
  font-size: 0.85rem; color: var(--text); line-height: 1.5; margin: 0;
}

.hero-actions { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.hero-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 12px;
  font-family: var(--font); font-size: 0.78rem; font-weight: 500; line-height: 1;
  text-transform: uppercase;
  border-radius: var(--radius-sm);
  cursor: pointer; border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.hero-btn-primary { background: var(--vermilion); color: #fff; }
.hero-btn-primary:hover { background: var(--vermilion-dark); }
/* --surface (blanc) contre le fond --light de .tome-hero — même combo que .hero-btn-outline
   sur la page série (fond --surface était identique à .tome-hero avant ce correctif, donc
   invisible : seule la bordure se voyait). */
.hero-btn-outline { background: var(--surface); color: var(--text); border-color: var(--border); }
.hero-btn-outline:hover { background: var(--light); }
.hero-btn-icon { padding: 6px 8px; }
.btn-icon-svg { font-size: 11px; vertical-align: middle; margin-right: 2px; }
/* État "coché" du bouton icône Lu — même recette que .toolbar-more-btn-active
   (SeriesDetailView.vue) pour rester visuellement cohérent entre les deux fiches. */
.toolbar-more-btn-active { border-color: var(--vermilion); color: var(--vermilion); background: var(--vermilion-light); }


/* Confirmation de suppression */
.confirm-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  padding: 24px; max-width: 400px; width: 100%;
}
.confirm-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.confirm-desc { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.confirm-btns { display: flex; justify-content: flex-end; gap: 8px; }

/* Infos fichier — une seule carte, chaque info séparée par un léger trait vertical plutôt
   que 4 cartes distinctes (même traitement que SeriesDetailView.vue, voir plus haut). */
.info-cards {
  display: flex; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow-sm); margin-bottom: 20px;
}
.info-card { flex: 1; min-width: 160px; position: relative; padding: 14px 18px; }
/* Trait vertical qui ne touche ni le haut ni le bas de la carte — atténue la séparation
   entre les infos tout en gardant une seule carte visuellement unifiée. */
.info-card:not(:last-child)::after {
  content: '';
  position: absolute; top: 12px; bottom: 12px; right: 0;
  width: 1px; background: var(--border);
}
.info-card-label { font: 600 0.68rem var(--font); letter-spacing: .16em; text-transform: uppercase; color: var(--muted); margin-bottom: 5px; }
.info-card-value { font: 700 0.9375rem var(--font); color: var(--text); }
.chip {
  font-size: 0.72rem; font-weight: 700;
  padding: 2px 8px; border-radius: 4px;
}

.resume-more-link {
  margin-left: 4px;
  font-size: 0.8125rem; font-weight: 600;
  color: var(--vermilion); white-space: nowrap;
}
.resume-more-link:hover { text-decoration: underline; }

/* Note Bedetheque — lecture seule, remplissage fractionnaire (demi-étoiles comprises) via
   un overlay coloré clippé en largeur au pourcentage de la note, par-dessus une rangée
   d'étoiles grisées de même taille. Détails (note chiffrée + votants) affichés sous les 2
   lignes d'étoiles plutôt qu'à côté, pour que les étoiles de "Ma note" et "Bedetheque.com"
   restent alignées verticalement. font-size doit rester identique au "size" du StarRating
   de "Ma note" (1rem, voir template) — un écart ici redonnait des étoiles visiblement plus
   grosses côté Bedetheque, déjà corrigé une fois par le passé. */
.bd-stars { position: relative; display: inline-block; font-size: 1rem; line-height: 1; white-space: nowrap; }
.bd-stars-bg { color: var(--star-empty); }
.bd-stars-fill {
  position: absolute; top: 0; left: 0; overflow: hidden;
  color: var(--star-filled);
}
.bd-rating-text { font-size: 0.78rem; color: var(--muted); }
.tag-chip-sm { background: none; color: var(--muted); border: 1px solid var(--border); cursor: pointer; }
.tag-chip-sm:hover { background: var(--light); }

/* Plus dans cette série — rangée horizontale des autres tomes, réutilise les tomes déjà
   chargés pour la navigation précédent/suivant (sortedSeriesTomes). */
.series-siblings { margin-top: 24px; margin-bottom: 20px; }
/* Même recette que .section-title (HomeView.vue) — la police d'affichage majuscule
   (Bebas Neue) tranchait avec tous les autres titres de section de l'app. */
.siblings-title { font-size: 1rem; font-weight: 600; color: var(--text); margin-bottom: 14px; }
/* Grille — mêmes paliers responsive que .tomes-grid (SeriesDetailView.vue). */
.siblings-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .siblings-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .siblings-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .siblings-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .siblings-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .siblings-grid { grid-template-columns: repeat(8, 1fr); } }
/* Carte complète (cover + titre), même habillage que .tome-card (SeriesDetailView.vue),
   au même détail près (cover clippée dans son propre calque, overflow:visible sur la carte
   elle-même — voir commentaire dans le template) — simplifiée : pas de sélection multiple
   ni de menu au survol, juste une carte cliquable (ce widget est un aperçu/une navigation,
   pas un outil de gestion). */
.sibling-card {
  display: block;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
  overflow: visible; box-shadow: var(--shadow-sm); text-decoration: none;
  position: relative;
  transition: box-shadow 0.18s, transform 0.18s, border-color 0.15s;
}
.sibling-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
.sibling-current { border-color: var(--primary); box-shadow: 0 0 0 1.5px var(--primary); }
.sibling-cover { aspect-ratio: 0.71; position: relative; }
.sibling-cover-clip {
  position: absolute; inset: 0; overflow: hidden;
  border-radius: var(--radius) var(--radius) 0 0;
  background: var(--light);
}
.sibling-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; }
.sibling-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 2rem; color: var(--placeholder);
}
.sibling-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}
.sibling-badge-oneshot { background: var(--vermilion); color: #fff; }
.sibling-info { padding: 8px 10px; border-top: 1px solid var(--border); }
.sibling-title {
  margin: 0;
  font-size: 0.8125rem; font-weight: 600; color: var(--text); line-height: 1.3;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
/* Album manquant — cover assombrie/grisée + badge dédié, même principe que
   .tome-card-missing (SeriesDetailView.vue) mais sans bouton d'upload (juste un repère
   visuel ici, pas d'action d'ajout depuis cette page). */
.sibling-card-missing, .sibling-card-missing:hover { text-decoration: none; }
.sibling-cover-img-missing { filter: grayscale(70%); opacity: 0.55; }
.sibling-badge-missing {
  position: absolute; bottom: 6px; left: 6px; z-index: 3;
  padding: 1px 6px;
  background: var(--warning-bg); color: var(--warning-text, var(--warning));
  font-size: 0.66rem; font-weight: 700; border-radius: 4px;
}

@media (max-width: 620px) {
  /* En dessous de 620px, cover et infos s'empilent — cover centrée à largeur fixe et réduite. */
  .tome-hero-inner { flex-direction: column; align-items: center; padding: 24px; }
  .tome-cover-wrap { width: 160px; align-self: center; }
  .tome-info { align-self: stretch; }
  .hero-title { font-size: 1.4rem; }
}
</style>
