<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import ConverterModal from '../components/converter/ConverterModal.vue'
import SeriesMetadataModal from '../components/metadata/SeriesMetadataModal.vue'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import SeriesEnrichModal from '../components/metadata/SeriesEnrichModal.vue'
import RenameModal from '../components/rename/RenameModal.vue'
import CoverPickerModal from '../components/library/CoverPickerModal.vue'
import MoveTomesModal from '../components/library/MoveTomesModal.vue'
import BulkEditTomesModal from '../components/metadata/BulkEditTomesModal.vue'
import MissingAlbumUploadModal from '../components/missingAlbums/MissingAlbumUploadModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { libraryApi } from '../api/library'
import { tomesApi } from '../api/tomes'
import { missingAlbumsApi } from '../api/missingAlbums'
import { useNotificationStore } from '../stores/notifications'
import { useLibraryStore } from '../stores/library'
import { useAuthStore } from '../stores/auth'
import { sortTomesByNumber } from '../utils/tomeSort'
import { truncateForReadMore } from '../utils/text'
import { heroVariantFor, HERO_GRADIENTS_WIDE } from '../utils/heroGradient'

const notif = useNotificationStore()
const libraryStore = useLibraryStore()
const authStore = useAuthStore()
// library.download retiré : Télécharger a sa propre icône dans la rangée d'actions, plus
// dans ce menu (voir template).
const canSeriesMoreMenu = computed(() => ['library.convert', 'library.rename', 'library.metadata_edit', 'library.delete']
  .some(p => authStore.hasPermission(p)))
const canTomeMoreMenu = computed(() => ['library.metadata_edit', 'library.move', 'library.download', 'library.delete']
  .some(p => authStore.hasPermission(p)))

const route = useRoute()
const router = useRouter()
const series = ref(null)
const loading = ref(true)

const seriesList = computed(() => libraryStore.series || [])
const currentIndex = computed(() => seriesList.value.findIndex(s => s.id === series.value?.id))
const prevSeries = computed(() => currentIndex.value > 0 ? seriesList.value[currentIndex.value - 1] : null)
const nextSeries = computed(() => currentIndex.value < seriesList.value.length - 1 ? seriesList.value[currentIndex.value + 1] : null)

// "Séries similaires" / "Du même scénariste" / "Du même dessinateur" — calculées côté client
// à partir de libraryStore.series (déjà chargée pour la navigation précédent/suivant
// ci-dessus, aucun nouvel appel réseau), sur le modèle de topGenres dans HomeView.vue.
// Séries masquées exclues, série courante exclue. "Similaires" triées par nombre de genres
// en commun décroissant (une série qui partage 2 genres remonte avant une qui n'en partage
// qu'1) ; les deux sections auteur triées alphabétiquement, un seul champ ne justifiant pas
// ce tri par pertinence.
// Casse/accents pas toujours cohérents entre fichiers ("Humour" vs "humour") — comparaison
// insensible à la casse/accents (même principe que norm() dans BooksView.vue), sinon des
// correspondances évidentes passeraient à la trappe pour une simple différence de saisie.
function norm(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase() }

function otherSeriesSharing(field, exclude) {
  const mine = new Set((series.value?.[field] || []).map(norm))
  if (!mine.size) return []
  return seriesList.value
    .filter(s => s.id !== series.value.id && !s.hidden && !exclude.has(s.id) && (s[field] || []).some(v => mine.has(norm(v))))
}
// Dédupliqué entre les 3 sections (par ordre de priorité genre → scénariste → dessinateur) :
// une série qui partage plusieurs critères à la fois ne doit apparaître qu'une fois, dans la
// section la plus pertinente, pas répétée trois fois de suite.
const similarSeries = computed(() => {
  const mine = new Set((series.value?.genres || []).map(norm))
  if (!mine.size) return []
  return seriesList.value
    .filter(s => s.id !== series.value.id && !s.hidden)
    .map(s => ({ s, shared: (s.genres || []).filter(g => mine.has(norm(g))).length }))
    .filter(x => x.shared > 0)
    .sort((a, b) => b.shared - a.shared || a.s.name.localeCompare(b.s.name, undefined, { sensitivity: 'base' }))
    .map(x => x.s)
    .slice(0, 16)
})
const sameWriterSeries = computed(() => {
  const exclude = new Set(similarSeries.value.map(s => s.id))
  return otherSeriesSharing('writers', exclude)
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })).slice(0, 16)
})
const samePencillerSeries = computed(() => {
  const exclude = new Set([...similarSeries.value, ...sameWriterSeries.value].map(s => s.id))
  return otherSeriesSharing('pencillers', exclude)
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })).slice(0, 16)
})

function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  if (/^\d+$/.test(s)) return s.padStart(2, '0')
  return s
}

const sortedTomes = computed(() => sortTomesByNumber(series.value?.tomes))

// Résumé affiché en entier — assez de place désormais. Le lien "Lire la suite" reste
// affiché (vers la fiche Bedetheque) dès qu'une URL existe, pas comme rattrapage d'une
// troncature mais comme lien source.
// Résumés scrapés avant le correctif du scraper : embarquaient parfois le propre lien
// "Lire la suite" de Bedetheque.com en toutes lettres à la fin du texte — retiré ici pour
// les séries déjà enregistrées, en plus du correctif à la source (nouveaux scrapes).
function stripTrailingReadMore(text) {
  if (!text) return text
  return text.replace(/\s*lire\s+la\s+suite\s*$/i, '').trim()
}

const resumeStripped = computed(() => stripTrailingReadMore(series.value?.bedetheque_resume))
// Tronqué à 181 caractères (~2 lignes), desktop ET mobile — même logique des deux côtés
// depuis que le résumé plein allongeait la page mobile sans raison de garder ce cas à part
// (contrairement au fond du hero en 4:1, qui ne s'applique qu'en desktop, la contrainte de
// hauteur du résumé lui-même n'a rien de spécifique au desktop).
const resumeDisplay = computed(() => truncateForReadMore(resumeStripped.value, 181))

// "1972 – 2019" pour une série finie, "depuis 1972" pour une série en cours (même logique
// que design-tests/series-detail-alt-no-art.html) — repliée sur une seule année si toutes
// les Metadata.Year connues des tomes coïncident (voir year_start/year_end, get_series).
const yearsLabel = computed(() => {
  const s = series.value
  if (!s?.year_start) return null
  if (s.bedetheque_status === 'Série en cours') return `depuis ${s.year_start}`
  if (!s.year_end || s.year_end === s.year_start) return `${s.year_start}`
  return `${s.year_start} – ${s.year_end}`
})

// Bandeau "hero" — fond illustré si fourni (voir SeriesMetadataModal.vue), sinon dégradé
// calculé à partir du nom (voir utils/heroGradient.js) : testé et validé dans design-tests/
// avant intégration ici.
const heroVariant = computed(() => heroVariantFor(series.value?.name))
// Le compteur de version indique qu'une image a été fournie un jour, pas qu'elle existe
// encore sur disque (ex. fichier supprimé manuellement sur le serveur, ou compteur laissé
// désynchronisé par un test) — un GET sur un fichier manquant renvoie 404. imgError (repris
// du même filet de sécurité que UserAvatar.vue::hasPhoto) retombe alors sur le dégradé/titre
// texte au lieu d'un cadre cassé/vide. Réinitialisé à chaque changement de série.
const heroBgError = ref(false)
const heroLogoError = ref(false)
const hasHeroBackground = computed(() => series.value?.hero_background_version > 0 && !heroBgError.value)
const heroBgImageUrl = computed(() => series.value?.hero_background_version > 0
  ? libraryApi.heroImageUrl(series.value.id, 'background', series.value.hero_background_version)
  : null)
const heroBgStyle = computed(() => {
  if (hasHeroBackground.value) {
    return { backgroundImage: `url(${heroBgImageUrl.value})` }
  }
  return { background: `${HERO_GRADIENTS_WIDE[heroVariant.value]}, var(--surface-raised)` }
})
const heroLogoUrl = computed(() => series.value?.hero_logo_version > 0 && !heroLogoError.value
  ? libraryApi.heroImageUrl(series.value.id, 'logo', series.value.hero_logo_version)
  : null)
