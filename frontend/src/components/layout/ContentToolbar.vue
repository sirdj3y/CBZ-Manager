<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLibraryStore } from '../../stores/library'
import { libraryApi } from '../../api/library'
import SvgIcon from '../SvgIcon.vue'
import AutocompleteInput from '../ui/AutocompleteInput.vue'

const props = defineProps({
  count: { type: Number, default: 0 },
  label: { type: String, default: 'éléments' },
  activeView: { type: String, default: 'series' }, // 'series' | 'books'
  activeLetter: { type: String, default: '' },
  showFilter: { type: Boolean, default: true },
  filterValues: { type: Object, default: () => ({}) },
  // Sélection multiple active : remplace la bande alphabet par le slot #selection, dans le
  // même emplacement — évite de décaler la grille en dessous en ajoutant une bande en plus.
  selectionActive: { type: Boolean, default: false },
})
const emit = defineEmits(['letter', 'filter-change'])

// Bouton "Sélectionner" — active/désactive l'affichage des cases de sélection sur les
// covers (SeriesCard/BooksView), sans quoi elles ne s'affichaient qu'au survol (jamais
// fiable au tactile) et encombraient inutilement la lecture des covers.
const selectMode = defineModel('selectMode', { default: false })

const router = useRouter()
const route = useRoute()
const library = useLibraryStore()

const ALPHABET = ['#', 'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']

// Barre alphabétique verticale (mobile) — glisser le doigt le long de la colonne pour
// naviguer en continu, en plus du tap sur une lettre. On retrouve sous le doigt l'élément
// réellement affiché à cette position (plutôt qu'un calcul de position par index/hauteur,
// fragile si l'espacement varie) et on n'émet que si la lettre a changé, pour ne pas
// spammer le filtrage à chaque pixel de mouvement.
let lastScrubKey = null
function emitLetterFromPoint(x, y) {
  const el = document.elementFromPoint(x, y)
  const btn = el?.closest('[data-alpha-key]')
  if (!btn) return
  const key = btn.dataset.alphaKey
  if (key === lastScrubKey) return
  lastScrubKey = key
  emit('letter', key === 'TOUT' ? '' : key)
}
function onAlphaVTouchStart(e) {
  lastScrubKey = null
  const t = e.touches[0]
  emitLetterFromPoint(t.clientX, t.clientY)
}
function onAlphaVTouchMove(e) {
  const t = e.touches[0]
  emitLetterFromPoint(t.clientX, t.clientY)
}
function onAlphaVTouchEnd() {
  lastScrubKey = null
}

const filterOpen = ref(false)
const filterWrapRef = ref(null)
const filterBtnRef = ref(null)
const filterDropdownRef = ref(null)
const filterPos = ref({ top: '0px', left: 'auto', right: '0px' })
const ratingHover = ref(0)

// Le menu est téléporté dans <body> en position:fixed (voir template) — .subbar doit
// pouvoir défiler horizontalement sur mobile (overflow-x:auto), ce qui clippe aussi
// verticalement tout ce qui dépasserait de sa propre boîte (règle CSS : un axe non-visible
// force l'autre à devenir "auto" lui aussi) — le dropdown ne peut donc plus rester un
// simple descendant en position:absolute sans être coupé. Même pattern que les autres
// menus "..." de l'app pour la même raison (voir CLAUDE.md).
function openFilter() {
  if (filterBtnRef.value) {
    const rect = filterBtnRef.value.getBoundingClientRect()
    const MARGIN = 8
    let right = window.innerWidth - rect.right
    if (right + 240 > window.innerWidth - MARGIN) right = MARGIN
    filterPos.value = { top: (rect.bottom + 6) + 'px', left: 'auto', right: right + 'px' }
  }
  filterOpen.value = !filterOpen.value
}

