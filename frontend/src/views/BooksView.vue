<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import ContentToolbar from '../components/layout/ContentToolbar.vue'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import MoveTomesModal from '../components/library/MoveTomesModal.vue'
import BulkEditTomesModal from '../components/metadata/BulkEditTomesModal.vue'
import { tomesApi } from '../api/tomes'
import { useNotificationStore } from '../stores/notifications'
import { useTomesStore } from '../stores/tomes'
import { useLibraryStore } from '../stores/library'
import { useAuthStore } from '../stores/auth'
import { sortTitle } from '../utils/text'

const router = useRouter()
const route = useRoute()
const tomesStore = useTomesStore()
const library = useLibraryStore()
const notif = useNotificationStore()
const authStore = useAuthStore()
const canTomeMenu = computed(() => ['library.metadata_edit', 'library.move', 'library.download', 'library.delete']
  .some(p => authStore.hasPermission(p)))

const activeLetter = ref('')
const selectedTome = ref(null)
const showMetadata = ref(false)

// Sélection multiple — indépendante du "editTome" (fiche d'un seul album) : un cercle sur
// chaque cover, cliquable sans ouvrir la fiche, pour des actions en lot (déplacer, etc.).
// Les cercles ne sont visibles que si "Sélectionner" est activé (bouton en haut à droite) —
// désactiver ce mode vide aussi la sélection en cours.
const selectedIds = reactive(new Set())
const selectMode = ref(false)
const showMove = ref(false)
const showBulkEdit = ref(false)
const confirmBulkDelete = ref(false)
const bulkDeleting = ref(false)
function toggleSelect(tomeId) {
  if (selectedIds.has(tomeId)) selectedIds.delete(tomeId)
  else selectedIds.add(tomeId)
}
function clearSelection() { selectedIds.clear(); selectMode.value = false }
watch(selectMode, (v) => { if (!v) selectedIds.clear() })

// Échap désélectionne — mais seulement si aucune popup n'est ouverte au-dessus (chacune gère
// déjà son propre Échap pour se refermer en premier, ex. MetadataDrawer/MoveTomesModal).
function onSelectionEscape(e) {
  if (e.key !== 'Escape' || !selectedIds.size) return
  if (showMetadata.value || showMove.value || showBulkEdit.value || confirmBulkDelete.value || confirmDeleteTome.value || openMenuId.value !== null) return
  clearSelection()
}
onMounted(() => window.addEventListener('keydown', onSelectionEscape))
onUnmounted(() => window.removeEventListener('keydown', onSelectionEscape))

async function bulkDelete() {
  bulkDeleting.value = true
  try {
    const { data } = await tomesApi.deleteBulk([...selectedIds])
    if (data.errors?.length) notif.error(`${data.errors.length} erreur(s) — ${data.errors[0]}`)
    else notif.success(`${data.ok} album(s) supprimé(s)`)
    clearSelection()
    await tomesStore.fetchAllTomes()
    await library.fetchSeries()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    bulkDeleting.value = false
    confirmBulkDelete.value = false
  }
}

// Déplacement — même champ (tome_ids) que la sélection soit multiple (barre du haut) ou
// un seul album (menu "plus d'options" par card).
const moveTomeIds = ref([])
function openMoveSelection() {
  moveTomeIds.value = [...selectedIds]
  showMove.value = true
}
function openMoveSingle(tome) {
  moveTomeIds.value = [tome.id]
  showMove.value = true
}
async function onMoved() {
  clearSelection()
  moveTomeIds.value = []
  await tomesStore.fetchAllTomes()
  await library.fetchSeries()
}

// Menu « plus d'options » (3 points) par album — déplacer/éditer/supprimer un seul album
// sans passer par la sélection multiple.
const openMenuId = ref(null)
const menuLeft = ref(false)
const confirmDeleteTome = ref(null)
const deletingSingle = ref(false)

function toggleTomeMenu(e, tomeId) {
  menuLeft.value = e.clientX > window.innerWidth * 0.66
  openMenuId.value = openMenuId.value === tomeId ? null : tomeId
}
function onClickOutsideMenu(e) {
  if (openMenuId.value !== null && !e.target.closest('.book-more-wrap')) {
    openMenuId.value = null
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutsideMenu))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutsideMenu))

async function deleteSingleTome() {
  if (!confirmDeleteTome.value) return
  deletingSingle.value = true
  try {
    await tomesApi.deleteFile(confirmDeleteTome.value.id)
    notif.success('Album supprimé')
    await tomesStore.fetchAllTomes()
    await library.fetchSeries()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deletingSingle.value = false
    confirmDeleteTome.value = null
  }
}