// Re-tente le chargement dès qu'un nouvel upload change le compteur de version (modale de
// métadonnées) — sans ça, un échec resterait mémorisé même après un remplacement réussi.
watch(() => series.value?.hero_background_version, () => { heroBgError.value = false })
watch(() => series.value?.hero_logo_version, () => { heroLogoError.value = false })

// Albums manquants (suivi Bedetheque) affichés à leur place dans la grille, mêlés aux
// tomes possédés par numéro — plutôt qu'un onglet séparé, peu pertinent pour la majorité
// des séries (non suivies, ou sans aucun album manquant).
const missingAlbums = ref([])
const displayItems = computed(() => {
  const tomes = (series.value?.tomes || []).map(t => ({ ...t, kind: 'tome' }))
  const missing = missingAlbums.value.map(m => ({ ...m, kind: 'missing' }))
  return sortTomesByNumber([...tomes, ...missing])
})

const showConverter = ref(false)
const showSeriesMeta = ref(false)
const showTomeMeta = ref(false)
const showEnrich = ref(false)
const showRename = ref(false)
const convertTomeId = ref(null)
const selectedTome = ref(null)

async function loadSeries(id) {
  // Une navigation plus récente (route.params.id qui change avant que CET appel ne
  // revienne — ex. clic rapide d'une série à l'autre depuis "Séries similaires") ne doit
  // jamais laisser une réponse obsolète afficher les données d'une série déjà quittée sous
  // l'URL d'une autre. route.params.id reste la source de vérité de "quelle série veut-on
  // voir maintenant", vérifiée après chaque await plutôt qu'une seule fois au début.
  const isStale = () => String(route.params.id) !== String(id)
  loading.value = true
  heroBgError.value = false
  heroLogoError.value = false
  try {
    const { data } = await libraryApi.getSeriesDetail(id)
    if (isStale()) return
    series.value = data
  } finally {
    if (!isStale()) loading.value = false
  }
  // Ne bloque pas l'affichage des tomes — chargé séparément, échec silencieux (série non
  // suivie ou sans donnée n'est pas une erreur).
  try {
    const { data } = await missingAlbumsApi.list()
    if (isStale()) return
    missingAlbums.value = data.missing.filter(m => m.series_id === Number(id))
  } catch {
    if (!isStale()) missingAlbums.value = []
  }
}

onMounted(async () => {
  if (!libraryStore.series.length) await libraryStore.fetchSeries()
  await loadSeries(route.params.id)
})

const uploadAlbum = ref(null)
function openMissingUpload(entry) { uploadAlbum.value = entry }
async function onAlbumUploaded() {
  uploadAlbum.value = null
  await loadSeries(route.params.id)
}

watch(() => route.params.id, (id) => { if (id) loadSeries(id) })

const openScraperOnOpen = ref(false)

function onEditTome(tome) {
  selectedTome.value = tome
  openScraperOnOpen.value = false
  showTomeMeta.value = true
}

function onSearchTomeMetadata(tome) {
  selectedTome.value = tome
  openScraperOnOpen.value = true
  showTomeMeta.value = true
}

function onConvert(tome) {
  convertTomeId.value = tome.id
  showConverter.value = true
}

async function toggleSeriesHidden() {
  const { data } = await libraryApi.toggleSeriesHidden(series.value.id)
  series.value.hidden = data.hidden
  notif.success(data.hidden ? 'Série masquée' : 'Série affichée')
  libraryStore.fetchSeries()
}

const showCoverPicker = ref(false)

// Menu « ... » secondaire de la barre d'actions — actions moins courantes (voir
// action-toolbar plus bas), différentes selon qu'on agit sur toute la série ou sur la
// sélection en cours. Auparavant dupliqué entre ce menu (sur la cover) et la rangée de
// boutons toujours visible ; fusionné en une seule barre d'actions.
const showActionsMenu = ref(false)
const actionsMenuLeft = ref(false)
const actionsMenuRef = ref(null)
const confirmDeleteSeries = ref(false)
const deletingSeries = ref(false)
const confirmDownload = ref(false)

function downloadSeries() {
  window.location.href = tomesApi.downloadBulkUrl(sortedTomes.value.map(t => t.id))
  confirmDownload.value = false
}

function toggleActionsMenu(e) {
  actionsMenuLeft.value = e.clientX > window.innerWidth * 0.66
  showActionsMenu.value = !showActionsMenu.value
}
function onClickOutsideActionsMenu(e) {
  if (showActionsMenu.value && actionsMenuRef.value && !actionsMenuRef.value.contains(e.target)) {
    showActionsMenu.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutsideActionsMenu))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutsideActionsMenu))

async function deleteSeries() {
  deletingSeries.value = true
  try {
    await libraryApi.deleteSeries(series.value.id)
    notif.success('Série supprimée')
    await libraryStore.fetchSeries()
    router.push('/series')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deletingSeries.value = false
    confirmDeleteSeries.value = false
  }
}

function onCoverUpdated({ cover_url, cover_tome_id }) {
  series.value.cover_url = cover_url
  series.value.cover_tome_id = cover_tome_id
  // Mettre à jour le store pour que la page Séries reflète le changement
  const s = libraryStore.series.find(s => s.id === series.value.id)
  if (s) s.cover_url = cover_url
}

// Sélection multiple — même mécanique que les pages Séries/Albums, pour déplacer, éditer
// ou supprimer plusieurs albums de cette série en une fois.
const selectedIds = reactive(new Set())
const showMove = ref(false)
const showBulkEdit = ref(false)
const confirmBulkDelete = ref(false)
const bulkDeleting = ref(false)
const moveTomeIds = ref([])

function toggleSelect(tomeId) {
  if (selectedIds.has(tomeId)) selectedIds.delete(tomeId)
  else selectedIds.add(tomeId)
}
function clearSelection() { selectedIds.clear() }

// Échap désélectionne — mais seulement si aucune popup n'est ouverte au-dessus (chacune gère
// déjà son propre Échap pour se refermer en premier, ex. MetadataDrawer/MoveTomesModal).
function onSelectionEscape(e) {
  if (e.key !== 'Escape' || !selectedIds.size) return
  if (showTomeMeta.value || showMove.value || showBulkEdit.value || confirmBulkDelete.value || confirmDeleteTome.value || openMenuId.value !== null || showSelectionMenu.value) return
  clearSelection()
}
onMounted(() => window.addEventListener('keydown', onSelectionEscape))
onUnmounted(() => window.removeEventListener('keydown', onSelectionEscape))

function openMoveSelection() {
  moveTomeIds.value = [...selectedIds]
  showMove.value = true
}

// Menu « ... » secondaire de la barre de sélection (Déplacer/Supprimer) — état séparé de
// celui de la barre d'actions série (showActionsMenu), les deux pouvant coexister dans le DOM.
const showSelectionMenu = ref(false)
const selectionMenuLeft = ref(false)
const selectionMenuRef = ref(null)
function toggleSelectionMenu(e) {
  selectionMenuLeft.value = e.clientX > window.innerWidth * 0.66
  showSelectionMenu.value = !showSelectionMenu.value
}
function onClickOutsideSelectionMenu(e) {
  if (showSelectionMenu.value && selectionMenuRef.value && !selectionMenuRef.value.contains(e.target)) {
    showSelectionMenu.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutsideSelectionMenu))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutsideSelectionMenu))

// Après un déplacement (lot ou individuel), la série courante peut avoir été supprimée si
// elle vient d'être vidée de son dernier album — dans ce cas on repart vers /series plutôt
// que de recharger une page qui n'existe plus.
async function onMoved(data) {
  clearSelection()
  moveTomeIds.value = []
  await libraryStore.fetchSeries()
  if (data?.deleted_series?.includes(series.value.name)) {
    router.push('/series')
    return
  }
  await loadSeries(route.params.id)
}

