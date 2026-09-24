import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { libraryApi } from '../api/library'
import { useTomesStore } from './tomes'
import { normalizeSearch, sortTitle } from '../utils/text'

export const useLibraryStore = defineStore('library', () => {
  const series = ref([])
  const loading = ref(false)
  const search = ref('')
  const sortBy = ref('name') // 'name' | 'added' | 'tomes' | 'updated'
  const sortDir = ref('asc') // 'asc' | 'desc'
  const showHidden = ref(false)
  const filters = ref({}) // { writer, penciller, publisher, tag, noMeta }
  const scanJobId = ref(null)
  const scanProgress = ref({ processed: 0, total: 0, status: 'idle' })

  const filteredSeries = computed(() => {
    let list = series.value
    const f = filters.value

    // Recherche par nom
    if (search.value.trim()) {
      const q = normalizeSearch(search.value)
      list = list.filter(s => normalizeSearch(s.name).includes(q))
    }

    // Filtres textuels — cherche dans toutes les valeurs agrégées de la série
    if (f.writer)    list = list.filter(s => (s.writers || []).some(w => normalizeSearch(w).includes(normalizeSearch(f.writer))))
    if (f.penciller) list = list.filter(s => (s.pencillers || []).some(p => normalizeSearch(p).includes(normalizeSearch(f.penciller))))
    if (f.publisher) list = list.filter(s => (s.publishers || []).some(p => normalizeSearch(p).includes(normalizeSearch(f.publisher))))
    if (f.tag)       list = list.filter(s => (s.tags || []).some(t => normalizeSearch(t).includes(normalizeSearch(f.tag))))
    if (f.genre)     list = list.filter(s => (s.genres || []).some(g => normalizeSearch(g).includes(normalizeSearch(f.genre))))
    if (f.noMeta)    list = list.filter(s => s.has_tomes_without_meta)
    if (f.classification) list = list.filter(s => s.classification === f.classification)

    // Sort
    const sorted = [...list]
    const dir = sortDir.value === 'asc' ? 1 : -1
    if (sortBy.value === 'name') {
      sorted.sort((a, b) => dir * sortTitle(a.name).localeCompare(sortTitle(b.name), 'fr'))
    } else if (sortBy.value === 'tomes') {
      sorted.sort((a, b) => dir * ((a.tome_count ?? 0) - (b.tome_count ?? 0)))
    } else if (sortBy.value === 'added') {
      sorted.sort((a, b) => dir * (new Date(a.created_at ?? 0) - new Date(b.created_at ?? 0)))
    } else if (sortBy.value === 'updated') {
      sorted.sort((a, b) => dir * (new Date(a.updated_at ?? 0) - new Date(b.updated_at ?? 0)))
    }
    return sorted
  })

  async function fetchSeries() {
    loading.value = true
    try {
      const { data } = await libraryApi.getSeries(showHidden.value)
      series.value = data
    } finally {
      loading.value = false
    }
  }

  let scanSource = null

  async function triggerScan() {
    const { data } = await libraryApi.startScan()

    // Backend dedups concurrent scans (returns the running job's id) — if we're already
    // streaming that same job, don't open a second EventSource on top of it.
    if (scanSource && data.job_id === scanJobId.value) {
      return scanJobId.value
    }
    if (scanSource) {
      scanSource.close()
      scanSource = null
    }

    scanJobId.value = data.job_id
    scanProgress.value = { processed: 0, total: 0, status: 'running' }

    const source = new EventSource(`/api/scan/${data.job_id}/stream`, { withCredentials: true })
    scanSource = source
    source.onmessage = (e) => {
      const d = JSON.parse(e.data)
      scanProgress.value = d
      if (d.status === 'done') {
        source.close()
        if (scanSource === source) scanSource = null
        fetchSeries()
        useTomesStore().fetchAllTomes()
      } else if (d.status === 'error') {
        source.close()
        if (scanSource === source) scanSource = null
      }
    }
    source.onerror = () => {
      source.close()
      if (scanSource === source) scanSource = null
      if (scanProgress.value.status === 'running') {
        scanProgress.value = { ...scanProgress.value, status: 'error' }
      }
    }

    return data.job_id
  }

  watch(showHidden, () => {
    fetchSeries()
    useTomesStore().fetchAllTomes()
  })

  // Auteurs connus (objets {name, tomes, series}) pour la page auteurs
  const authors = ref({ authors: [], publishers: [], genres: [], tags: [] })
  // Noms seuls pour l'autocomplétion
  const authorNames = computed(() => ({
    writers:    authors.value.authors.map(a => a.name),
    pencillers: authors.value.authors.map(a => a.name),
    publishers: authors.value.publishers.map(a => a.name),
    genres:     authors.value.genres || [],
    tags:       authors.value.tags || [],
  }))
  async function fetchAuthors() {
    try {
      const { data } = await libraryApi.getAuthors()
      authors.value = data
    } catch { /* ignoré */ }
  }

  return { series, loading, search, sortBy, sortDir, showHidden, filters, scanJobId, scanProgress, filteredSeries, fetchSeries, triggerScan, authors, authorNames, fetchAuthors }
})