function syncFromQuery() {
  const q = route.query
  if (q.writer || q.penciller || q.publisher || q.tag || q.genre || q.classification) {
    library.filters = {
      writer: q.writer || '',
      penciller: q.penciller || '',
      publisher: q.publisher || '',
      tag: q.tag || '',
      genre: q.genre || '',
      classification: q.classification || '',
    }
  }
  if (tomesStore.tomes.length === 0) {
    tomesStore.fetchAllTomes()
  }
}

onMounted(syncFromQuery)
watch(() => route.query, syncFromQuery)

// Normalize: strip accents, lowercase
function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  if (/^\d+$/.test(s)) return s.padStart(2, '0')
  return s
}

function norm(s) {
  return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

// M\u00eame logique que SeriesDetailView.vue, pour un tri num\u00e9rique coh\u00e9rent des tomes ("T2" avant "T10")
function parseTomeNumber(n) {
  if (!n) return { hs: true, val: Infinity, raw: '' }
  const s = String(n).trim()
  const isHS = /^hs/i.test(s)
  const num = parseFloat(s.replace(/[^0-9.]/gi, ''))
  return { hs: isHS, val: isNaN(num) ? Infinity : num, raw: s }
}

// Champs Writer/Penciller/Publisher potentiellement multi-valeurs (s\u00e9par\u00e9es par virgule) \u2014
// correspondance exacte sur une des valeurs, pas une sous-cha\u00eene : sinon "Bamboo" matcherait
// aussi "Bamboo \u00c9ditions" (entit\u00e9 distincte).
function hasExact(field, target) {
  const q = norm(target)
  return (field || '').split(',').some(v => norm(v.trim()) === q)
}

const filteredTomes = computed(() => {
  let list = tomesStore.tomes

  // Search in title AND filename, accent-insensitive
  if (library.search.trim()) {
    const q = norm(library.search)
    list = list.filter(t =>
      norm(t.title).includes(q) || norm(t.filename).includes(q)
    )
  }

  // Letter filter
  if (activeLetter.value) {
    const name = (t) => norm(t.title || t.filename)
    if (activeLetter.value === '#') {
      list = list.filter(t => /^[^a-z]/.test(name(t)))
    } else {
      const l = norm(activeLetter.value)
      list = list.filter(t => name(t).startsWith(l))
    }
  }

  // Sans métadonnées
  if (library.filters.noMeta) {
    list = list.filter(t => !t.has_metadata)
  }

  // One-shot uniquement
  if (library.filters.oneshot) {
    list = list.filter(t => t.is_oneshot)
  }

  // Filtres auteur/éditeur/tag
  // Si writer et penciller ont la même valeur → OR (auteur polyvalent)
  if (library.filters.writer && library.filters.penciller && library.filters.writer === library.filters.penciller) {
    const target = library.filters.writer
    list = list.filter(t => hasExact(t.writer, target) || hasExact(t.penciller, target))
  } else {
    if (library.filters.writer)    list = list.filter(t => hasExact(t.writer, library.filters.writer))
    if (library.filters.penciller) list = list.filter(t => hasExact(t.penciller, library.filters.penciller))
  }
  if (library.filters.publisher) list = list.filter(t => hasExact(t.publisher, library.filters.publisher))
  if (library.filters.genre)     list = list.filter(t => hasExact(t.genre, library.filters.genre))
  if (library.filters.tag)       list = list.filter(t => (t.user_tags || []).some(tag => norm(tag).includes(norm(library.filters.tag))))
  if (library.filters.classification) list = list.filter(t => t.classification === library.filters.classification)

  // Filtre format
  if (library.filters.format)    list = list.filter(t => t.file_format === library.filters.format)

  // Note Bedetheque.com minimale (ex: 4 → 4 étoiles et plus)
  if (library.filters.rating)    list = list.filter(t => (t.community_rating || 0) >= library.filters.rating)

  // Sort
  const sorted = [...list]
  // Vue "albums d'un auteur/éditeur" (arrivée via clic depuis la page Auteurs) : toujours
  // triée par série puis numéro de tome, quel que soit le tri choisi sur la page Albums —
  // sinon les albums de plusieurs séries différentes apparaissent mélangés.
  const isAuthorOrPublisherView = !!(library.filters.writer || library.filters.penciller || library.filters.publisher)
  if (isAuthorOrPublisherView) {
    sorted.sort((a, b) => {
      const sc = norm(sortTitle(a.series_name || '')).localeCompare(norm(sortTitle(b.series_name || '')), 'fr')
      if (sc !== 0) return sc
      const pa = parseTomeNumber(a.number)
      const pb = parseTomeNumber(b.number)
      if (pa.hs !== pb.hs) return pa.hs ? 1 : -1
      if (pa.val !== pb.val) return pa.val - pb.val
      return pa.raw.localeCompare(pb.raw, 'fr', { numeric: true })
    })
    return sorted
  }

  const dir = library.sortDir === 'asc' ? 1 : -1
  if (library.sortBy === 'name') {
    sorted.sort((a, b) => dir * norm(a.title || a.filename).localeCompare(norm(b.title || b.filename), 'fr'))
  } else if (library.sortBy === 'added') {
    sorted.sort((a, b) => dir * (new Date(a.created_at ?? 0) - new Date(b.created_at ?? 0)))
  } else if (library.sortBy === 'updated') {
    sorted.sort((a, b) => dir * (new Date(a.updated_at ?? 0) - new Date(b.updated_at ?? 0)))
  } else if (library.sortBy === 'size') {
    sorted.sort((a, b) => dir * ((a.file_size ?? 0) - (b.file_size ?? 0)))
  } else if (library.sortBy === 'year') {
    sorted.sort((a, b) => dir * ((parseInt(a.year) || 0) - (parseInt(b.year) || 0)))
  }

  return sorted
})

const openScraperOnOpen = ref(false)

function editTome(tome) {
  selectedTome.value = tome
  openScraperOnOpen.value = false
  showMetadata.value = true
}

function searchTomeMetadata(tome) {
  selectedTome.value = tome
  openScraperOnOpen.value = true
  showMetadata.value = true
}
</script>

<template>
  <AppLayout>
    <ContentToolbar
      :count="filteredTomes.length"
      active-view="books"
      :active-letter="activeLetter"
      :filter-values="library.filters"
      :selection-active="selectedIds.size > 0"
      v-model:select-mode="selectMode"
      @letter="(l) => activeLetter = l"
      @filter-change="(f) => library.filters = f"
    >
      <template #selection>
        <span class="selection-count">{{ selectedIds.size }} album{{ selectedIds.size > 1 ? 's' : '' }} sélectionné{{ selectedIds.size > 1 ? 's' : '' }}</span>
        <button v-if="authStore.hasPermission('library.move')" class="btn btn-secondary btn-sm" @click="openMoveSelection">Déplacer</button>
        <button v-if="authStore.hasPermission('library.metadata_edit')" class="btn btn-secondary btn-sm" @click="showBulkEdit = true">Éditer…</button>
        <a v-if="authStore.hasPermission('library.download')" class="btn btn-secondary btn-sm" :href="tomesApi.downloadBulkUrl([...selectedIds])">Télécharger</a>
        <button v-if="authStore.hasPermission('library.delete')" class="btn btn-secondary btn-sm btn-danger-ghost" @click="confirmBulkDelete = true">Supprimer</button>
        <button class="btn btn-ghost btn-sm selection-cancel" @click="clearSelection">✕ Annuler la sélection</button>
      </template>
    </ContentToolbar>

    <main class="content-area">
      <div v-if="tomesStore.loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>
      <div v-else-if="filteredTomes.length === 0" class="state-box">
        <p class="state-desc">Aucun album trouvé</p>
      </div>
      <div v-else class="books-grid" :class="{ 'books-grid-select-mode': selectMode }">
        <div
          v-for="tome in filteredTomes"
          :key="tome.id"
          class="book-card"
          :class="{ 'book-card-hidden': tome.hidden || tome.series_hidden, 'book-card-selected': selectedIds.has(tome.id), 'menu-open': openMenuId === tome.id }"
          :title="tome.title || tome.filename"
        >
          <!-- Cover -->
          <div class="book-cover" @click="router.push(`/tomes/${tome.id}`)">
            <!-- Wrapper qui clippe l'image — laisse le menu "plus d'options" dépasser sans être coupé -->
            <div class="book-cover-clip">
              <img
                v-if="tome.cover_url"
                :src="tome.cover_url"
                :alt="tome.title"
                class="book-cover-img"
                loading="lazy"
                @error="$event.target.style.display='none'"
              />
              <div v-else class="book-cover-placeholder">📖</div>
              <div v-if="!selectedIds.has(tome.id)" class="book-cover-dim" :class="{ 'force-visible': openMenuId === tome.id }"></div>
            </div>

            <!-- Sélection multiple — retirée du DOM hors mode "Sélectionner", pas seulement
                 masquée, pour qu'un tap sur la zone (même invisible) ne puisse rien sélectionner. -->
            <button
              v-if="selectMode"
              class="book-select"
              :class="{ 'book-select-active': selectedIds.has(tome.id) }"
              :title="selectedIds.has(tome.id) ? 'Désélectionner' : 'Sélectionner'"
              @click.stop="toggleSelect(tome.id)"
            ></button>

            <!-- Number badge -->
            <span v-if="tome.is_oneshot" class="book-badge book-badge-oneshot">One-shot</span>
            <span v-else-if="tome.number" class="book-badge">T{{ fmtNumber(tome.number) }}</span>

            <!-- Hover overlay : icône lecture grande au centre, comme sur la page série —
                 masqué une fois l'album sélectionné, pour se concentrer sur la sélection. -->
            <div
              v-if="!selectedIds.has(tome.id)"
              class="book-overlay"
              :class="{ 'force-visible': openMenuId === tome.id }"
              @click.stop="router.push(`/read/${tome.id}`)"
            >
              <SvgIcon name="read" class="book-read-icon" />
              <button v-if="authStore.hasPermission('library.metadata_edit')" class="overlay-btn book-edit-btn" title="Modifier" @click.stop="editTome(tome)">
                <SvgIcon name="edit" style="font-size:20px" />
              </button>
              <div v-if="canTomeMenu" class="book-more-wrap" @click.stop>
                <button
                  class="overlay-btn book-more-btn"
                  :class="{ 'overlay-btn-active': openMenuId === tome.id }"
                  title="Plus d'options"
                  @click="toggleTomeMenu($event, tome.id)"
                >
                  <SvgIcon name="more-vertical" style="font-size:20px" />
                </button>
                <div v-if="openMenuId === tome.id" class="more-menu" :class="{ 'more-menu-left': menuLeft }">
                  <template v-if="authStore.hasPermission('library.metadata_edit')">
                    <button class="more-item" @click="editTome(tome); openMenuId = null">Éditer les métadonnées</button>
                    <button class="more-item" @click="searchTomeMetadata(tome); openMenuId = null">Rechercher les métadonnées</button>
                  </template>
                  <button v-if="authStore.hasPermission('library.move')" class="more-item" @click="openMoveSingle(tome); openMenuId = null">Déplacer vers une série</button>
                  <a v-if="authStore.hasPermission('library.download')" class="more-item" :href="tomesApi.downloadUrl(tome.id)" @click="openMenuId = null">Télécharger</a>
                  <div v-if="authStore.hasPermission('library.delete')" class="more-divider"></div>
                  <button v-if="authStore.hasPermission('library.delete')" class="more-item more-item-danger" @click="confirmDeleteTome = tome; openMenuId = null">Supprimer l'album</button>
                </div>
              </div>
            </div>

          </div>

          <!-- Info -->
          <div class="book-info" @click="router.push(`/tomes/${tome.id}`)">
            <p class="book-title">{{ tome.title || tome.filename }}</p>
            <p class="book-meta">
              <span v-if="tome.year" class="year-badge">{{ tome.year }}</span>
              <span v-if="tome.file_format !== 'cbz'" :class="['fmt-badge', `fmt-${tome.file_format}`]">{{ tome.file_format.toUpperCase() }}</span>
              <span v-if="tome.page_count" class="book-pages">{{ tome.page_count }} pages</span>
            </p>
          </div>
        </div>
      </div>
    </main>

    <!-- Metadata drawer -->
    <MetadataDrawer
      v-if="showMetadata && selectedTome"
      :tome="selectedTome"
      :open-scraper="openScraperOnOpen"
      @close="showMetadata = false"
      @saved="tomesStore.fetchAllTomes()"
      @deleted="tomesStore.fetchAllTomes()"
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
      @saved="clearSelection(); tomesStore.fetchAllTomes()"
    />

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
.content-area {
  flex: 1;
  padding: 16px 20px;
}

.selection-count { font-size: 0.82rem; font-weight: 600; color: var(--primary); margin-right: 4px; }
.selection-cancel { margin-left: auto; }

.books-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .books-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .books-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .books-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .books-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .books-grid { grid-template-columns: repeat(8, 1fr); } }