async function bulkDelete() {
  bulkDeleting.value = true
  try {
    const { data } = await tomesApi.deleteBulk([...selectedIds])
    if (data.errors?.length) notif.error(`${data.errors.length} erreur(s) — ${data.errors[0]}`)
    else notif.success(`${data.ok} album(s) supprimé(s)`)
    clearSelection()
    await libraryStore.fetchSeries()
    if (data.deleted_series?.includes(series.value.name)) {
      router.push('/series')
      return
    }
    await loadSeries(route.params.id)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    bulkDeleting.value = false
    confirmBulkDelete.value = false
  }
}

// Menu « plus d'options » (3 points) par album — déplacer/éditer/supprimer un seul album
// sans passer par la sélection multiple ni ouvrir le tiroir d'édition complet.
const openMenuId = ref(null)
const menuLeft = ref(false)
const confirmDeleteTome = ref(null)
const deletingSingle = ref(false)

function toggleTomeMenu(e, tomeId) {
  menuLeft.value = e.clientX > window.innerWidth * 0.66
  openMenuId.value = openMenuId.value === tomeId ? null : tomeId
}
function onClickOutsideMenu(e) {
  if (openMenuId.value !== null && !e.target.closest('.tome-more-wrap')) {
    openMenuId.value = null
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutsideMenu))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutsideMenu))

function openMoveSingle(tome) {
  moveTomeIds.value = [tome.id]
  showMove.value = true
}

