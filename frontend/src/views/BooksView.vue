<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import ContentToolbar from '../components/layout/ContentToolbar.vue'
import MetadataDrawer from '../components/metadata/MetadataDrawer.vue'
import { useTomesStore } from '../stores/tomes'
import { useLibraryStore } from '../stores/library'

const router = useRouter()
const route = useRoute()
const tomesStore = useTomesStore()
const library = useLibraryStore()

const activeLetter = ref('')
const selectedTome = ref(null)
const showMetadata = ref(false)

function syncFromQuery() {
  const q = route.query
  if (q.writer || q.penciller || q.publisher || q.tag) {
    library.filters = {
      writer: q.writer || '',
      penciller: q.penciller || '',
      publisher: q.publisher || '',
      tag: q.tag || '',
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

  // Filtres auteur/éditeur/tag
  // Si writer et penciller ont la même valeur → OR (auteur polyvalent)
  if (library.filters.writer && library.filters.penciller && library.filters.writer === library.filters.penciller) {
    const q = norm(library.filters.writer)
    list = list.filter(t => norm(t.writer || '').includes(q) || norm(t.penciller || '').includes(q))
  } else {
    if (library.filters.writer)    list = list.filter(t => norm(t.writer || '').includes(norm(library.filters.writer)))
    if (library.filters.penciller) list = list.filter(t => norm(t.penciller || '').includes(norm(library.filters.penciller)))
  }
  if (library.filters.publisher) list = list.filter(t => norm(t.publisher || '').includes(norm(library.filters.publisher)))
  if (library.filters.tag)       list = list.filter(t => (t.user_tags || []).some(tag => norm(tag).includes(norm(library.filters.tag))))

  // Filtre format
  if (library.filters.format)    list = list.filter(t => t.file_format === library.filters.format)

  // Sort
  const sorted = [...list]
  const dir = library.sortDir === 'asc' ? 1 : -1
  if (library.sortBy === 'name') {
    sorted.sort((a, b) => dir * norm(a.title || a.filename).localeCompare(norm(b.title || b.filename), 'fr'))
  } else if (library.sortBy === 'added') {
    sorted.sort((a, b) => dir * (new Date(a.created_at ?? 0) - new Date(b.created_at ?? 0)))
  } else if (library.sortBy === 'updated') {
    sorted.sort((a, b) => dir * (new Date(a.updated_at ?? 0) - new Date(b.updated_at ?? 0)))
  }

  return sorted
})

function editTome(tome) {
  selectedTome.value = tome
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
      @letter="(l) => activeLetter = l"
      @filter-change="(f) => library.filters = f"
    />

    <main class="content-area">
      <div v-if="tomesStore.loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>
      <div v-else-if="filteredTomes.length === 0" class="state-box">
        <p class="state-desc">Aucun album trouvé</p>
      </div>
      <div v-else class="books-grid">
        <div
          v-for="tome in filteredTomes"
          :key="tome.id"
          class="book-card"
          :class="{ 'book-card-hidden': tome.hidden || tome.series_hidden }"
          :title="tome.title || tome.filename"
        >
          <!-- Cover -->
          <div class="book-cover" @click="router.push(`/tomes/${tome.id}`)">
            <img
              v-if="tome.cover_url"
              :src="tome.cover_url"
              :alt="tome.title"
              class="book-cover-img"
              loading="lazy"
              @error="$event.target.style.display='none'"
            />
            <div v-else class="book-cover-placeholder">📖</div>

            <!-- Number badge -->
            <span v-if="tome.number" class="book-badge">T{{ fmtNumber(tome.number) }}</span>

            <!-- Hover overlay : crayon gauche, œil droite -->
            <div class="book-overlay">
              <button class="overlay-btn" title="Modifier" @click.stop="editTome(tome)">
                <SvgIcon name="edit" style="font-size:15px" />
              </button>
              <div class="overlay-spacer"></div>
              <button class="overlay-btn" title="Lire" @click.stop="router.push(`/read/${tome.id}`)">
                <SvgIcon name="read" style="font-size:15px" />
              </button>
            </div>

          </div>

          <!-- Info -->
          <div class="book-info" @click="router.push(`/tomes/${tome.id}`)">
            <p class="book-title">{{ tome.title || tome.filename }}</p>
            <p class="book-meta">
              <span :class="['fmt-badge', `fmt-${tome.file_format}`]">{{ tome.file_format.toUpperCase() }}</span>
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
      @close="showMetadata = false"
      @saved="tomesStore.fetchAllTomes()"
      @deleted="tomesStore.fetchAllTomes()"
    />
  </AppLayout>
</template>

<style scoped>
.content-area {
  flex: 1;
  padding: 16px 20px;
}

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
  overflow: hidden;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
}
.book-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}

.book-cover {
  aspect-ratio: 2/3;
  background: var(--light);
  position: relative;
  overflow: hidden;
  cursor: pointer;
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

.book-badge {
  position: absolute; top: 6px; right: 6px; z-index: 2;
  padding: 1px 6px;
  background: rgba(255,255,255,0.92); color: var(--text);
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}

.book-overlay {
  position: absolute; inset: 0; z-index: 3;
  background: rgba(0,0,0,0.32);
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: flex-end;
  padding: 8px;
}
.overlay-spacer { flex: 1; }
.book-card:hover .book-overlay { opacity: 1; }

.overlay-btn {
  width: 30px; height: 30px; border-radius: 50%;
  background: var(--overlay-btn-bg); border: none; cursor: pointer;
  color: var(--text);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, transform 0.12s;
  flex-shrink: 0;
}
.overlay-btn:hover { background: var(--surface); transform: scale(1.1); }

.book-info {
  padding: 7px 9px;
  border-top: 1px solid var(--border);
  cursor: pointer;
}
.book-title {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 4px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.book-meta {
  display: flex; align-items: center; gap: 6px;
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
</style>
