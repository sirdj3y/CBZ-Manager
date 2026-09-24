<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { useLibraryStore } from '../stores/library'
import { libraryApi } from '../api/library'
import { useNotificationStore } from '../stores/notifications'

const router = useRouter()
const library = useLibraryStore()
const notif = useNotificationStore()

const activeTab = ref('authors')
const sortKey = ref('name')
const sortDir = ref('asc')
const nameFilter = ref('')

const TABS = [
  { key: 'authors',    label: 'Auteurs' },
  { key: 'publishers', label: 'Éditeurs' },
]

const COLS = [
  { key: 'name',   label: 'Nom' },
  { key: 'series', label: 'Séries' },
  { key: 'tomes',  label: 'Albums' },
]

const TIER_LABELS = {
  1: { text: 'Casse/accents différents', cls: 'tier-1' },
  2: { text: 'Mêmes mots, ordre différent', cls: 'tier-2' },
  3: { text: 'À vérifier', cls: 'tier-3' },
}

const duplicates = ref({ authors: [], publishers: [] })
const duplicatesOpen = ref(false)
// clé = signature du groupe (nom_kind + variantes triées), stable même si la liste
// détectée change d'ordre ou de longueur d'un chargement à l'autre.
const targetChoice = reactive({})
const merging = reactive(new Set())

function groupKey(kind, group) {
  return `${kind}:${group.variants.map(v => v.name).slice().sort().join('|')}`
}

// Groupes ignorés par l'utilisateur — suggestion masquée mais jamais perdue (réaffichable),
// mémorisée localement au navigateur : c'est une préférence d'affichage, pas une donnée
// de bibliothèque, inutile de la stocker en base.
const IGNORED_KEY = 'cbz-manager:ignoredDuplicateGroups'
function loadIgnored() {
  try { return new Set(JSON.parse(localStorage.getItem(IGNORED_KEY) || '[]')) }
  catch { return new Set() }
}
function saveIgnored(set) {
  localStorage.setItem(IGNORED_KEY, JSON.stringify([...set]))
}
const ignoredGroups = ref(loadIgnored())

function ignoreGroup(kind, group) {
  const next = new Set(ignoredGroups.value)
  next.add(groupKey(kind, group))
  ignoredGroups.value = next
  saveIgnored(next)
}

function restoreIgnoredForTab() {
  const next = new Set(ignoredGroups.value)
  for (const key of next) {
    if (key.startsWith(`${activeTab.value}:`)) next.delete(key)
  }
  ignoredGroups.value = next
  saveIgnored(next)
}

const visibleDuplicates = computed(() =>
  (duplicates.value[activeTab.value] || []).filter(g => !ignoredGroups.value.has(groupKey(activeTab.value, g)))
)
const ignoredCountForTab = computed(() =>
  (duplicates.value[activeTab.value] || []).length - visibleDuplicates.value.length
)

function loadDuplicates() {
  libraryApi.getAuthorDuplicates().then(({ data }) => {
    duplicates.value = data
  })
}

async function mergeGroup(kind, group) {
  const key = groupKey(kind, group)
  const target = (targetChoice[key] || group.variants[0].name).trim()
  if (!target) return
  merging.add(key)
  try {
    const { data } = await libraryApi.mergeAuthors(
      kind === 'authors' ? 'author' : 'publisher',
      group.variants.map(v => v.name),
      target
    )
    if (data.errors) notif.error(`${data.errors} erreur(s) pendant la fusion`)
    else notif.success(`Fusionné — ${data.merged} album(s) mis à jour`)
    library.fetchAuthors()
    loadDuplicates()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la fusion')
  } finally {
    merging.delete(key)
  }
}

onMounted(() => {
  if (!library.authors.authors.length) library.fetchAuthors()
  loadDuplicates()
})

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'name' ? 'asc' : 'desc'
  }
}

// "Trier par" — même toolbar que la page Albums manquants, mappée sur les mêmes sortKey/
// sortDir que les en-têtes de colonnes cliquables (deux façons d'accéder au même état).
const SORT_OPTIONS = [
  { value: 'name-asc', label: 'Nom (A → Z)' },
  { value: 'name-desc', label: 'Nom (Z → A)' },
  { value: 'series-desc', label: 'Séries (plus nombreuses)' },
  { value: 'tomes-desc', label: 'Albums (plus nombreux)' },
]
const sortSelect = computed({
  get: () => `${sortKey.value}-${sortDir.value}`,
  set: (v) => {
    const [key, dir] = v.split('-')
    sortKey.value = key
    sortDir.value = dir
  },
})