async function deleteSingleTome() {
  if (!confirmDeleteTome.value) return
  deletingSingle.value = true
  try {
    const { data } = await tomesApi.deleteFile(confirmDeleteTome.value.id)
    notif.success('Album supprimé')
    await libraryStore.fetchSeries()
    if (data.series_deleted) {
      router.push('/series')
    } else {
      await loadSeries(route.params.id)
    }
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deletingSingle.value = false
    confirmDeleteTome.value = null
  }
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

      <!-- Series header — bandeau "hero" : fond illustré fourni (SeriesMetadataModal.vue) ou
           dégradé de repli (heroGradient.js), testé et validé dans design-tests/ avant
           intégration. Le picker de couverture (cover_url) reste accessible depuis le menu
           "..." ("Modifier la miniature") plutôt que sous forme de vignette toujours visible
           ici — la vignette apparaît déjà partout ailleurs (grilles Séries/Accueil). -->
      <section class="series-hero">
        <div class="series-hero-bg-clip">
          <!-- Sonde invisible : background-image (CSS) n'a pas d'événement d'erreur natif,
               donc on charge la même URL dans un <img> caché pour détecter un 404 (compteur
               de version désynchronisé du fichier réel, voir hasHeroBackground) et retomber
               sur le dégradé. -->
          <img v-if="heroBgImageUrl" :key="heroBgImageUrl" :src="heroBgImageUrl" alt="" aria-hidden="true" style="position:absolute;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none" @error="heroBgError = true">
          <div class="series-hero-bg" :style="heroBgStyle"></div>
          <div class="series-hero-fade-h" :class="{ 'series-hero-fade--soft': !hasHeroBackground }"></div>
          <div class="series-hero-fade-v" :class="{ 'series-hero-fade--soft': !hasHeroBackground }"></div>
          <!-- Trame de points façon impression BD (test) — voir hero-bd-replication.md.
               mix-blend-mode:multiply fonce le fond dessous au lieu de le recouvrir, donne
               un effet "papier imprimé" discret par-dessus le fond/dégradé, avec ou sans
               image fournie. -->
          <div class="series-hero-halftone"></div>
        </div>
        <div class="series-hero-inner">
          <div v-if="heroLogoUrl" class="series-hero-logo-box">
            <img :src="heroLogoUrl" :alt="series.name" class="series-hero-logo" @error="heroLogoError = true">
          </div>
          <h1 v-else class="series-title">{{ series.name }}</h1>

          <!-- Genre(s) • années • tomes • statut, en une ligne de texte plutôt qu'en badges
               cliquables — voir design-tests/series-detail-alt-no-art.html. Perd le filtrage
               direct par genre que portaient les anciens chips (toujours possible depuis la
               page Albums elle-même). -->
          <p class="series-count">
            <template v-if="series.genres?.length">{{ series.genres.join(', ') }}<span class="series-info-sep">&nbsp;•&nbsp;</span></template>
            <template v-if="yearsLabel">{{ yearsLabel }}<span class="series-info-sep">&nbsp;•&nbsp;</span></template>
            <span class="mono-num">{{ series.tome_count }}</span> tome{{ series.tome_count !== 1 ? 's' : '' }}
            <span v-if="series.bedetheque_status" class="bd-status-badge">{{ series.bedetheque_status }}</span>
          </p>

          <!-- Series metadata chips — auteurs/éditeurs distincts sur TOUS les tomes,
               un album pouvant avoir plusieurs scénaristes/dessinateurs. -->
          <div v-if="series.pencillers?.length || series.writers?.length || series.publishers?.length" class="series-meta-rows">
            <div v-if="series.pencillers?.length" class="series-meta-row">
              <span class="series-meta-label">Dessinateur{{ series.pencillers.length > 1 ? 's' : '' }}</span>
              <span class="series-meta-links">
                <template v-for="(name, i) in series.pencillers" :key="name">
                  <button class="series-meta-link" @click="router.push(`/series?penciller=${encodeURIComponent(name)}`)">{{ name }}</button><span v-if="i < series.pencillers.length - 1" class="series-meta-sep">, </span>
                </template>
              </span>
            </div>
            <div v-if="series.writers?.length" class="series-meta-row">
              <span class="series-meta-label">Scénariste{{ series.writers.length > 1 ? 's' : '' }}</span>
              <span class="series-meta-links">
                <template v-for="(name, i) in series.writers" :key="name">
                  <button class="series-meta-link" @click="router.push(`/series?writer=${encodeURIComponent(name)}`)">{{ name }}</button><span v-if="i < series.writers.length - 1" class="series-meta-sep">, </span>
                </template>
              </span>
            </div>
            <div v-if="series.publishers?.length" class="series-meta-row">
              <span class="series-meta-label">Éditeur{{ series.publishers.length > 1 ? 's' : '' }}</span>
              <span class="series-meta-links">
                <template v-for="(name, i) in series.publishers" :key="name">
                  <button class="series-meta-link" @click="router.push(`/series?publisher=${encodeURIComponent(name)}`)">{{ name }}</button><span v-if="i < series.publishers.length - 1" class="series-meta-sep">, </span>
                </template>
              </span>
            </div>
          </div>

          <div v-if="series.bedetheque_resume" class="series-resume-wrap">
            <p class="series-resume">{{ resumeDisplay }}<a v-if="series.bedetheque_url" :href="series.bedetheque_url" target="_blank" rel="noopener" class="resume-more-link">Lire la suite</a></p>
          </div>
          <!-- Série reconnue sur Bedetheque.com mais sans résumé extrait (page sans
               synopsis, ou non encore récupéré) — au moins un accès direct à la fiche. -->
          <div v-else-if="series.bedetheque_url" class="series-resume-wrap">
            <a :href="series.bedetheque_url" target="_blank" rel="noopener" class="resume-more-link">Consulter la fiche Bedetheque.com</a>
          </div>

          <!-- Actions sur toute la série — "Éditer" est le seul bouton principal (plus de
               bascule "Reprendre TXX" à sa place : pas cohérent en tant qu'action de premier
               plan pour une série entière). Le reste en icônes seules, comme la fiche
               album. -->
          <div class="series-action-btns">
            <button v-if="authStore.hasPermission('library.metadata_edit')" class="hero-btn hero-btn-primary" @click="showSeriesMeta = true">
              <SvgIcon name="edit" class="btn-icon-svg" /> Éditer
            </button>
            <button v-if="authStore.hasPermission('library.metadata_edit')" class="hero-btn hero-btn-outline hero-btn-icon" title="Métadonnées" @click="showEnrich = true">
              <SvgIcon name="search" style="font-size:15px" />
            </button>
            <button v-if="authStore.hasPermission('library.download')" class="hero-btn hero-btn-outline hero-btn-icon" title="Télécharger" @click="confirmDownload = true">
              <SvgIcon name="download" style="font-size:15px" />
            </button>
            <div v-if="canSeriesMoreMenu" class="toolbar-more-wrap" ref="actionsMenuRef">
              <button class="hero-btn hero-btn-outline hero-btn-icon" :class="{ 'toolbar-more-btn-active': showActionsMenu }" title="Plus d'options" @click="toggleActionsMenu">
                <SvgIcon name="more-vertical" style="font-size:13px" />
              </button>
              <div v-if="showActionsMenu" class="more-menu toolbar-menu" :class="{ 'more-menu-left': actionsMenuLeft }">
                <button v-if="authStore.hasPermission('library.convert')" class="more-item" @click="showConverter = true; showActionsMenu = false">Convertir les fichiers</button>
                <button v-if="authStore.hasPermission('library.rename')" class="more-item" @click="showRename = true; showActionsMenu = false">Renommer les fichiers</button>
                <button v-if="authStore.hasPermission('library.metadata_edit')" class="more-item" @click="showCoverPicker = true; showActionsMenu = false">Modifier la miniature</button>
                <button v-if="authStore.hasPermission('library.metadata_edit')" class="more-item" @click="toggleSeriesHidden(); showActionsMenu = false">
                  {{ series.hidden ? 'Afficher la série' : 'Masquer la série' }}
                </button>
                <div v-if="authStore.hasPermission('library.delete')" class="more-divider"></div>
                <button v-if="authStore.hasPermission('library.delete')" class="more-item more-item-danger" @click="confirmDeleteSeries = true; showActionsMenu = false">Supprimer la série</button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Cartes d'info — Classification/Public/Note plutôt que Dessinateur/Éditeur (déjà
           affichés dans le hero, en lignes qui s'enroulent pour les séries à nombreux
           auteurs) et Bibliothèque (peu intéressant, voir échange de conception). -->
      <section class="info-cards">
        <div class="info-card">
          <div class="info-card-label">Classification</div>
          <div class="info-card-value">{{ series.classification || '—' }}</div>
        </div>
        <div class="info-card">
          <div class="info-card-label">Public</div>
          <div class="info-card-value">{{ series.age_rating || '—' }}</div>
        </div>
        <div class="info-card">
          <div class="info-card-label">Note Bedetheque.com</div>
          <div v-if="series.community_rating" class="info-card-value info-card-rating">
            <span class="bd-stars">
              <span class="bd-stars-bg">★★★★★</span>
              <span class="bd-stars-fill" :style="{ width: (series.community_rating / 5 * 100) + '%' }">★★★★★</span>
            </span>
            <span class="bd-rating-text">{{ series.community_rating }}/5</span>
          </div>
          <div v-else class="info-card-value">—</div>
        </div>
        <div class="info-card">
          <div class="info-card-label">Fiche externe</div>
          <div class="info-card-value">
            <a v-if="series.bedetheque_url" :href="series.bedetheque_url" target="_blank" rel="noopener">Bedetheque.com ↗</a>
            <template v-else>—</template>
          </div>
        </div>
      </section>

      <!-- Barre de sélection multiple — réapparaît sous le header dès qu'un tome est coché -->
      <div v-if="selectedIds.size" class="selection-bar">
        <span class="selection-count">{{ selectedIds.size }} album{{ selectedIds.size > 1 ? 's' : '' }} sélectionné{{ selectedIds.size > 1 ? 's' : '' }}</span>
        <button v-if="authStore.hasPermission('library.metadata_edit')" class="btn btn-secondary btn-sm" @click="showBulkEdit = true">Éditer…</button>
        <a v-if="authStore.hasPermission('library.download')" class="btn btn-secondary btn-sm" :href="tomesApi.downloadBulkUrl([...selectedIds])">Télécharger</a>
        <div v-if="authStore.hasPermission('library.move') || authStore.hasPermission('library.delete')" class="toolbar-more-wrap" ref="selectionMenuRef">
          <button class="toolbar-more-btn" :class="{ 'toolbar-more-btn-active': showSelectionMenu }" title="Plus d'options" @click="toggleSelectionMenu">
            <SvgIcon name="more-vertical" style="font-size:18px" />
          </button>
          <div v-if="showSelectionMenu" class="more-menu toolbar-menu" :class="{ 'more-menu-left': selectionMenuLeft }">
            <button v-if="authStore.hasPermission('library.move')" class="more-item" @click="openMoveSelection(); showSelectionMenu = false">Déplacer</button>
            <div v-if="authStore.hasPermission('library.move') && authStore.hasPermission('library.delete')" class="more-divider"></div>
            <button v-if="authStore.hasPermission('library.delete')" class="more-item more-item-danger" @click="confirmBulkDelete = true; showSelectionMenu = false">Supprimer</button>
          </div>
        </div>
        <button class="btn btn-ghost btn-sm selection-cancel" @click="clearSelection">✕ Annuler la sélection</button>
      </div>

      <!-- Tomes grid — albums possédés et manquants (suivi Bedetheque) mêlés par numéro -->
      <div class="tomes-grid">
        <template v-for="entry in displayItems" :key="entry.kind + '-' + entry.id">
        <div
          v-if="entry.kind === 'tome'"
          class="tome-card"
          :class="{ 'tome-card-selected': selectedIds.has(entry.id), 'menu-open': openMenuId === entry.id }"
          :title="entry.title || entry.filename"
        >
          <!-- Cover — click → tome detail page -->
          <div class="tome-cover" @click="router.push(`/tomes/${entry.id}`)" :class="{ 'tome-cover-hidden': entry.hidden }">
            <!-- Wrapper qui clippe l'image — laisse le menu "plus d'options" dépasser sans être coupé -->
            <div class="tome-cover-clip">
              <img
                v-if="entry.cover_url"
                :src="entry.cover_url"
                :alt="entry.title"
                class="tome-cover-img"
                loading="lazy"
                @error="$event.target.style.display='none'"
              />
              <div v-else class="tome-cover-placeholder">📖</div>
              <div v-if="!selectedIds.has(entry.id)" class="tome-cover-dim" :class="{ 'force-visible': openMenuId === entry.id }"></div>
            </div>

            <!-- Sélection multiple -->
            <button
              class="tome-select"
              :class="{ 'tome-select-active': selectedIds.has(entry.id) }"
              :title="selectedIds.has(entry.id) ? 'Désélectionner' : 'Sélectionner'"
              @click.stop="toggleSelect(entry.id)"
            ></button>

            <!-- Number badge -->
            <span v-if="entry.is_oneshot" class="tome-badge tome-badge-oneshot">One-shot</span>
            <span v-else-if="entry.number" class="tome-badge">T{{ fmtNumber(entry.number) }}</span>

            <!-- Hover overlay — masqué une fois l'album sélectionné, pour se concentrer sur
                 l'action de sélection, comme sur les pages Séries/Albums. -->
            <div
              v-if="!selectedIds.has(entry.id)"
              class="tome-overlay"
              :class="{ 'force-visible': openMenuId === entry.id }"
              @click.stop="router.push(`/read/${entry.id}`)"
            >
              <SvgIcon name="read" class="tome-read-icon" />
              <button v-if="authStore.hasPermission('library.metadata_edit')" class="overlay-btn tome-edit-btn" title="Modifier" @click.stop="onEditTome(entry)">
                <SvgIcon name="edit" style="font-size:20px" />
              </button>
              <div v-if="canTomeMoreMenu" class="tome-more-wrap" @click.stop>
                <button
                  class="overlay-btn tome-more-btn"
                  :class="{ 'overlay-btn-active': openMenuId === entry.id }"
                  title="Plus d'options"
                  @click="toggleTomeMenu($event, entry.id)"
                >
                  <SvgIcon name="more-vertical" style="font-size:20px" />
                </button>
                <div v-if="openMenuId === entry.id" class="more-menu" :class="{ 'more-menu-left': menuLeft }">
                  <template v-if="authStore.hasPermission('library.metadata_edit')">
                    <button class="more-item" @click="onEditTome(entry); openMenuId = null">Éditer les métadonnées</button>
                    <button class="more-item" @click="onSearchTomeMetadata(entry); openMenuId = null">Rechercher les métadonnées</button>
                  </template>
                  <button v-if="authStore.hasPermission('library.move')" class="more-item" @click="openMoveSingle(entry); openMenuId = null">Déplacer vers une série</button>
                  <a v-if="authStore.hasPermission('library.download')" class="more-item" :href="tomesApi.downloadUrl(entry.id)" @click="openMenuId = null">Télécharger</a>
                  <div v-if="authStore.hasPermission('library.delete')" class="more-divider"></div>
                  <button v-if="authStore.hasPermission('library.delete')" class="more-item more-item-danger" @click="confirmDeleteTome = entry; openMenuId = null">Supprimer l'album</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Info — click → tome detail page -->
          <div class="tome-info" @click="router.push(`/tomes/${entry.id}`)">
            <p class="tome-title">{{ entry.title || entry.filename }}</p>
            <p class="tome-meta">
              <span :class="['fmt-badge', `fmt-${entry.file_format}`]">{{ entry.file_format.toUpperCase() }}</span>
              <span v-if="entry.page_count" class="tome-pages">{{ entry.page_count }} pages</span>
            </p>
          </div>
        </div>

        <!-- Album manquant — pas de lecture/édition possible, juste un repère visuel dans la
             collection + lien vers la fiche Bedetheque si connue. Cover assombrie et badge
             "Manquant" pour ne pas le confondre avec un album réellement possédé. -->
        <a
          v-else
          class="tome-card tome-card-missing"
          :href="entry.bedetheque_url || null"
          :target="entry.bedetheque_url ? '_blank' : null"
          :rel="entry.bedetheque_url ? 'noopener' : null"
          :title="(entry.title || ('Tome ' + entry.number)) + ' — manquant'"
        >
          <div class="tome-cover">
            <div class="tome-cover-clip">
              <img
                v-if="entry.cover_url"
                :src="entry.cover_url"
                :alt="entry.title"
                class="tome-cover-img tome-cover-img-missing"
                loading="lazy"
                @error="$event.target.style.display='none'"
              />
              <div v-else class="tome-cover-placeholder">📖</div>
              <div class="tome-cover-dim tome-cover-dim-missing force-visible"></div>
              <SvgIcon name="square-arrow-out-up-right" class="tome-missing-open-icon" />
            </div>
            <span v-if="entry.number" class="tome-badge">T{{ fmtNumber(entry.number) }}</span>
            <span class="tome-missing-badge">Manquant</span>
            <button
              class="overlay-btn tome-missing-upload-btn"
              type="button"
              title="Ajouter ce fichier depuis mon appareil"
              @click.stop.prevent="openMissingUpload(entry)"
            ><SvgIcon name="square-plus" style="font-size:20px" /></button>
          </div>
          <div class="tome-info">
            <p class="tome-title">{{ entry.title || ('Tome ' + entry.number) }}</p>
            <p v-if="entry.year" class="tome-meta"><span class="tome-pages">{{ entry.year }}</span></p>
          </div>
        </a>
        </template>
      </div>

      <!-- Séries similaires / du même auteur — mêmes données que la navigation précédent/
           suivant ci-dessus (libraryStore.series), aucun nouvel appel réseau. Une section
           masquée entièrement si aucune autre série ne partage le critère (pas de rangée
           vide à afficher). -->
      <section v-if="similarSeries.length" class="related-section">
        <div class="related-title-group">
          <h2 class="related-title">Séries similaires</h2>
          <span class="related-count">{{ similarSeries.length }}</span>
        </div>
        <div class="scroll-row">
          <div v-for="s in similarSeries" :key="s.id" class="related-card" @click="router.push(`/series/${s.id}`)">
            <div class="related-cover">
              <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="related-cover-img" />
              <div v-else class="related-cover-placeholder">📚</div>
            </div>
            <div class="related-info">
              <p class="related-name">{{ s.name }}</p>
            </div>
          </div>
        </div>
      </section>

      <section v-if="sameWriterSeries.length" class="related-section">
        <div class="related-title-group">
          <h2 class="related-title">Du même scénariste</h2>
          <span class="related-count">{{ sameWriterSeries.length }}</span>
        </div>
        <div class="scroll-row">
          <div v-for="s in sameWriterSeries" :key="s.id" class="related-card" @click="router.push(`/series/${s.id}`)">
            <div class="related-cover">
              <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="related-cover-img" />
              <div v-else class="related-cover-placeholder">📚</div>
            </div>
            <div class="related-info">
              <p class="related-name">{{ s.name }}</p>
            </div>
          </div>
        </div>
      </section>

      <section v-if="samePencillerSeries.length" class="related-section">
        <div class="related-title-group">
          <h2 class="related-title">Du même dessinateur</h2>
          <span class="related-count">{{ samePencillerSeries.length }}</span>
        </div>
        <div class="scroll-row">
          <div v-for="s in samePencillerSeries" :key="s.id" class="related-card" @click="router.push(`/series/${s.id}`)">
            <div class="related-cover">
              <img v-if="s.cover_url" :src="s.cover_url" :alt="s.name" class="related-cover-img" />
              <div v-else class="related-cover-placeholder">📚</div>
            </div>
            <div class="related-info">
              <p class="related-name">{{ s.name }}</p>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- Series metadata modal -->
    <SeriesMetadataModal
      v-if="showSeriesMeta"
      :series="series"
      @close="showSeriesMeta = false"
      @saved="loadSeries(route.params.id)"
      @deleted="libraryStore.fetchSeries().then(() => router.push('/series'))"
      @enrich="showEnrich = true"
    />

    <!-- Tome metadata modal -->
    <MetadataDrawer
      v-if="showTomeMeta && selectedTome"
      :tome="selectedTome"
      :open-scraper="openScraperOnOpen"
      @close="showTomeMeta = false"
      @deleted="({ series_deleted }) => { if (series_deleted) libraryStore.fetchSeries().then(() => router.push('/series')); else libraryApi.getSeriesDetail(route.params.id).then(({ data }) => { series.value = data }) }"
    />

    <!-- Enrich from Bedetheque modal -->
    <SeriesEnrichModal
      v-if="showEnrich"
      :series="series"
      @close="showEnrich = false"
      @saved="libraryApi.getSeriesDetail(route.params.id).then(({ data }) => { series.value = data })"
    />

    <!-- Converter modal -->
    <ConverterModal
      v-if="showConverter"
      :tomes="convertTomeId ? sortedTomes.filter(t => t.id === convertTomeId) : sortedTomes"
      @close="showConverter = false; convertTomeId = null"
      @done="showConverter = false; convertTomeId = null"
    />

    <CoverPickerModal
      v-if="showCoverPicker && series"
      :series="series"
      @close="showCoverPicker = false"
      @updated="onCoverUpdated"
    />

    <!-- Renommer les fichiers de la série -->
    <RenameModal
      v-if="showRename && series"
      :tomes="sortedTomes"
      :series-name="series.name"
      @close="showRename = false"
      @done="showRename = false; loadSeries(route.params.id)"
    />

    <!-- Déplacer un ou plusieurs albums vers une autre série -->
    <MoveTomesModal
      v-if="showMove"
      :tome-ids="moveTomeIds"
      @close="showMove = false"
      @moved="onMoved"
    />

    <!-- Éditer en lot -->
    <BulkEditTomesModal
      v-if="showBulkEdit"
      :tome-ids="[...selectedIds]"
      @close="showBulkEdit = false"
      @saved="loadSeries(route.params.id)"
    />

    <!-- Uploader un fichier pour un album manquant -->
    <MissingAlbumUploadModal
      v-if="uploadAlbum"
      :album="uploadAlbum"
      @close="uploadAlbum = null"
      @uploaded="onAlbumUploaded"
    />

    <!-- Confirmation téléchargement de la série -->
    <div v-if="confirmDownload" class="confirm-backdrop" @click.self="confirmDownload = false">
      <div class="confirm-box">
        <p class="confirm-title">Télécharger la série ?</p>
        <p class="confirm-desc">
          {{ sortedTomes.length }} album{{ sortedTomes.length > 1 ? 's' : '' }} de <strong>{{ series.name }}</strong> seront téléchargés dans une archive.
        </p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDownload = false">Annuler</button>
          <button class="btn btn-primary btn-sm" @click="downloadSeries">Télécharger</button>
        </div>
      </div>
    </div>

    <!-- Confirmation suppression de la série -->
    <div v-if="confirmDeleteSeries" class="confirm-backdrop" @click.self="confirmDeleteSeries = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer la série ?</p>
        <p class="confirm-desc">
          <strong>{{ series.name }}</strong> et tous ses fichiers seront supprimés définitivement.
        </p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDeleteSeries = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteSeries" :disabled="deletingSeries">
            {{ deletingSeries ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirmation suppression en lot -->
    <div v-if="confirmBulkDelete" class="confirm-backdrop" @click.self="confirmBulkDelete = false">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer {{ selectedIds.size }} album{{ selectedIds.size > 1 ? 's' : '' }} ?</p>
        <p class="confirm-desc">Les fichiers seront supprimés définitivement du disque.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmBulkDelete = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="bulkDelete" :disabled="bulkDeleting">
            {{ bulkDeleting ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirmation suppression d'un seul album -->
    <div v-if="confirmDeleteTome" class="confirm-backdrop" @click.self="confirmDeleteTome = null">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer l'album ?</p>
        <p class="confirm-desc">
          <strong>{{ confirmDeleteTome.title || confirmDeleteTome.filename }}</strong> sera supprimé définitivement du disque.
        </p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDeleteTome = null">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="deleteSingleTome" :disabled="deletingSingle">
            {{ deletingSingle ? 'Suppression…' : 'Supprimer définitivement' }}
          </button>
        </div>
      </div>
    </div>
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
  color: var(--vermilion); font-size: 0.875rem; font-family: var(--font);
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

/* Series header — bandeau "hero" : fond illustré fourni ou dégradé de repli (voir
   heroGradient.js), remplace l'ancien header sans fond (voir TomeDetailView.vue pour le
   même principe côté album, avec un fond systématiquement plus discret). Dégradés de fade
   en rgba(var(--light-rgb),…) — un gradient ne peut pas piocher les composantes RGB d'une
   variable CSS classique, d'où --light-rgb (canaux séparés, voir style.css) plutôt que
   rgba(242,237,226,…) figé en dur : ce dernier restait toujours clair même en thème sombre,
   rendant le texte du bandeau (clair lui aussi en sombre) illisible dessus. Testé et validé
   dans design-tests/ avant intégration. */
.series-hero {
  position: relative;
  border-radius: 16px; box-shadow: var(--shadow-lg);
  background: var(--light);
  margin-bottom: 16px;
}
/* Le fond/dégradé est clippé dans son propre calque plutôt que sur .series-hero directement
   — un overflow:hidden ici aurait aussi coupé le menu "..." (position:absolute), qui dépasse
   volontairement de la carte pour s'ouvrir par-dessus le contenu en dessous. */
.series-hero-bg-clip { position: absolute; inset: 0; border-radius: 16px; overflow: hidden; }
/* Hauteur pleine, largeur ancrée à droite — pas "cover" (recadre le haut du sujet, revenu en
   arrière sur retour utilisateur). "auto 100%" garantit que toute la hauteur de l'image reste
   visible, quitte à ce que sa largeur rendue soit inférieure à celle du bandeau — voir
   .series-hero-fade-h juste en dessous, qui masque ce manque de largeur sous un dégradé, et
   dont le point de départ est recalculé par palier d'écran ci-dessous. */
.series-hero-bg { position: absolute; inset: 0; background-size: auto 100%; background-position: 100% center; background-repeat: no-repeat; }
/* Images fond de série désormais en 1600×400 (ratio 4:1, voir échange avec l'utilisateur —
   remplace l'ancien 1200×600/2:1) : à hauteur de bandeau H, l'image (auto 100%) est rendue à
   une largeur de 4×H px. H ≈ 470px (mesuré : bandeau 1435×470) → largeur rendue ≈ 1880px, DÉJÀ
   plus large que le bandeau de référence et que la plupart des largeurs de fenêtre courantes :
   contrairement au 2:1 (qui laissait toujours ~35 à 75% de bandeau à masquer), le 4:1 ne laisse
   plus aucun trou avant ~1900px de bandeau. Le dégradé de base n'a donc plus qu'un rôle de
   lisibilité du texte (l'image passe désormais dessous), pas de coupure à cacher ; les paliers
   ne recalent un vrai fondu de bord que pour les fenêtres très larges où un trou réapparaît
   (S = 1 − 1880/largeur_bandeau). Non vérifié visuellement au-delà de la résolution de
   référence (pas d'outil de navigateur/écran 4K dans cette session) — à ajuster si un palier
   ne tombe pas juste. */
.series-hero-fade-h {
  position: absolute; inset: 0;
  background: linear-gradient(100deg,
    rgba(var(--light-rgb),.95) 0%, rgba(var(--light-rgb),.95) 38%, rgba(var(--light-rgb),.6) 50%,
    rgba(var(--light-rgb),0) 60%, rgba(var(--light-rgb),0) 100%);
}
/* ~2400px de bandeau (S ≈ 22%) — trou réel, dégradé "smoothstep" complet comme avant 4:1 */
@media (min-width: 2100px) {
  .series-hero-fade-h {
    background: linear-gradient(100deg,
      rgba(var(--light-rgb),.97) 0%, rgba(var(--light-rgb),.97) 32%, rgba(var(--light-rgb),.90) 39%,
      rgba(var(--light-rgb),.76) 45%, rgba(var(--light-rgb),.49) 55%, rgba(var(--light-rgb),.21) 63%,
      rgba(var(--light-rgb),.06) 70%, rgba(var(--light-rgb),0) 77%, rgba(var(--light-rgb),0) 100%);
  }
}
/* ~3840px de bandeau, 4K (S ≈ 51%) */
@media (min-width: 3000px) {
  .series-hero-fade-h {
    background: linear-gradient(100deg,
      rgba(var(--light-rgb),.97) 0%, rgba(var(--light-rgb),.97) 61%, rgba(var(--light-rgb),.90) 68%,
      rgba(var(--light-rgb),.76) 74%, rgba(var(--light-rgb),.49) 84%, rgba(var(--light-rgb),.21) 92%,
      rgba(var(--light-rgb),.06) 99%, rgba(var(--light-rgb),0) 100%, rgba(var(--light-rgb),0) 100%);
  }
}
.series-hero-fade-v {
  position: absolute; inset: 0;
  background: linear-gradient(to top, rgba(var(--light-rgb),.9) 0%, rgba(var(--light-rgb),.2) 22%, rgba(var(--light-rgb),0) 46%);
}
/* Trame de points (halftone) — test visuel, voir hero-bd-replication.md. Point rond en
   couleur d'accent (vermillon, "encre" du thème), plein à 1.5px puis coupé net à 1.6px pour
   un bord légèrement anti-aliasé ; répété tous les 8px. opacity:.25 en plus des 45% déjà
   dans color-mix adoucit encore la trame (~11% d'encre effective) ; mix-blend-mode:multiply
   fonce le fond dessous plutôt que de le voiler d'une teinte plate. */
.series-hero-halftone {
  position: absolute; inset: 0;
  pointer-events: none;
  opacity: 0.25;
  mix-blend-mode: multiply;
  background-image: radial-gradient(color-mix(in srgb, var(--vermilion) 45%, transparent) 1.5px, transparent 1.6px);
  background-size: 8px 8px;
}
/* Repli sans image de fond (voir design-tests/series-detail-alt-no-art.html) : le dégradé CSS
   est déjà bien plus discret qu'une photo, les mêmes fades que la version "avec fond fourni"
   le lessivaient quasi entièrement (jusqu'à .97 d'opacité). Variante allégée, appliquée
   uniquement quand hero_background_version vaut 0 (voir hasHeroBackground). */
.series-hero-fade--soft.series-hero-fade-h {
  background: linear-gradient(100deg,
    rgba(var(--light-rgb),.55) 0%, rgba(var(--light-rgb),.55) 45%, rgba(var(--light-rgb),.51) 52%,
    rgba(var(--light-rgb),.43) 58%, rgba(var(--light-rgb),.28) 68%, rgba(var(--light-rgb),.12) 76%,
    rgba(var(--light-rgb),.03) 83%, rgba(var(--light-rgb),0) 90%, rgba(var(--light-rgb),0) 100%);
}
.series-hero-fade--soft.series-hero-fade-v {
  background: linear-gradient(to top, rgba(var(--light-rgb),.55) 0%, rgba(var(--light-rgb),0) 40%);
}
/* Padding vertical resserré (40 → 28px) — voir aussi les marges resserrées plus bas
   (series-title/series-count/series-meta-rows/series-resume-wrap) : la hauteur du bandeau
   est pilotée par ce contenu, pas par le fond, donc plus il est haut, plus le fond (fourni
   en 4:1, voir échange sur le format) doit être zoomé/recadré pour le couvrir. Écart encore
   réel avec un vrai 4:1 (impossible à atteindre sans retirer du contenu), mais nettement
   réduit. */
.series-hero-inner { position: relative; padding: 28px 44px; max-width: 600px; }
/* Cadre à hauteur FIXE (pas max-height) : contrairement aux essais précédents (plafonner
   uniquement le logo lui-même), la hauteur totale du bandeau ne doit jamais dépendre de la
   forme du logo — même principe que .logo-card sur l'accueil (boîte fixe, object-fit sur
   l'image dedans), qui n'a jamais ce problème. Un logo carré/vertical (ex. "Les 4 As") sera
   simplement plus petit à l'intérieur de ce cadre plutôt que de l'agrandir.
   150px (pas 44) : la première valeur était calée sur "Sillage" (127px de haut réels sur
   1000px de large), un cas extrême très plat — "Poussy" (1000×400, pas de marge à rogner)
   rendait déjà 136px de haut avec la règle validée au dernier rituel (width:340px sans
   plafond), donc 44px le rétrécissait à tort. 150px laisse tout logo jusqu'à ~2,3:1 de
   ratio (la plupart des cas réels) inchangé par rapport à avant, et ne plafonne que les
   vrais carrés/verticaux qui posaient effectivement problème. */
.series-hero-logo-box {
  width: 272px; max-width: 100%; height: 120px;
  margin-bottom: 20px;
  display: flex; align-items: center; justify-content: flex-start;
}
.series-hero-logo { display: block; max-width: 100%; max-height: 100%; width: auto; height: auto; filter: drop-shadow(0 4px 10px rgba(30,42,66,.25)); }
/* Bebas Neue, capitales — poids 400 uniquement disponible dans cette police. Taille du repli
   "no-art" (design-tests/series-detail-alt-no-art.html) : plus grande que quand un vrai logo
   est fourni, pour occuper seul le rôle visuel que tenait la cover/le logo. Pas d'ombre
   portée : sans photo de fond, la lisibilité n'est jamais un problème ici. */
.series-title {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: clamp(2.2rem, 4.6vw, 3.8rem); line-height: 0.96; letter-spacing: .01em;
  margin-bottom: 10px; color: var(--text);
}
/* Un peu moins foncé que var(--text) pur — même mélange que .tome-meta (TomeDetailView.vue). */
.series-count { font-size: 0.875rem; font-weight: 600; color: color-mix(in srgb, var(--text) 85%, var(--muted) 15%); margin-bottom: 8px; }
/* &nbsp; de part et d'autre plutôt qu'un simple espacement flex/gap — un vrai caractère
   d'espace, qui reste correct même si le texte est sélectionné/copié. */
/* Séparateur discret : poids normal (le reste de la ligne est en gras) et opacité réduite,
   pour ne pas ressortir comme un point plein entre les segments. */
.series-info-sep { color: var(--muted); font-weight: 400; opacity: .45; }
.mono-num { font-family: var(--font-mono); }

.series-meta-rows { display: flex; flex-direction: column; gap: 3px; margin-bottom: 10px; }
.series-meta-row { display: flex; gap: 8px; font-size: 0.8125rem; }
.series-meta-label { color: var(--muted); width: 90px; flex-shrink: 0; }
.series-meta-links { display: inline; }
.series-meta-link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--vermilion); font-size: 0.8125rem; font-family: var(--font);
  text-align: left; display: inline;
}
.series-meta-link:hover { text-decoration: underline; }
.series-meta-sep { color: var(--muted); }
.series-resume-wrap { margin-bottom: 12px; }
.series-resume {
  font-size: 0.85rem; color: var(--text); line-height: 1.5; margin: 0;
}
.resume-more-link {
  margin-left: 4px;
  font-size: 0.8125rem; font-weight: 600;
  color: var(--vermilion); white-space: nowrap;
}
.resume-more-link:hover { text-decoration: underline; }

.bd-status-badge {
  display: inline-flex; align-items: center;
  vertical-align: middle; margin-left: 6px;
  padding: 1px 7px; border-radius: 20px;
  font-size: 0.62rem; font-weight: 600; white-space: nowrap;
  text-transform: uppercase;
  background: none; color: var(--text); border: 1px solid var(--text);
}

/* Cartes d'info sous le hero — une seule carte, chaque info séparée par un léger trait
   vertical plutôt que 4 cartes distinctes avec un espace entre elles. */
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
/* Étoiles Bedetheque.com — repris tel quel de TomeDetailView.vue (remplissage proportionnel
   par overlay clippé, gère les notes décimales contrairement à un compte d'étoiles entier). */
.info-card-rating { display: flex; align-items: center; gap: 8px; }
.bd-stars { position: relative; display: inline-block; font-size: 1rem; line-height: 1; white-space: nowrap; }
.bd-stars-bg { color: var(--star-empty); }
.bd-stars-fill { position: absolute; top: 0; left: 0; overflow: hidden; color: var(--star-filled); }
.bd-rating-text { font-family: var(--font-mono); font-size: 0.78rem; color: var(--muted); }

/* Boutons du hero — même style que .hero-btn de TomeDetailView.vue (primary blanc,
   outline assorti au thème clair/sombre du site puisque le fond n'est plus sombre fixe). */
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
.hero-btn-outline { background: var(--surface); color: var(--text); border-color: var(--border); }
.hero-btn-outline:hover,
.hero-btn-outline.toolbar-more-btn-active { background: var(--light); }
.hero-btn-icon { padding: 6px 8px; }

/* Tomes grid */
.tomes-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .tomes-grid { grid-template-columns: repeat(3, 1fr); } }

@media (max-width: 620px) {
  .series-hero-inner { padding: 28px 22px; }
  /* Fond (image fournie ou dégradé de repli) + fondus retirés sur mobile — un bandeau
     étroit rend mal le recadrage pensé pour une largeur desktop. Le fond uni de
     .series-hero (var(--light)) suffit, texte toujours lisible dessus. */
  .series-hero-bg-clip { display: none; }
}

@media (min-width: 700px)  { .tomes-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .tomes-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .tomes-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .tomes-grid { grid-template-columns: repeat(8, 1fr); } }

/* Tome card */
.tome-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: visible;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
  position: relative;
  z-index: 1;
}
.tome-card:hover {
  box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg);
  transform: translateY(-2px);
  /* Juste assez pour passer au-dessus des cards voisines (z-index:1) — jamais au-dessus
     de la barre du haut (z-index:40, sticky) sous peine de la traverser au survol. */
  z-index: 2;
}
.tome-card.menu-open { z-index: 6; }
.tome-card-selected { box-shadow: 0 0 0 1.5px var(--primary); }