.book-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: visible;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
  position: relative;
  z-index: 1;
}
.book-card:hover {
  box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg);
  transform: translateY(-2px);
  /* Juste assez pour passer au-dessus des cards voisines (z-index:1) — jamais au-dessus
     de la barre du haut (z-index:40, sticky) sous peine de la traverser au survol. */
  z-index: 2;
}
.book-card.menu-open { z-index: 6; }

.book-cover {
  aspect-ratio: 0.71;
  position: relative;
  cursor: pointer;
  overflow: visible; /* laisse le menu "plus d'options" dépasser */
}

/* Wrapper qui clippe l'image — le reste de .book-cover reste visible pour le menu */
.book-cover-clip {
  position: absolute; inset: 0;
  overflow: hidden;
  border-radius: var(--radius) var(--radius) 0 0;
  background: var(--light);
}
.book-cover-img {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
  transition: transform 0.3s;
}
.book-card:hover .book-cover-img { transform: scale(1.04); }
.book-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 2rem; color: var(--placeholder);
}
.book-cover-dim {
  position: absolute; inset: 0; z-index: 2;
  background: rgba(0,0,0,0.45);
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
/* Le menu "plus d'options" reste ouvert même si la souris quitte la card — donc le fond
   sombre et l'overlay doivent rester visibles tant qu'il l'est, pas juste au survol. En
   mode sélection, rien à mettre en avant par-dessus : le fond sombre reste éteint. */
.book-card:hover .book-cover-dim,
.book-cover-dim.force-visible { opacity: 1; }
.books-grid-select-mode .book-cover-dim { opacity: 0 !important; }

.book-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}
.book-badge-oneshot { background: var(--vermilion); color: #fff; }
.books-grid-select-mode .book-badge { display: none; }

.book-select {
  position: absolute; top: 6px; left: 6px; z-index: 4;
  width: 19px; height: 19px; border-radius: 50%;
  /* Fond semi-opaque : un simple contour blanc se fondait dans les covers claires, surtout
     maintenant que la case reste affichée en permanence (mode "Sélectionner") et non plus
     seulement au survol. */
  background: rgba(0,0,0,0.4); border: 1.5px solid #fff;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
  cursor: pointer; padding: 0;
  display: flex; align-items: center; justify-content: center;
  transition: border-color 0.12s, background 0.12s, transform 0.1s;
}
.book-select:hover { transform: scale(1.15); }
.book-select-active { border-color: var(--vermilion); background: var(--vermilion); }
.book-select-active::after {
  content: '✓';
  color: #fff; font-size: 10px; font-weight: 700; line-height: 1;
}
.book-card-selected { box-shadow: 0 0 0 1.5px var(--primary); }

.book-overlay {
  position: absolute; inset: 0; z-index: 3;
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.book-card:hover .book-overlay,
.book-overlay.force-visible { opacity: 1; }
/* En mode sélection, on se concentre sur la case à cocher : les icônes Lire/Modifier/Plus
   disparaissent (et n'interceptent plus le tap, sinon un appui imprécis lancerait la lecture
   au lieu de sélectionner). */
.books-grid-select-mode .book-overlay { opacity: 0 !important; pointer-events: none; }

.book-read-icon {
  font-size: 48px; color: #fff;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
}
.book-edit-btn {
  position: absolute; bottom: 8px; left: 8px;
}

/* Menu "plus d'options" — en bas à droite de la cover, s'ouvre vers le bas */
.book-more-wrap { position: absolute; bottom: 8px; right: 8px; }
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

.book-info {
  padding: 7px 9px;
  border-top: 1px solid var(--border);
  cursor: pointer;
}
.book-title {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 4px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  /* Filet de sécurité : un titre très long pouvait laisser dépasser le haut d'une 3e ligne
     au lieu d'un troncage propre en "…" — max-height verrouille la hauteur à 2 lignes quoi
     qu'il arrive (ex. police pas encore chargée au premier rendu). */
  max-height: 2.7em;
}
.book-meta {
  display: flex; align-items: center; gap: 6px;
  min-width: 0;
}
/* Remplace le badge de format (quasi-toujours "CBZ", donc peu informatif) — le format ne
   reste affiché que pour CBR/PDF, seul cas où c'est réellement utile de le savoir au premier
   coup d'œil. Année plutôt que classification : toujours courte (jamais de troncature,
   contrairement à "BD franco-belge") et renseignée sur la majorité des albums. */
.year-badge {
  font-size: 0.65rem; font-weight: 700;
  padding: 1px 5px; border-radius: 3px;
  background: var(--light); color: var(--muted); border: 1px solid var(--border);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.fmt-badge {
  font-size: 0.65rem; font-weight: 700;
  padding: 1px 5px; border-radius: 3px;
}
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }
.book-pages { font-size: 0.72rem; color: var(--muted); }

.book-card-hidden .book-cover-img,
.book-card-hidden .book-cover-placeholder { opacity: 0.4; filter: grayscale(40%); }

/* States */
.state-box {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; min-height: 260px;
}
.state-desc  { font-size: 0.875rem; color: var(--muted); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }

.btn-danger-ghost { color: var(--danger); }
.btn-danger-ghost:hover { background: var(--danger-bg-light); }

.confirm-backdrop {
  position: fixed; inset: 0; z-index: 300;
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
