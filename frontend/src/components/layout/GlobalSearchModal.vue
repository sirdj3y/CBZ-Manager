<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ListboxFilter } from 'reka-ui'
import { BookOpen, Search, X } from '@lucide/vue'
import { useLibraryStore } from '../../stores/library'
import { useTomesStore } from '../../stores/tomes'
import { normalizeSearch } from '../../utils/text'
import { Command, CommandGroup, CommandItem, CommandList } from '@/components/shadcn/command'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/shadcn/dialog'

// Palette de recherche (⌘K ou champ du topbar) — Dialog + Command de shadcn-vue : focus
// bloqué dans la palette, Échap, flèches/Entrée et accessibilité gérés par Reka UI. Le filtrage
// reste le nôtre (sans accents, 6 résultats par groupe, albums chargés à la demande) : le champ
// est un ListboxFilter branché sur `query`, pas le CommandInput de shadcn, dont le filtrage
// intégré obligerait à afficher tous les albums de la bibliothèque pour les filtrer ensuite.

// initialQuery : premier caractère tapé sur le bouton de recherche du topbar avant que la
// modale n'ait eu le temps de s'ouvrir (voir AppLayout.vue::onTopbarSearchKeydown) — transmis
// ici plutôt que perdu, pour que l'utilisateur n'ait pas l'impression d'avoir à le retaper.
const props = defineProps({ initialQuery: { type: String, default: '' } })
const emit = defineEmits(['close'])
const router = useRouter()
const library = useLibraryStore()
const tomesStore = useTomesStore()

const query = ref(props.initialQuery)
const MAX_PER_GROUP = 6

// Chargement paresseux — les séries/auteurs sont déjà chargés dès l'ouverture de l'app
// (AppLayout::onMounted), mais les albums (tomesStore) ne le sont que sur la page Livres :
// évite de payer ce coût pour tout le monde tant que la recherche globale n'a jamais servi.
onMounted(() => {
  if (!library.series.length) library.fetchSeries()
  if (!library.authors.authors.length) library.fetchAuthors()
  if (!tomesStore.tomes.length) tomesStore.fetchAllTomes()
})

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
// Séries/Albums/Auteurs. La navigation clavier (flèches, Entrée) est celle de Reka UI.
const activeGroups = computed(() => {
  if (!hasQuery.value) {
    return recentResolved.value.length ? [{ label: 'Suggestions', entries: recentResolved.value }] : []
  }
  const wrap = (kind, arr) => arr.map(item => ({ kind, item }))
  return [
    { label: 'Séries', entries: wrap('series', seriesMatches.value) },
    { label: 'Albums', entries: wrap('album', albumMatches.value) },
    { label: 'Auteurs', entries: wrap('author', authorMatches.value) },
  ].filter(g => g.entries.length)
})
const hasResults = computed(() => activeGroups.value.some(g => g.entries.length))
const entryKey = entry => `${entry.kind}:${entry.item.id ?? entry.item.name}`

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
</script>

<template>
  <Dialog :open="true" @update:open="open => { if (!open) emit('close') }">
    <DialogContent
      :show-close-button="false"
      class="top-[12vh] translate-y-0 gap-0 overflow-hidden rounded-[var(--radius-lg)] bg-[var(--surface-raised)] p-0 sm:max-w-[640px]"
    >
      <DialogTitle class="sr-only">Recherche</DialogTitle>
      <DialogDescription class="sr-only">Rechercher une série, un album ou un auteur dans la bibliothèque</DialogDescription>
      <Command class="bg-transparent">
        <div class="flex items-center gap-2.5 border-b px-4 py-3">
          <Search class="size-[1.1rem] shrink-0 text-muted-foreground" />
          <ListboxFilter
            v-model="query"
            auto-focus
            class="min-w-0 flex-1 bg-transparent text-base text-foreground outline-hidden placeholder:text-[var(--placeholder)]"
            placeholder="Rechercher une série, un album, un auteur…"
          />
          <button
            v-if="query" type="button" aria-label="Effacer"
            class="flex size-[26px] shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground"
            @click="query = ''"
          ><X class="size-3.5" /></button>
          <button
            type="button"
            class="shrink-0 cursor-pointer rounded-sm border bg-background px-2.5 py-1 text-xs font-semibold text-muted-foreground hover:border-[var(--vermilion)] hover:text-[var(--vermilion)]"
            @click="emit('close')"
          >Échap</button>
        </div>

        <CommandList class="max-h-[min(60vh,560px)] p-2">
          <p v-if="!hasQuery && !hasResults" class="px-4 py-7 text-center text-sm text-muted-foreground">Tape pour rechercher dans toute ta bibliothèque…</p>
          <p v-else-if="hasQuery && !hasResults" class="px-4 py-7 text-center text-sm text-muted-foreground">Aucun résultat pour « {{ trimmedQuery }} ».</p>

          <CommandGroup
            v-for="group in activeGroups" :key="group.label" :heading="group.label"
            class="[&_[data-slot=command-group-heading]]:text-[0.7rem] [&_[data-slot=command-group-heading]]:font-bold [&_[data-slot=command-group-heading]]:uppercase [&_[data-slot=command-group-heading]]:tracking-wider"
          >
            <CommandItem
              v-for="entry in group.entries" :key="entryKey(entry)" :value="entryKey(entry)"
              class="group gap-3 py-2 pr-2"
              @select="select(entry)"
            >
              <span
                v-if="entry.kind === 'author'"
                class="flex size-10 shrink-0 items-center justify-center rounded-sm text-sm font-bold text-white"
                :style="{ background: avatarColor(entry.item.name) }"
              >{{ entry.item.name.charAt(0).toUpperCase() }}</span>
              <span v-else class="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-muted">
                <img v-if="entry.item.cover_url" :src="entry.item.cover_url" alt="" loading="lazy" class="size-full object-cover" />
                <BookOpen v-else class="size-4" />
              </span>
              <span class="min-w-0 flex-1 truncate font-medium text-foreground">{{ entryLabel(entry) }}</span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ entryMeta(entry) }}</span>
              <button
                v-if="group.label === 'Suggestions'"
                type="button" aria-label="Retirer des suggestions"
                class="flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground opacity-0 group-hover:opacity-100 group-data-[highlighted]:opacity-100 hover:bg-[var(--danger-bg-light)] hover:text-[var(--danger)]"
                @pointerdown.stop @click.stop="removeRecent(entry.raw)"
              ><X class="size-3" /></button>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </Command>
    </DialogContent>
  </Dialog>
</template>