const filtered = computed(() => {
  const list = library.authors[activeTab.value] || []
  const q = library.search.trim().toLowerCase()
  const nq = nameFilter.value.trim().toLowerCase()
  let base = q ? list.filter(a => a.name.toLowerCase().includes(q)) : [...list]
  if (nq) base = base.filter(a => a.name.toLowerCase().includes(nq))
  const k = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return base.sort((a, b) => {
    if (k === 'name') return dir * a.name.localeCompare(b.name)
    return dir * ((a[k] || 0) - (b[k] || 0))
  })
})

function goToLibrary(name) {
  const n = encodeURIComponent(name)
  if (activeTab.value === 'publishers') {
    router.push(`/books?publisher=${n}`)
  } else {
    router.push(`/books?writer=${n}&penciller=${n}`)
  }
}
</script>

<template>
  <AppLayout>
    <main class="authors-main">
      <!-- Titre — même traitement que Statistiques/Albums manquants (h1 simple), pour une
           page qui n'a pas de barre d'outils partagée avec Séries/Albums (tri/filtre/vue). -->
      <h1 class="authors-title">Auteurs</h1>

      <!-- Tabs -->
      <div class="authors-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          :class="['authors-tab', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span class="tab-count">{{ library.authors[tab.key]?.length || 0 }}</span>
        </button>
      </div>

      <!-- Filtre + tri — s'applique au tableau actif (Auteurs ou Éditeurs), même toolbar que
           la page Albums manquants (recherche avec icône + "Trier par"). -->
      <div class="authors-toolbar">
        <div class="authors-search-wrap">
          <SvgIcon name="search" class="authors-search-icon" />
          <input
            v-model="nameFilter"
            type="text"
            class="form-control authors-search-input"
            :placeholder="activeTab === 'publishers' ? 'Rechercher un éditeur…' : 'Rechercher un auteur…'"
          />
        </div>
        <div class="authors-sort-wrap">
          <label class="authors-sort-label" for="authors-sort-select">Trier par</label>
          <select id="authors-sort-select" v-model="sortSelect" class="form-control authors-sort-select">
            <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
      </div>

      <!-- Doublons potentiels -->
      <div v-if="duplicates[activeTab]?.length" class="card duplicates-card">
        <button class="duplicates-header" @click="duplicatesOpen = !duplicatesOpen">
          <span class="duplicates-title">Doublons potentiels</span>
          <span class="duplicates-count">{{ visibleDuplicates.length }}</span>
          <span class="duplicates-toggle">{{ duplicatesOpen ? '▾' : '▸' }}</span>
        </button>
        <div v-if="duplicatesOpen" class="duplicates-body">
          <p v-if="!visibleDuplicates.length" class="dup-all-ignored">Tous les groupes détectés ont été ignorés.</p>
          <div v-for="group in visibleDuplicates" :key="groupKey(activeTab, group)" class="dup-group">
            <span :class="['dup-tier', TIER_LABELS[group.tier].cls]">{{ TIER_LABELS[group.tier].text }}</span>
            <div class="dup-variants">
              <label v-for="v in group.variants" :key="v.name" class="dup-variant">
                <input
                  type="radio"
                  :name="groupKey(activeTab, group)"
                  :value="v.name"
                  :checked="(targetChoice[groupKey(activeTab, group)] || group.variants[0].name) === v.name"
                  @change="targetChoice[groupKey(activeTab, group)] = v.name"
                />
                <span>{{ v.name }}</span>
                <span class="dup-variant-count">{{ v.tomes }}</span>
              </label>
            </div>
            <div class="dup-actions">
              <button
                class="btn btn-primary btn-sm"
                :disabled="merging.has(groupKey(activeTab, group))"
                @click="mergeGroup(activeTab, group)"
              >{{ merging.has(groupKey(activeTab, group)) ? 'Fusion…' : 'Fusionner' }}</button>
              <button
                class="btn btn-ghost btn-sm"
                :disabled="merging.has(groupKey(activeTab, group))"
                @click="ignoreGroup(activeTab, group)"
              >Ignorer</button>
            </div>
          </div>
          <p v-if="ignoredCountForTab" class="dup-ignored-hint">
            {{ ignoredCountForTab }} groupe(s) ignoré(s) —
            <button class="dup-restore-btn" @click="restoreIgnoredForTab">réafficher</button>
          </p>
        </div>
      </div>

      <!-- Liste -->
      <div v-if="!library.authors.authors.length" class="authors-empty">
        Chargement…
      </div>
      <div v-else-if="!filtered.length" class="authors-empty">
        Aucun résultat pour "{{ nameFilter || library.search }}"
      </div>
      <div v-else class="authors-table-wrap">
        <table class="authors-table">
          <thead>
            <tr>
              <th
                v-for="col in COLS"
                :key="col.key"
                class="th-sortable"
                :class="{ 'th-active': sortKey === col.key }"
                @click="toggleSort(col.key)"
              >
                {{ col.label }}
                <span class="sort-indicator">
                  {{ sortKey === col.key ? (sortDir === 'asc' ? '↑' : '↓') : '↕' }}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="author in filtered"
              :key="author.name"
              class="author-row"
              @click="goToLibrary(author.name)"
            >
              <td class="author-name">{{ author.name }}</td>
              <td class="author-count">{{ author.series }}</td>
              <td class="author-count">{{ author.tomes }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </AppLayout>
</template>

<style scoped>
.authors-main {
  flex: 1;
  padding: 24px 20px;
  max-width: 1100px;
}

.authors-title {
  font-family: var(--font-display);
  font-weight: 400;
  text-transform: uppercase;
  font-size: 1.4rem;
  color: var(--text);
  margin-bottom: 16px;
}

.authors-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.authors-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 16px;
  font-size: 0.875rem;
  font-family: var(--font);
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: -1px;
  transition: color 0.12s;
}
.authors-tab:hover { color: var(--text); }
.authors-tab.active {
  color: var(--vermilion);
  border-bottom-color: var(--vermilion);
  font-weight: 500;
}

.tab-count {
  font-size: 0.75rem;
  background: var(--light);
  border-radius: 10px;
  padding: 1px 7px;
  color: var(--muted);
}
.authors-tab.active .tab-count {
  background: var(--vermilion-light);
  color: var(--vermilion);
}

.authors-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.authors-search-wrap { position: relative; flex: 1; min-width: 200px; max-width: 420px; }
.authors-search-icon {
  position: absolute; left: 11px; top: 50%; transform: translateY(-50%);
  color: var(--muted); font-size: 0.9rem; pointer-events: none;
}
.authors-search-input { width: 100%; padding: 8px 12px 8px 34px; font-size: 0.85rem; }
.authors-sort-wrap { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.authors-sort-label { font-size: 0.82rem; color: var(--muted); white-space: nowrap; }
.authors-sort-select { padding: 7px 10px; font-size: 0.82rem; width: auto; }

.authors-empty {
  text-align: center;
  color: var(--muted);
  font-size: 0.9rem;
  padding: 40px 0;
}

.duplicates-card { margin-bottom: 16px; padding: 14px 18px; }
.duplicates-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-family: var(--font);
}
.duplicates-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.duplicates-count {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  background: var(--light);
  border-radius: 20px;
  padding: 1px 8px;
}
.duplicates-toggle { margin-left: auto; color: var(--muted); }

.duplicates-body { margin-top: 12px; display: flex; flex-direction: column; gap: 12px; }
.dup-group {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 0;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.dup-tier {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 20px;
  flex-shrink: 0;
  white-space: nowrap;
}
.tier-1 { background: var(--success-bg, #f0fdf4); color: var(--success-text, #059669); }
.tier-2 { background: var(--info-bg, #eff6ff); color: var(--info-text, #2563eb); }
.tier-3 { background: var(--warning-bg, #fffbeb); color: var(--orange-bar, #b45309); }

.dup-variants { display: flex; gap: 14px; flex-wrap: wrap; flex: 1; min-width: 200px; }
.dup-variant { display: flex; align-items: center; gap: 5px; font-size: 0.82rem; cursor: pointer; }
.dup-variant-count { font-size: 0.72rem; color: var(--muted); }
.dup-actions { display: flex; gap: 6px; flex-shrink: 0; }

.dup-all-ignored { font-size: 0.85rem; color: var(--muted); padding: 6px 0; }
.dup-ignored-hint { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
.dup-restore-btn {
  background: none; border: none; padding: 0;
  color: var(--vermilion); font-size: 0.78rem; font-family: var(--font);
  cursor: pointer; text-decoration: underline;
}

.authors-table-wrap { overflow-x: auto; }

.authors-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.authors-table th {
  text-align: left;
  padding: 10px 14px;
  background: var(--light);
  color: var(--muted);
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.th-sortable {
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.th-sortable:hover { color: var(--text); }
.th-active { color: var(--primary); }
.sort-indicator { margin-left: 4px; font-size: 0.7rem; opacity: 0.6; }

.authors-table td {
  padding: 9px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}

.authors-table tr:last-child td { border-bottom: none; }

.author-row {
  cursor: pointer;
}
.author-row:hover td { background: var(--light); }

.author-name {
  font-weight: 500;
  color: var(--vermilion);
}

.author-count {
  color: var(--muted);
  width: 80px;
}
</style>