function onClickOutside(e) {
  if (filterOpen.value && !filterWrapRef.value?.contains(e.target) && !filterDropdownRef.value?.contains(e.target)) {
    filterOpen.value = false
  }
  if (sortOpen.value && !sortWrapRef.value?.contains(e.target) && !sortDropdownRef.value?.contains(e.target)) {
    sortOpen.value = false
  }
}
const classifications = ref([])

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
  // Nécessaire à l'autocomplétion des filtres Dessinateur/Scénariste/Éditeur ci-dessous —
  // ni SeriesView ni BooksView ne le déclenchent elles-mêmes (contrairement à la page
  // Auteurs ou à l'import).
  if (!library.authorNames.writers.length) library.fetchAuthors()
  libraryApi.getClassifications().then(({ data }) => { classifications.value = data }).catch(() => {})
})
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))

// Pool commun scénaristes + dessinateurs (dédupliqué) — même logique que MetadataForm/
// SeriesMetadataModal : un auteur polyvalent (ex. Peyo) apparaît dans les deux métiers.
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

// Critère de tri — le champ (Nom/Titre, Date d'ajout...) et la direction (croissant/
// décroissant) sont deux contrôles séparés dans le popup, plutôt qu'une seule liste
// combinant les deux comme avant ("Nom (A-Z)"). La liste des critères dépend de la vue :
// "Nombre d'albums" n'a pas de sens sur Albums, "Taille de fichier"/"Année de publication"
// n'ont pas de sens sur Séries.
const SORT_OPTIONS_SERIES = [
  { value: 'name',    label: 'Nom' },
  { value: 'tomes',   label: "Nombre d'albums" },
  { value: 'added',   label: "Date d'ajout" },
  { value: 'updated', label: 'Date de modification' },
]
const SORT_OPTIONS_BOOKS = [
  { value: 'name',    label: 'Titre' },
  { value: 'added',   label: "Date d'ajout" },
  { value: 'updated', label: 'Date de modification' },
  { value: 'size',    label: 'Taille de fichier' },
  { value: 'year',    label: 'Année de publication' },
]
const sortCriteria = computed(() => props.activeView === 'books' ? SORT_OPTIONS_BOOKS : SORT_OPTIONS_SERIES)

const sortField = computed({
  get: () => library.sortBy,
  set: (v) => { library.sortBy = v },
})
// Un critère valide sur une vue ("Taille de fichier" sur Albums) ne l'est pas forcément sur
// l'autre (Séries) — retombe sur "Nom/Titre", commun aux deux, plutôt que de garder un tri
// sélectionné mais silencieusement ignoré.
watch(() => props.activeView, () => {
  if (!sortCriteria.value.some(o => o.value === library.sortBy)) library.sortBy = 'name'
}, { immediate: true })
function toggleSortDir() {
  library.sortDir = library.sortDir === 'asc' ? 'desc' : 'asc'
}

const sortOpen = ref(false)
const sortWrapRef = ref(null)
const sortBtnRef = ref(null)
const sortDropdownRef = ref(null)
const sortPos = ref({ top: '0px', left: 'auto', right: '0px' })
function openSort() {
  if (sortBtnRef.value) {
    const rect = sortBtnRef.value.getBoundingClientRect()
    const MARGIN = 8
    let right = window.innerWidth - rect.right
    if (right + 220 > window.innerWidth - MARGIN) right = MARGIN
    sortPos.value = { top: (rect.bottom + 6) + 'px', left: 'auto', right: right + 'px' }
  }
  sortOpen.value = !sortOpen.value
}

const hasActiveFilters = computed(() =>
  !!(library.filters.writer || library.filters.penciller || library.filters.publisher ||
     library.filters.tag || library.filters.genre || library.filters.classification ||
     library.filters.noMeta || library.filters.oneshot ||
     library.filters.format || library.showHidden)
)
</script>

