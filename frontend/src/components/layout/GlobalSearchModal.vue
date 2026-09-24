<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore } from '../../stores/library'
import { useTomesStore } from '../../stores/tomes'
import SvgIcon from '../SvgIcon.vue'
import { normalizeSearch } from '../../utils/text'

// initialQuery : premier caractère tapé sur le bouton de recherche du topbar avant que la
// modale n'ait eu le temps de s'ouvrir (voir AppLayout.vue::onTopbarSearchKeydown) — transmis
// ici plutôt que perdu, pour que l'utilisateur n'ait pas l'impression d'avoir à le retaper.
const props = defineProps({ initialQuery: { type: String, default: '' } })
const emit = defineEmits(['close'])
const router = useRouter()
const library = useLibraryStore()
const tomesStore = useTomesStore()

const query = ref(props.initialQuery)
const inputRef = ref(null)
const highlighted = ref(0)
const MAX_PER_GROUP = 6

// Chargement paresseux — les séries/auteurs sont déjà chargés dès l'ouverture de l'app
// (AppLayout::onMounted), mais les albums (tomesStore) ne le sont que sur la page Livres :
// évite de payer ce coût pour tout le monde tant que la recherche globale n'a jamais servi.
onMounted(async () => {
  await nextTick()
  inputRef.value?.focus()
  if (!library.series.length) library.fetchSeries()
  if (!library.authors.authors.length) library.fetchAuthors()
  if (!tomesStore.tomes.length) tomesStore.fetchAllTomes()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

const AVATAR_HUES = [12, 28, 190, 265, 320, 150, 45]
function avatarColor(name) {
  let hash = 0
  for (const ch of name || '') hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return `hsl(${AVATAR_HUES[hash % AVATAR_HUES.length]}, 58%, 52%)`
}

const trimmedQuery = computed(() => query.value.trim())
const hasQuery = computed(() => trimmedQuery.value.length > 0)

// Suggestions — dernières séries/albums/auteurs réellement consultés via cette recherche
// (pas les termes tapés : afficher "cédr" tout seul est moins utile que la fiche vers
// laquelle il menait). Enregistrées uniquement à la sélection d'un résultat, pas à chaque
// frappe. Résolues "en direct" contre les stores courants à l'affichage plutôt que mises en
// cache telles quelles : cover/genre à jour, et une entrée supprimée depuis (série effacée)
// disparaît d'elle-même au lieu de pointer dans le vide.
const RECENT_KEY = 'cbz-manager:recentSelections'
const MAX_RECENT = 8
function loadRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') } catch { return [] }
}
const recentRaw = ref(loadRecent())
function stampKey(r) { return r.kind === 'author' ? `author:${r.name}` : `${r.kind}:${r.id}` }
function saveRecent(entry) {
  const stamped = { kind: entry.kind, id: entry.item.id ?? null, name: entry.item.name ?? null }
  const key = stampKey(stamped)
  const next = [stamped, ...recentRaw.value.filter(r => stampKey(r) !== key)].slice(0, MAX_RECENT)
  recentRaw.value = next
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}
function removeRecent(stamped) {
  recentRaw.value = recentRaw.value.filter(r => stampKey(r) !== stampKey(stamped))
  localStorage.setItem(RECENT_KEY, JSON.stringify(recentRaw.value))
}
const recentResolved = computed(() => {
  const out = []
  for (const r of recentRaw.value) {
    let item = null
    if (r.kind === 'series') item = library.series.find(s => s.id === r.id)
    else if (r.kind === 'album') item = tomesStore.tomes.find(t => t.id === r.id)
    else if (r.kind === 'author') item = library.authors.authors.find(a => a.name === r.name)
    if (item) out.push({ kind: r.kind, item, raw: r })
  }
  return out
})

const seriesMatches = computed(() => {
  const q = normalizeSearch(trimmedQuery.value)
  if (!q) return []
  return library.series.filter(s => normalizeSearch(s.name).includes(q)).slice(0, MAX_PER_GROUP)
})
const albumMatches = computed(() => {
  const q = normalizeSearch(trimmedQuery.value)
  if (!q) return []
  return tomesStore.tomes
    .filter(t => normalizeSearch(t.title || t.filename).includes(q) || normalizeSearch(t.series_name).includes(q))
    .slice(0, MAX_PER_GROUP)
})
const authorMatches = computed(() => {
  const q = normalizeSearch(trimmedQuery.value)
  if (!q) return []
  return library.authors.authors.filter(a => normalizeSearch(a.name).includes(q)).slice(0, MAX_PER_GROUP)
})

// Groupes affichés — "Suggestions" (une seule liste mixte) tant que rien n'est tapé, sinon
// Séries/Albums/Auteurs. Chaque entrée porte son index global (idx), partagé entre tous les
// groupes affichés à cet instant — sert à la fois de clé de surbrillance et de cible de
// navigation clavier (flèches) sans recalcul de décalage dans le template.
const activeGroups = computed(() => {
  let i = 0
  if (!hasQuery.value) {
    const entries = recentResolved.value.map(r => ({ ...r, idx: i++ }))
    return entries.length ? [{ label: 'Suggestions', entries }] : []
  }
  const withIdx = (kind, arr) => arr.map(item => ({ kind, item, idx: i++ }))
  return [
    { label: 'Séries', entries: withIdx('series', seriesMatches.value) },
    { label: 'Albums', entries: withIdx('album', albumMatches.value) },
    { label: 'Auteurs', entries: withIdx('author', authorMatches.value) },
  ].filter(g => g.entries.length)
})
const flatActive = computed(() => activeGroups.value.flatMap(g => g.entries))
const hasResults = computed(() => flatActive.value.length > 0)

watch(trimmedQuery, () => { highlighted.value = 0 })

function seriesMeta(s) {
  const parts = []
  if (s.genres?.length) parts.push(s.genres.join(' / '))
  else if (s.classification) parts.push(s.classification)
  parts.push(`${s.tome_count} tome${s.tome_count > 1 ? 's' : ''}`)
  return parts.join(' · ')
}
function albumMeta(t) {
  const parts = [t.series_name]
  if (t.number) parts.push(`T${t.number}`)
  return parts.filter(Boolean).join(' · ')
}
function authorMeta(a) {
  const n = a.tomes ?? 0
  return `${n} album${n > 1 ? 's' : ''}`
}
function entryLabel(entry) {
  if (entry.kind === 'album') return entry.item.title || entry.item.filename
  return entry.item.name
}
function entryMeta(entry) {
  if (entry.kind === 'series') return seriesMeta(entry.item)
  if (entry.kind === 'album') return albumMeta(entry.item)
  return authorMeta(entry.item)
}

function select(entry) {
  if (!entry) return
  saveRecent(entry)
  if (entry.kind === 'series') router.push(`/series/${entry.item.id}`)
  else if (entry.kind === 'album') router.push(`/tomes/${entry.item.id}`)
  else if (entry.kind === 'author') router.push(`/books?writer=${encodeURIComponent(entry.item.name)}&penciller=${encodeURIComponent(entry.item.name)}`)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape') { e.preventDefault(); emit('close'); return }
  if (e.key === 'ArrowDown') {
    if (!flatActive.value.length) return
    e.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, flatActive.value.length - 1)
    return
  }
  if (e.key === 'ArrowUp') {
    if (!flatActive.value.length) return
    e.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    select(flatActive.value[highlighted.value])
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="gs-backdrop" @click="$emit('close')">
      <div class="gs-box" @click.stop>
        <div class="gs-header">
          <SvgIcon name="search" class="gs-search-icon" />
          <input
            ref="inputRef"
            v-model="query"
            type="text"
            class="gs-input"
            placeholder="Rechercher une série, un album, un auteur…"
          />
          <button v-if="query" type="button" class="gs-clear-btn" title="Effacer" @click="query = ''">✕</button>
          <button type="button" class="gs-escape-btn" @click="$emit('close')">Échap</button>
        </div>

        <div class="gs-body">
          <p v-if="!hasQuery && !hasResults" class="gs-hint">Tape pour rechercher dans toute ta bibliothèque…</p>
          <p v-else-if="hasQuery && !hasResults" class="gs-hint">Aucun résultat pour « {{ trimmedQuery }} ».</p>

          <div v-for="group in activeGroups" :key="group.label" class="gs-group">
            <p class="gs-group-title">{{ group.label }}</p>
            <div
              v-for="entry in group.entries"
              :key="entry.kind + (entry.item.id ?? entry.item.name)"
              class="gs-row-wrap"
            >
              <button
                type="button"
                :class="['gs-row', { 'gs-row-active': entry.idx === highlighted }]"
                @mouseenter="highlighted = entry.idx"
                @click="select(entry)"
              >
                <span v-if="entry.kind === 'author'" class="gs-thumb gs-thumb-avatar" :style="{ background: avatarColor(entry.item.name) }">
                  {{ entry.item.name.charAt(0).toUpperCase() }}
                </span>
                <span v-else class="gs-thumb gs-thumb-cover">
                  <img v-if="entry.item.cover_url" :src="entry.item.cover_url" alt="" loading="lazy" />
                  <span v-else class="gs-thumb-fallback">📖</span>
                </span>
                <span class="gs-row-text">
                  <span class="gs-row-name">{{ entryLabel(entry) }}</span>
                </span>
                <span class="gs-row-meta">{{ entryMeta(entry) }}</span>
              </button>
              <button
                v-if="group.label === 'Suggestions'"
                type="button" class="gs-row-remove" title="Retirer des suggestions"
                @click="removeRecent(entry.raw)"
              >✕</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.gs-backdrop {
  position: fixed; inset: 0; z-index: 600;
  background: var(--overlay-bg);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 12vh 20px 20px;
}
.gs-box {
  width: 100%; max-width: 640px; max-height: 70vh;
  background: var(--surface-raised); border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column; overflow: hidden;
}
.gs-header {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.gs-search-icon { color: var(--muted); font-size: 1.1rem; flex-shrink: 0; }
.gs-input {
  flex: 1; border: none; outline: none; background: none;
  font-family: var(--font); font-size: 1rem; color: var(--text);
}
.gs-input::placeholder { color: var(--placeholder); }
.gs-clear-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 50%;
  background: none; border: none; color: var(--muted); cursor: pointer;
  flex-shrink: 0;
}
.gs-clear-btn:hover { background: var(--light); color: var(--text); }
.gs-escape-btn {
  flex-shrink: 0;
  padding: 4px 10px;
  font-size: 0.75rem; font-weight: 600; font-family: var(--font);
  color: var(--muted); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer;
}
.gs-escape-btn:hover { border-color: var(--vermilion); color: var(--vermilion); }

.gs-body { flex: 1; overflow-y: auto; padding: 8px; }
.gs-hint { padding: 28px 16px; text-align: center; font-size: 0.85rem; color: var(--muted); }

.gs-group { display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }
.gs-group-title {
  padding: 8px 10px 4px;
  font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted);
}
.gs-row-wrap { position: relative; display: flex; align-items: center; }
.gs-row {
  display: flex; align-items: center; gap: 12px;
  width: 100%; padding: 8px 10px; border-radius: var(--radius-sm);
  background: none; border: none; cursor: pointer; text-align: left;
  font-family: var(--font);
  transition: background 0.1s;
}
.gs-row:hover, .gs-row-active { background: var(--light); }
/* "Retirer des suggestions" — superposé au bord droit de la ligne plutôt qu'un élément à
   part dans le flex, sinon le survol du bouton lui-même retirait le fond de surbrillance de
   la ligne en dessous (les deux ne sont plus dans le même conteneur :hover). */
.gs-row-remove {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--surface-raised); border: none; color: var(--muted); cursor: pointer;
  font-size: 0.68rem;
  opacity: 0; transition: opacity 0.12s, background 0.12s;
}
.gs-row-wrap:hover .gs-row-remove { opacity: 1; }
.gs-row-remove:hover { background: var(--danger-bg-light); color: var(--danger); }

.gs-thumb {
  flex-shrink: 0; width: 40px; height: 40px; border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.gs-thumb-cover { background: var(--light); }
.gs-thumb-cover img { width: 100%; height: 100%; object-fit: cover; }
.gs-thumb-fallback { font-size: 1.1rem; }
.gs-thumb-avatar { color: #fff; font-weight: 700; font-size: 0.9rem; }

.gs-row-text { flex: 1; min-width: 0; }
.gs-row-name {
  display: block; font-size: 0.875rem; color: var(--text); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gs-row-meta {
  flex-shrink: 0; font-size: 0.78rem; color: var(--muted);
  white-space: nowrap; margin-left: 8px;
}

@media (max-width: 620px) {
  .gs-backdrop { padding: 8vh 12px 12px; }
}
</style>
