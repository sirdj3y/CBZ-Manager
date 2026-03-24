<script setup>
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNav from '../components/layout/AppNav.vue'
import SeriesGrid from '../components/library/SeriesGrid.vue'
import AutocompleteInput from '../components/ui/AutocompleteInput.vue'
import { useLibraryStore } from '../stores/library'

const library = useLibraryStore()
const route = useRoute()
const router = useRouter()

const SORT_OPTIONS = [
  { value: 'name',    label: 'Nom (A→Z)' },
  { value: 'tomes',   label: 'Nb de tomes' },
  { value: 'added',   label: 'Date d\'ajout' },
  { value: 'updated', label: 'Mis à jour' },
]

const activeFilterLabel = computed(() => {
  const f = library.filters
  if (f.writer)    return `Scénariste : ${f.writer}`
  if (f.penciller) return `Dessinateur : ${f.penciller}`
  if (f.publisher) return `Éditeur : ${f.publisher}`
  return null
})

function clearFilter() {
  library.filters = {}
  router.replace('/series')
}

onMounted(async () => {
  // Appliquer les filtres depuis les query params
  const { writer, penciller, publisher } = route.query
  if (writer || penciller || publisher) {
    library.filters = {
      ...(writer    ? { writer }    : {}),
      ...(penciller ? { penciller } : {}),
      ...(publisher ? { publisher } : {}),
    }
  } else {
    library.filters = {}
  }
  if (library.series.length === 0) await library.fetchSeries()
  if (!library.authors.writers.length) library.fetchAuthors()
})
</script>

<template>
  <div class="library-page">
    <AppNav />

    <!-- Scan progress bar -->
    <div v-if="library.scanProgress.status === 'running'" class="scan-progress-bar">
      <div
        class="scan-progress-fill"
        :style="{ width: library.scanProgress.total ? `${(library.scanProgress.processed / library.scanProgress.total) * 100}%` : '0%' }"
      />
    </div>

    <div class="library-body">
      <!-- Sidebar gauche -->
      <aside class="library-sidebar">
        <div class="sidebar-section">
          <p class="sidebar-label">Bibliothèque</p>
          <div class="sidebar-count">
            {{ library.filteredSeries.length }}
            <span>{{ library.filteredSeries.length === 1 ? 'série' : 'séries' }}</span>
          </div>
        </div>

        <div class="sidebar-section">
          <p class="sidebar-label">Filtrer par</p>
          <div class="sidebar-filters">
            <AutocompleteInput
              :model-value="library.filters.writer || ''"
              :suggestions="library.authorNames.writers"
              placeholder="Scénariste…"
              @update:model-value="v => { library.filters = { ...library.filters, writer: v || undefined } }"
            />
            <AutocompleteInput
              :model-value="library.filters.penciller || ''"
              :suggestions="library.authorNames.pencillers"
              placeholder="Dessinateur…"
              @update:model-value="v => { library.filters = { ...library.filters, penciller: v || undefined } }"
            />
            <AutocompleteInput
              :model-value="library.filters.publisher || ''"
              :suggestions="library.authorNames.publishers"
              placeholder="Éditeur…"
              @update:model-value="v => { library.filters = { ...library.filters, publisher: v || undefined } }"
            />
          </div>
        </div>

        <div class="sidebar-section">
          <p class="sidebar-label">Trier par</p>
          <div class="sidebar-sort">
            <button
              v-for="opt in SORT_OPTIONS"
              :key="opt.value"
              @click="library.sortBy = opt.value"
              :class="['sort-btn', { 'sort-btn-active': library.sortBy === opt.value }]"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </aside>

      <!-- Contenu principal -->
      <main class="library-main">
        <!-- Barre de filtre -->
        <div class="library-toolbar">
          <div v-if="activeFilterLabel" class="filter-chip">
            <span>{{ activeFilterLabel }}</span>
            <button class="filter-chip-clear" @click="clearFilter" title="Effacer le filtre">✕</button>
          </div>
          <div class="toolbar-search">
            <input
              v-model="library.search"
              type="search"
              placeholder="Filtrer les séries…"
              class="form-control"
            />
          </div>
        </div>

        <!-- Loading -->
        <div v-if="library.loading" class="state-box">
          <span class="state-text loading-pulse">Chargement…</span>
        </div>

        <!-- Empty state -->
        <div v-else-if="library.filteredSeries.length === 0 && !library.search" class="state-box">
          <div class="state-icon">📚</div>
          <p class="state-title">Bibliothèque vide</p>
          <p class="state-desc">Configurez le chemin de la bibliothèque et lancez un scan.</p>
        </div>

        <!-- No results -->
        <div v-else-if="library.filteredSeries.length === 0" class="state-box">
          <p class="state-text">Aucune série pour "{{ library.search }}"</p>
        </div>

        <!-- Grid -->
        <SeriesGrid v-else :series="library.filteredSeries" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.library-page {
  min-height: 100vh;
  background-color: var(--light);
  display: flex;
  flex-direction: column;
}

.scan-progress-bar {
  height: 3px;
  background-color: var(--border);
  flex-shrink: 0;
}
.scan-progress-fill {
  height: 100%;
  background-color: var(--primary);
  transition: width 0.3s ease;
}

/* Layout principal : sidebar + contenu */
.library-body {
  display: flex;
  flex: 1;
}

/* ---- Sidebar ---- */
.library-sidebar {
  width: 200px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  position: sticky;
  top: 56px; /* hauteur navbar */
  height: calc(100vh - 56px);
  overflow-y: auto;
}

.sidebar-section { display: flex; flex-direction: column; gap: 8px; }

.sidebar-label {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}

.sidebar-count {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}
.sidebar-count span {
  font-size: 0.8125rem;
  font-weight: 400;
  color: var(--muted);
  margin-left: 4px;
}

.sidebar-filters {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-sort {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sort-btn {
  text-align: left;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  border: none;
  background: none;
  font-size: 0.8125rem;
  font-family: var(--font);
  color: var(--text);
  cursor: pointer;
  transition: background-color 0.12s, color 0.12s;
}
.sort-btn:hover { background-color: var(--light); }
.sort-btn-active {
  background-color: var(--primary-light);
  color: var(--primary);
  font-weight: 500;
}

/* ---- Contenu ---- */
.library-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.library-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px 0;
}

.filter-chip {
  display: flex; align-items: center; gap: 6px;
  background: var(--primary-light); color: var(--primary);
  border: 1px solid var(--primary); border-radius: 20px;
  padding: 3px 10px 3px 12px; font-size: 0.8125rem; font-weight: 500;
}
.filter-chip-clear {
  background: none; border: none; cursor: pointer;
  color: var(--primary); font-size: 0.85rem; line-height: 1;
  padding: 0 2px; opacity: 0.7;
}
.filter-chip-clear:hover { opacity: 1; }

.toolbar-search {
  width: 280px;
}
.toolbar-search .form-control {
  font-size: 0.875rem;
  padding: 6px 12px;
}

/* States */
.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 280px;
  padding: 40px 20px;
}
.state-icon { font-size: 3.5rem; }
.state-title { font-size: 1.1rem; font-weight: 600; color: var(--text); }
.state-desc  { font-size: 0.875rem; color: var(--muted); text-align: center; }
.state-text  { font-size: 0.9rem; color: var(--muted); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.loading-pulse { animation: pulse 1.4s ease-in-out infinite; }
</style>
