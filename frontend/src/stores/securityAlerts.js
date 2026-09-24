import { defineStore } from 'pinia'
import { ref } from 'vue'
import { logsApi } from '../api/logs'

// Badge sur "Historique" (AppLayout) + bandeau sur la page Historique elle-même — un seul
// fetch partagé, même principe que missingAlbums.js pour son compteur de nav.
export const useSecurityAlertsStore = defineStore('securityAlerts', () => {
  const alerts = ref([])

  async function refresh() {
    try {
      const { data } = await logsApi.alerts()
      alerts.value = data
    } catch { /* pas bloquant — admin only, 403 possible si appelé hors contexte admin */ }
  }

  return { alerts, refresh }
})
