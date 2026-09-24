import { defineStore } from 'pinia'
import { ref } from 'vue'
import { missingAlbumsApi } from '../api/missingAlbums'

// Compteur + progression de scan partagés entre le badge de nav (AppLayout), le menu
// "Scanner" global (AppLayout) et la page Albums manquants — pour que déclencher le scan
// depuis n'importe où affiche sa progression partout, sans dépendre de rester sur une page
// précise (même principe que library.scanProgress pour le scan fichiers).
export const useMissingAlbumsStore = defineStore('missingAlbums', () => {
  const count = ref(0)
  const scanProgress = ref({ status: 'idle', processed: 0, total: 0 })
  let pollTimer = null

  async function refreshCount() {
    try {
      const { data } = await missingAlbumsApi.count()
      count.value = data.count
    } catch { /* pas bloquant */ }
  }

  function pollScan(jobId) {
    clearInterval(pollTimer)
    pollTimer = setInterval(async () => {
      try {
        const { data } = await missingAlbumsApi.scanStatus(jobId)
        scanProgress.value = data
        if (data.status === 'done' || data.status === 'error') {
          clearInterval(pollTimer)
          refreshCount()
        }
      } catch {
        clearInterval(pollTimer)
        scanProgress.value = { ...scanProgress.value, status: 'error' }
      }
    }, 2000)
  }

  async function triggerScan() {
    const { data } = await missingAlbumsApi.startScan()
    scanProgress.value = { status: 'pending', processed: 0, total: 0, job_id: data.job_id }
    pollScan(data.job_id)
    return data.job_id
  }

  return { count, refreshCount, scanProgress, triggerScan }
})
