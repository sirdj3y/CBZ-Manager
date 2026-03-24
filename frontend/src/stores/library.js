import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { libraryApi } from '../api/library'
import { useTomesStore } from './tomes'

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

  function norm(s) {
    return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  }

  const filteredSeries = computed(() => {
    let list = series.value
    const f = filters.value

    // Recherche par nom
    if (search.value.trim()) {
      const q = norm(search.value)
      list = list.filter(s => norm(s.name).includes(q))
    }

    // Filtres textuels — cherche dans toutes les valeurs agrégées de la série
    if (f.writer)    list = list.filter(s => (s.writers || []).some(w => norm(w).includes(norm(f.writer))))
    if (f.penciller) list = list.filter(s => (s.pencillers || []).some(p => norm(p).includes(norm(f.penciller))))
    if (f.publisher) list = list.filter(s => (s.publishers || []).some(p => norm(p).includes(norm(f.publisher))))
    if (f.tag)       list = list.filter(s => (s.tags || []).some(t => norm(t).includes(norm(f.tag))))
    if (f.noMeta)    list = list.filter(s => s.has_tomes_without_meta)

    // Sort
    const sorted = [...list]
    const dir = sortDir.value === 'asc' ? 1 : -1
    if (sortBy.value === 'name') {
      sorted.sort((a, b) => dir * a.name.localeCompare(b.name, 'fr'))
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

  async function triggerScan() {
    const { data } = await libraryApi.startScan()
    scanJobId.value = data.job_id
    scanProgress.value = { processed: 0, total: 0, status: 'running' }

    const source = new EventSource(`/api/scan/${data.job_id}/stream`, { withCredentials: true })
    source.onmessage = (e) => {
      const d = JSON.parse(e.data)
      scanProgress.value = d
      if (d.status === 'done') {
        source.close()
        fetchSeries()
        useTomesStore().fetchAllTomes()
      } else if (d.status === 'error') {
        source.close()
      }
    }
    source.onerror = () => source.close()

    return data.job_id
  }

  watch(showHidden, () => {
    fetchSeries()
    useTomesStore().fetchAllTomes()
  })

  // Auteurs connus (objets {name, tomes, series}) pour la page auteurs
  const authors = ref({ authors: [], publishers: [] })
  // Noms seuls pour l'autocomplétion
  const authorNames = computed(() => ({
    writers:    authors.value.authors.map(a => a.name),
    pencillers: authors.value.authors.map(a => a.name),
    publishers: authors.value.publishers.map(a => a.name),
  }))
  async function fetchAuthors() {
    try {
      const { data } = await libraryApi.getAuthors()
      authors.value = data
    } catch { /* ignoré */ }
  }

  return { series, loading, search, sortBy, sortDir, showHidden, filters, scanJobId, scanProgress, filteredSeries, fetchSeries, triggerScan, authors, authorNames, fetchAuthors }
})