<template>
  <!-- Sub-toolbar : titre+compteur (gauche, fixe) / bande alphabet (centre, défile seule si
       à l'étroit) / switch+tri+filtre (droite, fixe — jamais poussés hors champ). -->
  <div class="subbar">
    <!-- Left: count -->
    <div class="subbar-left">
      <span class="subbar-title">{{ activeView === 'books' ? 'Albums' : 'Séries' }}</span>
      <span class="subbar-count">{{ count }}</span>
    </div>

    <!-- Center: alphabet bar / barre de sélection — même emplacement, jamais les deux en
         même temps. -->
    <div class="alpha-bar" :class="{ 'alpha-bar-selection': selectionActive }">
      <slot v-if="selectionActive" name="selection" />
      <template v-else>
        <button
          :class="['alpha-btn', { 'alpha-btn-active': activeLetter === '' }]"
          @click="$emit('letter', '')"
        >TOUT</button>
        <button
          v-for="letter in ALPHABET"
          :key="letter"
          :class="['alpha-btn', { 'alpha-btn-active': activeLetter === letter }]"
          @click="$emit('letter', letter)"
        >{{ letter }}</button>
      </template>
    </div>

    <!-- Right: view toggle + filter -->
    <div class="subbar-right">
      <div class="view-toggle">
        <button
          @click="router.push('/series')"
          :class="['view-btn', { 'view-btn-active': activeView === 'series' }]"
        >SÉRIES</button>
        <button
          @click="router.push('/books')"
          :class="['view-btn', { 'view-btn-active': activeView === 'books' }]"
        >ALBUMS</button>
      </div>

      <!-- Sort -->
      <div class="sort-wrap" ref="sortWrapRef">
        <button
          ref="sortBtnRef"
          type="button"
          @click="openSort"
          :class="['btn btn-ghost btn-icon btn-sm sort-btn', { 'sort-btn-active': sortOpen }]"
          title="Trier"
        >
          <SvgIcon name="arrow-up-down" style="font-size:14px" />
        </button>
      </div>

      <!-- Filter button -->
      <div class="filter-wrap" v-if="showFilter" ref="filterWrapRef">
        <button
          ref="filterBtnRef"
          @click="openFilter"
          :class="['btn btn-ghost btn-icon btn-sm filter-btn', { 'filter-btn-active': filterOpen || hasActiveFilters }]"
          title="Filtrer"
        >
          <SvgIcon :name="hasActiveFilters ? 'filter-off' : 'filter'" style="font-size:14px" :key="hasActiveFilters ? 'off' : 'on'" />
        </button>
      </div>

      <!-- Sélectionner -->
      <button
        type="button"
        :class="['select-mode-btn', { 'select-mode-btn-active': selectMode }]"
        :aria-pressed="selectMode"
        title="Sélectionner"
        @click="selectMode = !selectMode"
      >
        <span class="select-mode-box">
          <span v-if="selectMode" class="select-mode-check">✓</span>
        </span>
        <span class="select-mode-label">Sélectionner</span>
      </button>
    </div>

    <!-- Sort dropdown — même contrainte que le filtre : téléporté en position:fixed. -->
    <Teleport to="body">
      <div v-if="sortOpen" ref="sortDropdownRef" class="filter-dropdown sort-dropdown" :style="sortPos" @click.stop>
        <div class="filter-header">
          <span>Trier par</span>
        </div>
        <div class="sort-field-row">
          <select v-model="sortField" class="form-control">
            <option v-for="o in sortCriteria" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <button
            type="button"
            class="sort-dir-btn"
            @click="toggleSortDir"
            :title="library.sortDir === 'asc' ? 'Croissant' : 'Décroissant'"
          >
            <SvgIcon :name="library.sortDir === 'asc' ? 'arrow-down-a-z' : 'arrow-down-z-a'" style="font-size:16px" />
          </button>
        </div>
      </div>
    </Teleport>

    <!-- Filter dropdown — téléporté en position:fixed (voir openFilter) : .subbar défile
         horizontalement sur mobile, ce qui clippe verticalement tout descendant en
         position:absolute qui en dépasserait. -->
    <Teleport to="body">
      <div v-if="filterOpen" ref="filterDropdownRef" class="filter-dropdown" :style="filterPos" @click.stop>
        <div class="filter-header">
          <span>Filtres</span>
          <button class="btn btn-ghost btn-sm" @click="library.filters = { format: '' }; library.showHidden = false; filterOpen = false">Effacer</button>
        </div>
        <div class="filter-group">
          <label class="form-label">Dessinateur</label>
          <AutocompleteInput
            v-model="library.filters.penciller"
            :suggestions="authorPool"
            placeholder="ex: Uderzo"
          />
        </div>
        <div class="filter-group">
          <label class="form-label">Scénariste</label>
          <AutocompleteInput
            v-model="library.filters.writer"
            :suggestions="authorPool"
            placeholder="ex: Goscinny"
          />
        </div>
        <div class="filter-group">
          <label class="form-label">Éditeur</label>
          <AutocompleteInput
            v-model="library.filters.publisher"
            :suggestions="library.authorNames.publishers"
            placeholder="ex: Dargaud"
          />
        </div>
        <div class="filter-group">
          <label class="form-label">Étiquette</label>
          <AutocompleteInput
            v-model="library.filters.tag"
            :suggestions="library.authorNames.tags"
            placeholder="ex: Favori"
          />
        </div>
        <div class="filter-group">
          <label class="form-label">Genre</label>
          <AutocompleteInput
            v-model="library.filters.genre"
            :suggestions="library.authorNames.genres"
            placeholder="ex: Humour"
          />
        </div>
        <div class="filter-group">
          <label class="form-label">Classification</label>
          <select v-model="library.filters.classification" class="form-control">
            <option value="">Toutes</option>
            <option v-for="c in classifications" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="form-label">Format</label>
          <div class="format-btns">
            <button
              v-for="fmt in ['cbz', 'cbr', 'pdf']"
              :key="fmt"
              :class="['fmt-btn', `fmt-btn-${fmt}`, { 'fmt-btn-active': library.filters.format === fmt }]"
              @click="library.filters.format = library.filters.format === fmt ? '' : fmt"
            >{{ fmt.toUpperCase() }}</button>
          </div>
        </div>
        <div v-if="activeView === 'books'" class="filter-group">
          <label class="form-label">Note Bedetheque.com minimale</label>
          <div class="rating-btns" @mouseleave="ratingHover = 0">
            <button
              v-for="n in [1,2,3,4,5]"
              :key="n"
              type="button"
              class="rating-star-btn"
              :class="{ filled: n <= (ratingHover || library.filters.rating || 0) }"
              :title="n + ' étoile' + (n > 1 ? 's' : '') + ' et plus'"
              @mouseenter="ratingHover = n"
              @click="library.filters.rating = library.filters.rating === n ? 0 : n"
            >★</button>
          </div>
        </div>
        <div class="filter-group filter-group-toggle">
          <label class="toggle-label">
            <input type="checkbox" v-model="library.filters.noMeta" class="toggle-checkbox" />
            <span>Sans métadonnées uniquement</span>
          </label>
          <label v-if="activeView === 'books'" class="toggle-label" style="margin-top: 8px">
            <input type="checkbox" v-model="library.filters.oneshot" class="toggle-checkbox" />
            <span>One-shot uniquement</span>
          </label>
          <label class="toggle-label" style="margin-top: 8px">
            <input type="checkbox" v-model="library.showHidden" class="toggle-checkbox" />
            <span>Afficher les séries masquées</span>
          </label>
        </div>
      </div>
    </Teleport>
  </div>

  <!-- Version mobile : colonne fixe sur le bord droit, tap ou glisser pour naviguer —
       masquée en sélection (le slot #selection ci-dessus reste alors visible à sa place
       habituelle). Voir .alpha-bar-vertical (display:none hors mobile) dans le style. -->
  <div
    v-if="!selectionActive"
    class="alpha-bar-vertical"
    @touchstart.prevent="onAlphaVTouchStart"
    @touchmove.prevent="onAlphaVTouchMove"
    @touchend="onAlphaVTouchEnd"
  >
    <button
      :class="['alpha-v-btn', { 'alpha-btn-active': activeLetter === '' }]"
      data-alpha-key="TOUT"
      title="Tout afficher"
      @click="$emit('letter', '')"
    >•</button>
    <button
      v-for="letter in ALPHABET"
      :key="letter"
      :class="['alpha-v-btn', { 'alpha-btn-active': activeLetter === letter }]"
      :data-alpha-key="letter"
      @click="$emit('letter', letter)"
    >{{ letter }}</button>
  </div>
</template>

<style scoped>
/* ── Subbar ── */
/* Trois zones : gauche (titre+compteur, fixe) / centre (bande alphabet, seule à défiler en
   interne si la place manque) / droite (toggle+tri+filtre, fixe — jamais poussés hors champ,
   contrairement à un simple overflow-x sur toute la barre). */
.subbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  height: 44px;
  /* Pas de fond ni de séparation propres : la barre s'intègre visuellement à la page,
     comme la grille de covers juste en dessous, plutôt que de former un bandeau à part. */
  flex-shrink: 0;
  /* Filet de sécurité sur très petit écran (bande alphabet masquée, voir media query) si
     titre+compteur+toggle+tri+filtre dépassent malgré tout. */
  overflow-x: auto;
  scrollbar-width: none;
}
.subbar::-webkit-scrollbar { height: 0; }

.subbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.subbar-title {
  font-family: var(--font-display);
  font-weight: 400;
  text-transform: uppercase;
  font-size: 0.95rem;
  color: var(--text);
  white-space: nowrap;
}

.subbar-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 20px;
  padding: 0 6px;
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text);
}

/* View toggle */
.subbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.view-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.view-btn {
  padding: 3px 8px;
  font-size: 0.68rem;
  font-weight: 700;
  font-family: var(--font);
  letter-spacing: 0.03em;
  background: var(--surface);
  border: none;
  border-right: 1px solid var(--border);
  cursor: pointer;
  color: var(--muted);
  transition: background 0.12s, color 0.12s;
}
.view-btn:last-child { border-right: none; }
.view-btn:hover { background: var(--light); color: var(--text); }
.view-btn-active { background: var(--primary); color: #fff; }
.view-btn-active:hover { background: var(--primary-dark); color: #fff; }

/* Sort */
.sort-wrap { position: relative; }
.sort-btn { color: var(--muted); width: 26px; height: 26px; padding: 0; justify-content: center; }
.sort-btn-active { background: var(--primary-light) !important; color: var(--primary) !important; }

.sort-dropdown { width: 200px; }
.sort-field-row { display: flex; align-items: center; gap: 6px; }
.sort-field-row .form-control { flex: 1; min-width: 0; }
.sort-dir-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 30px; height: 30px;
  color: var(--text);
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.sort-dir-btn:hover { background: var(--surface); border-color: var(--primary-focus-border); }

/* Filter button + dropdown */
.filter-wrap { position: relative; }

.filter-btn { color: var(--muted); width: 26px; height: 26px; padding: 0; justify-content: center; }
.filter-btn-active { background: var(--primary-light) !important; color: var(--primary) !important; }

/* Bouton "Sélectionner" */
.select-mode-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 3px 8px;
  font-size: 0.68rem;
  font-weight: 600;
  font-family: var(--font);
  white-space: nowrap;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--muted);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.select-mode-btn:hover { background: var(--light); color: var(--text); }
.select-mode-btn-active { background: var(--primary-light); color: var(--primary); border-color: var(--primary); }
.select-mode-box {
  width: 13px; height: 13px;
  flex-shrink: 0;
  border-radius: 3px;
  border: 1.5px solid currentColor;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, border-color 0.12s;
}
.select-mode-btn-active .select-mode-box { background: var(--primary); border-color: var(--primary); }
.select-mode-check { color: #fff; font-size: 9px; font-weight: 700; line-height: 1; }

.filter-dropdown {
  position: fixed;
  z-index: 200;
  width: 240px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rating-btns { display: flex; gap: 4px; }
.rating-star-btn {
  background: none; border: none; cursor: pointer; padding: 0;
  font-size: 1.3rem; line-height: 1; color: var(--border);
  transition: color 0.12s, transform 0.12s;
}
.rating-star-btn:hover { transform: scale(1.15); }
.rating-star-btn.filled { color: var(--star-filled, #f59e0b); }

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.875rem;
  font-weight: 600;
}

.filter-group { display: flex; flex-direction: column; }
.filter-group-toggle { padding-top: 4px; border-top: 1px solid var(--border); }

.format-btns { display: flex; gap: 6px; margin-top: 4px; }
.fmt-btn {
  flex: 1; padding: 4px 0;
  font-size: 0.7rem; font-weight: 700; font-family: var(--font);
  border-radius: var(--radius-sm); border: 1px solid var(--border);
  cursor: pointer; background: var(--light); color: var(--muted);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.fmt-btn:hover { background: var(--surface); color: var(--text); }
.fmt-btn-active.fmt-btn-cbz { background: var(--success-bg); color: var(--success-text); border-color: var(--success-border); }
.fmt-btn-active.fmt-btn-cbr { background: var(--warning-bg); color: var(--orange-bar); border-color: var(--warning-bg); }
.fmt-btn-active.fmt-btn-pdf { background: var(--info-bg); color: var(--info-text); border-color: var(--info-bg); }
.toggle-label {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.8125rem; color: var(--text); cursor: pointer;
}
.toggle-checkbox { accent-color: var(--primary); flex-shrink: 0; }

/* ── Alphabet bar ── */
/* Zone centrale de .subbar : prend toute la place restante entre le titre et les contrôles
   de droite, et défile SEULE en interne si les lettres ne tiennent pas — le titre à gauche
   et le toggle/tri/filtre à droite restent, eux, toujours fixes et accessibles. */
.alpha-bar {
  display: flex;
  align-items: center;
  gap: 0;
  margin-left: 10px;
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  overflow-x: auto;
  scrollbar-width: none;
}
.alpha-bar::-webkit-scrollbar { height: 0; }
.alpha-bar-selection {
  background: var(--primary-light);
  border-radius: var(--radius-sm);
  gap: 10px;
  padding: 0 10px;
}

.alpha-btn {
  flex-shrink: 0;
  padding: 0 4px;
  height: 24px;
  font-size: 0.68rem;
  font-weight: 600;
  font-family: var(--font);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--muted);
  transition: background 0.1s, color 0.1s;
}
.alpha-btn:hover { background: var(--light); color: var(--text); }
.alpha-btn-active { background: var(--primary); color: #fff; }

/* Colonne verticale (mobile uniquement) — cachée par défaut, activée par le média-query
   ci-dessous. En sélection, .alpha-bar reste affichée pour son slot #selection : on ne
   masque donc .alpha-bar que quand elle n'a pas cette classe. */
.alpha-bar-vertical {
  display: none;
  flex-direction: column; align-items: center;
  position: fixed; right: 4px; top: 50%; transform: translateY(-50%);
  z-index: 15;
  padding: 4px 2px;
  max-height: 70vh; overflow-y: auto;
  scrollbar-width: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow-sm);
}
.alpha-bar-vertical::-webkit-scrollbar { width: 0; }
.alpha-v-btn {
  flex-shrink: 0;
  width: 20px; height: 18px;
  font-size: 0.62rem;
  font-weight: 600;
  font-family: var(--font);
  background: none;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--muted);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.1s, color 0.1s;
}

@media (max-width: 768px) {
  .alpha-bar:not(.alpha-bar-selection) { display: none; }
  .alpha-bar-vertical { display: flex; }
}

@media (max-width: 480px) {
  /* Ne garder que la case à cocher, le libellé "Sélectionner" prend trop de place. */
  .select-mode-label { display: none; }
  .select-mode-btn { padding: 3px 6px; }
}

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 0.9s linear infinite; }
</style>
