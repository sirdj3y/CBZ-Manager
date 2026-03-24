<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import { useLibraryStore } from '../stores/library'

const router = useRouter()
const library = useLibraryStore()

const activeTab = ref('authors')

const TABS = [
  { key: 'authors',    label: 'Auteurs' },
  { key: 'publishers', label: 'Éditeurs' },
]

onMounted(() => {
  if (!library.authors.authors.length) library.fetchAuthors()
})

const filtered = computed(() => {
  const list = library.authors[activeTab.value] || []
  const q = library.search.trim().toLowerCase()
  if (!q) return list
  return list.filter(a => a.name.toLowerCase().includes(q))
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

      <!-- Liste -->
      <div v-if="!library.authors.authors.length" class="authors-empty">
        Chargement…
      </div>
      <div v-else-if="!filtered.length" class="authors-empty">
        Aucun résultat pour "{{ library.search }}"
      </div>
      <div v-else class="authors-table-wrap">
        <table class="authors-table">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Séries</th>
              <th>Albums</th>
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
  padding: 20px;
  max-width: 900px;
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
  color: var(--primary);
  border-bottom-color: var(--primary);
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
  background: var(--primary-light);
  color: var(--primary);
}

.authors-empty {
  text-align: center;
  color: var(--muted);
  font-size: 0.9rem;
  padding: 40px 0;
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
  color: var(--primary);
}

.author-count {
  color: var(--muted);
  width: 80px;
}
</style>
