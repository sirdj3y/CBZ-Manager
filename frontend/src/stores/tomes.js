import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import client from '../api/client'
import { useLibraryStore } from './library'

export const useTomesStore = defineStore('tomes', () => {
  const tomes = ref([])
  const loading = ref(false)

  async function fetchAllTomes() {
    const library = useLibraryStore()
    loading.value = true
    try {
      const { data } = await client.get('/api/tomes', { params: { show_hidden: library.showHidden } })
      tomes.value = data
    } finally {
      loading.value = false
    }
  }

  return { tomes, loading, fetchAllTomes }
})