.tome-cover {
  aspect-ratio: 0.71;
  position: relative;
  cursor: pointer;
  overflow: visible; /* laisse le menu "plus d'options" dépasser */
}

/* Wrapper qui clippe l'image — le reste de .tome-cover reste visible pour le menu */
.tome-cover-clip {
  position: absolute; inset: 0;
  overflow: hidden;
  border-radius: var(--radius) var(--radius) 0 0;
  background: var(--light);
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
.tome-cover-dim {
  position: absolute; inset: 0; z-index: 2;
  background: rgba(0,0,0,0.45);
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
/* Le menu "plus d'options" reste ouvert même si la souris quitte la card — donc le fond
   sombre et l'overlay doivent rester visibles tant qu'il l'est, pas juste au survol. */
.tome-card:hover .tome-cover-dim,
.tome-cover-dim.force-visible { opacity: 1; }

.tome-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}
.tome-badge-oneshot { background: var(--vermilion); color: #fff; }

/* Carte "album manquant" — même gabarit que .tome-card, mais sans aucune action de
   lecture/édition (juste un lien vers Bedetheque si connu) et une distinction visuelle
   nette pour ne jamais la confondre avec un album réellement possédé. */
/* La card manquante est un <a> — sans ce reset, le titre hérite du bleu/soulignement
   lien par défaut (a { color }, a:hover { text-decoration }). */
/* text-decoration:none sur le descendant ne suffit pas toujours à annuler la ligne de
   l'ancêtre <a> — le fix fiable est de désactiver la décoration sur le <a> lui-même. */
.tome-card-missing, .tome-card-missing:hover { text-decoration: none; cursor: pointer; }
.tome-card-missing:hover { box-shadow: var(--shadow-lg); }
.tome-card-missing .tome-title { color: var(--text); text-decoration: none; }
.tome-card-missing:hover .tome-title { text-decoration: none; }
.tome-cover-img-missing { filter: grayscale(70%); opacity: 0.55; }
.tome-cover-dim-missing { background: rgba(0,0,0,0.25); }
.tome-missing-badge {
  position: absolute; bottom: 6px; left: 6px; z-index: 3;
  padding: 1px 6px;
  background: var(--warning-bg); color: var(--warning-text, var(--warning));
  font-size: 0.66rem; font-weight: 700; border-radius: 4px;
}

/* Survol carte manquante — même traitement que la page Albums manquants : grande icône
   "lien externe" au centre (renvoie vers Bedetheque), bouton d'upload en bas à droite. */
.tome-missing-open-icon {
  position: absolute; inset: 0; z-index: 2;
  display: flex; align-items: center; justify-content: center;
  font-size: 40px; color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
.tome-card-missing:hover .tome-missing-open-icon { opacity: 1; }

.tome-missing-upload-btn {
  position: absolute; bottom: 6px; right: 6px; z-index: 3;
  opacity: 0; transition: opacity 0.15s, transform 0.12s, color 0.12s;
}
.tome-card-missing:hover .tome-missing-upload-btn { opacity: 1; }
.tome-missing-upload-btn:hover { color: var(--primary-focus-border); }

.tome-select {
  position: absolute; top: 6px; left: 6px; z-index: 4;
  width: 16px; height: 16px; border-radius: 50%;
  background: none; border: 1.5px solid #fff;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
  cursor: pointer; padding: 0;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.15s, border-color 0.12s, background 0.12s, transform 0.1s;
}
.tome-card:hover .tome-select,
.tome-select-active { opacity: 1; }
.tome-select:hover { transform: scale(1.15); }
.tome-select-active { border-color: var(--vermilion); background: var(--vermilion); }
.tome-select-active::after {
  content: '✓';
  color: #fff; font-size: 10px; font-weight: 700; line-height: 1;
}

.tome-overlay {
  position: absolute; inset: 0; z-index: 3;
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.tome-card:hover .tome-overlay,
.tome-overlay.force-visible { opacity: 1; }
.tome-read-icon {
  font-size: 48px; color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}
.tome-edit-btn {
  position: absolute; bottom: 8px; left: 8px;
}

/* Menu "plus d'options" — en bas à droite de la cover, s'ouvre vers le bas comme sur la
   page Séries. */
.tome-more-wrap { position: absolute; bottom: 8px; right: 8px; }
.more-menu {
  position: absolute;
  top: calc(100% + 4px); left: 0;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  min-width: 190px;
  padding: 4px 0;
  z-index: 300;
}
.more-menu.more-menu-left { left: auto; right: 0; }
.more-item {
  display: block;
  width: 100%; padding: 8px 14px;
  background: none; border: none; cursor: pointer;
  font-size: 0.8125rem; font-family: var(--font); color: var(--text);
  text-align: left;
  transition: background 0.1s;
  white-space: nowrap;
}
.more-item:hover { background: var(--light); }
.more-divider { height: 1px; background: var(--border); margin: 4px 0; }
.more-item-danger { color: var(--danger); }
.more-item-danger:hover { background: var(--danger-bg-light); }

.tome-info {
  padding: 7px 9px; border-top: 1px solid var(--border); cursor: pointer;
}
.tome-title {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 4px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.tome-meta { display: flex; align-items: center; gap: 6px; }
.fmt-badge {
  font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px;
}
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }
.tome-pages { font-size: 0.72rem; color: var(--muted); }

.series-action-btns { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: auto; }

/* Barre de sélection multiple */
.selection-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 8px 14px;
  margin-bottom: 14px;
  background: var(--primary-light);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.selection-count { font-size: 0.82rem; font-weight: 600; color: var(--primary); margin-right: 4px; }
.selection-cancel { margin-left: auto; }
.toolbar-more-wrap { position: relative; }
/* Déclencheur "..." à droite des boutons principaux — .overlay-btn (icône blanche, pensé
   pour survoler une image) ne convient pas ici, fond clair de la barre. */
.toolbar-more-btn {
  width: 30px; height: 30px; flex-shrink: 0;
  background: none; border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer; color: var(--text);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}
.toolbar-more-btn:hover { background: var(--light); }
.toolbar-more-btn-active { border-color: var(--vermilion); color: var(--vermilion); background: var(--vermilion-light); }
.btn-danger-ghost { color: var(--danger); }
.btn-danger-ghost:hover { background: var(--danger-bg-light); }

/* Confirmation de suppression */
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

/* Séries similaires / du même auteur — même rangée à défilement horizontal que HomeView.vue
   (ascenseur masqué, fondu discret sur le bord droit). */
.related-section { margin-top: 28px; }
.related-title-group { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.related-title { font-size: 1rem; font-weight: 600; }
.related-count { font-family: var(--font-mono); font-size: 0.72rem; color: var(--muted); }
/* padding-top/-left + margin négatif égal : compense le rognage du pixel de bordure collé au
   bord (overflow-x:auto force overflow-y:auto, qui rogne le haut ; le bord gauche de la toute
   première carte n'a lui aussi aucun "gap" voisin pour le masquer) sans décaler visuellement
   la rangée — même correctif que HomeView.vue::.scroll-row, jamais appliqué ici jusqu'ici. */
.scroll-row {
  display: flex; flex-direction: row; gap: 12px; overflow-x: auto; scrollbar-width: none;
  padding-top: 4px; margin-top: -4px;
  padding-left: 4px; margin-left: -4px;
  mask-image: linear-gradient(to right, black calc(100% - 14px), rgba(0,0,0,0.6) 100%);
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 14px), rgba(0,0,0,0.6) 100%);
}
.scroll-row::-webkit-scrollbar { display: none; }
/* Carte fond blanc — même habillage que .tome-card (background/border/shadow) plutôt qu'une
   cover nue : c'était l'écart signalé face au reste de l'app. Plus petite (100px, vs 140-160px
   pour une cover de tome ailleurs) pour qu'on distingue au premier coup d'œil les tomes de
   cette série (grille au-dessus) des séries suggérées (rangées ici). */
.related-card {
  flex: 0 0 auto; width: 132px; cursor: pointer; transition: box-shadow 0.18s, transform 0.18s;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow-sm); overflow: hidden;
}
.related-card:hover { box-shadow: var(--shadow-lg); transform: translateY(-2px); }
.related-cover { width: 100%; aspect-ratio: 0.71; background: var(--light); overflow: hidden; position: relative; }
.related-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s; }
.related-card:hover .related-cover-img { transform: scale(1.04); }
.related-cover-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; color: var(--placeholder); }
.related-info { padding: 6px 8px; border-top: 1px solid var(--border); }
.related-name {
  font-size: 0.75rem; font-weight: 600; color: var(--text); line-height: 1.3;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.6em;
}
</style>
