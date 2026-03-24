import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import client from '../api/client'
import { tomesApi } from '../api/tomes'

export const useReaderStore = defineStore('reader', () => {
  const tomeId = ref(null)
  const tomeInfo = ref(null)
  const currentPage = ref(0)
  const savedPage = ref(0)
  const mode = ref('single') // 'single' | 'double' | 'vertical'
  const zoom = ref(1.0)
  const showToolbar = ref(true)

  const pageCount = computed(() => tomeInfo.value?.page_count ?? 0)
  const title = computed(() => tomeInfo.value?.title ?? '')
  const hasSavedProgress = computed(() => savedPage.value > 0)

  function pageUrl(id, index) {
    return `/api/reader/${id}/page/${index}`
  }

  async function loadTome(id) {
    tomeId.value = id
    currentPage.value = 0
    savedPage.value = 0
    const [infoRes, progressRes] = await Promise.all([
      client.get(`/api/reader/${id}/info`),
      tomesApi.getProgress(id),
    ])
    tomeInfo.value = infoRes.data
    savedPage.value = progressRes.data.last_page ?? 0
  }

  function resumeFromSaved() {
    currentPage.value = savedPage.value
  }

  let _saveTimer = null
  function _scheduleSave() {
    if (!tomeId.value) return
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(() => {
      tomesApi.saveProgress(tomeId.value, currentPage.value)
    }, 800)
  }

  function nextPage() {
    const step = mode.value === 'double' ? 2 : 1
    const max = pageCount.value - 1
    currentPage.value = Math.min(currentPage.value + step, max)
    _scheduleSave()
  }

  function prevPage() {
    const step = mode.value === 'double' ? 2 : 1
    currentPage.value = Math.max(currentPage.value - step, 0)
    _scheduleSave()
  }

  function setMode(m) { mode.value = m }
  function setZoom(z) { zoom.value = Math.max(0.5, Math.min(3, z)) }
  function toggleToolbar() { showToolbar.value = !showToolbar.value }

  return {
    tomeId, tomeInfo, currentPage, savedPage, mode, zoom, showToolbar,
    pageCount, title, hasSavedProgress, pageUrl,
    loadTome, resumeFromSaved, nextPage, prevPage, setMode, setZoom, toggleToolbar,
  }
})
