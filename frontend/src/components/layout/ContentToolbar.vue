<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLibraryStore } from '../../stores/library'
import SvgIcon from '../SvgIcon.vue'

const props = defineProps({
  count: { type: Number, default: 0 },
  label: { type: String, default: 'éléments' },
  activeView: { type: String, default: 'series' }, // 'series' | 'books'
  activeLetter: { type: String, default: '' },
  showFilter: { type: Boolean, default: true },
  filterValues: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['letter', 'filter-change'])

const router = useRouter()
const route = useRoute()
const library = useLibraryStore()

const ALPHABET = ['#', 'A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']

const filterOpen = ref(false)
const filterWrapRef = ref(null)

function onClickOutside(e) {
  if (filterOpen.value && filterWrapRef.value && !filterWrapRef.value.contains(e.target)) {
    filterOpen.value = false
  }
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))

const SORT_OPTIONS = [
  { value: 'name:asc',     label: 'Nom (A-Z)' },
  { value: 'name:desc',    label: 'Nom (Z-A)' },
  { value: 'tomes:desc',   label: 'Plus grande série' },
  { value: 'tomes:asc',    label: 'Plus petite série' },
  { value: 'added:desc',   label: 'Ajout récent' },
  { value: 'added:asc',    label: 'Ajout ancien' },
  { value: 'updated:desc', label: 'Mis à jour récent' },
  { value: 'updated:asc',  label: 'Mis à jour ancien' },
]

const sortValue = computed({
  get: () => `${library.sortBy}:${library.sortDir}`,
  set: (val) => {
    const [by, dir] = val.split(':')
    library.sortBy = by
    library.sortDir = dir
  }
})

const hasActiveFilters = computed(() =>
  !!(library.filters.writer || library.filters.penciller || library.filters.publisher ||
     library.filters.tag || library.filters.noMeta || library.filters.format || library.showHidden)
)
</script>

<template>
  <!-- Sub-toolbar -->
  <div class="subbar">
    <!-- Left: count -->
    <div class="subbar-left">
      <span class="subbar-title">Bandes dessinées</span>
      <span class="subbar-count">{{ count }}</span>
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
      <div class="sort-select-wrap">
        <select v-model="sortValue" class="sort-select">
          <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>

      <!-- Filter button -->
      <div class="filter-wrap" v-if="showFilter" ref="filterWrapRef">
        <button
          @click="filterOpen = !filterOpen"
          :class="['btn btn-ghost btn-icon btn-sm filter-btn', { 'filter-btn-active': filterOpen || hasActiveFilters }]"
          title="Filtrer"
        >
          <SvgIcon :name="hasActiveFilters ? 'filter-off' : 'filter'" style="font-size:16px" :key="hasActiveFilters ? 'off' : 'on'" />
        </button>

        <!-- Filter dropdown -->
        <div v-if="filterOpen" class="filter-dropdown" @click.stop>
          <div class="filter-header">
            <span>Filtres</span>
            <button class="btn btn-ghost btn-sm" @click="library.filters = { format: '' }; library.showHidden = false; filterOpen = false">Effacer</button>
          </div>
          <div class="filter-group">
            <label class="form-label">Scénariste</label>
            <input v-model="library.filters.writer" type="text" class="form-control" placeholder="ex: Goscinny" />
          </div>
          <div class="filter-group">
            <label class="form-label">Dessinateur</label>
            <input v-model="library.filters.penciller" type="text" class="form-control" placeholder="ex: Uderzo" />
          </div>
          <div class="filter-group">
            <label class="form-label">Éditeur</label>
            <input v-model="library.filters.publisher" type="text" class="form-control" placeholder="ex: Dargaud" />
          </div>
          <div class="filter-group">
            <label class="form-label">Étiquette</label>
            <input v-model="library.filters.tag" type="text" class="form-control" placeholder="ex: Favori" />
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
          <div class="filter-group filter-group-toggle">
            <label class="toggle-label">
              <input type="checkbox" v-model="library.filters.noMeta" class="toggle-checkbox" />
              <span>Sans métadonnées uniquement</span>
            </label>
            <label class="toggle-label" style="margin-top: 8px">
              <input type="checkbox" v-model="library.showHidden" class="toggle-checkbox" />
              <span>Afficher les séries masquées</span>
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Alphabet bar -->
  <div class="alpha-bar">
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
  </div>
</template>

<style scoped>
/* ── Subbar ── */
.subbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 20px;
  height: 48px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.subbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.subbar-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}

.subbar-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 22px;
  padding: 0 7px;
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text);
}

/* View toggle */
.subbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.view-btn {
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 700;
  font-family: var(--font);
  letter-spacing: 0.06em;
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

/* Sort select */
.sort-select-wrap { position: relative; }
.sort-select {
  padding: 4px 28px 4px 10px;
  font-size: 0.8125rem; font-family: var(--font);
  color: var(--text);
  background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23757575'/%3E%3C/svg%3E") no-repeat right 8px center;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  appearance: none; cursor: pointer;
}
.sort-select:focus { outline: none; border-color: var(--primary-focus-border); }

/* Filter button + dropdown */
.filter-wrap { position: relative; }

.filter-btn { color: var(--muted); }
.filter-btn-active { background: var(--primary-light) !important; color: var(--primary) !important; }

.filter-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
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
.alpha-bar {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0 16px;
  height: 34px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
}
.alpha-bar::-webkit-scrollbar { height: 0; }

.alpha-btn {
  flex-shrink: 0;
  padding: 0 6px;
  height: 28px;
  font-size: 0.75rem;
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

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 0.9s linear infinite; }
</style>
