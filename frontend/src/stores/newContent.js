import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationsApi } from '../api/notifications'

// Nouveautés (albums/séries) depuis la dernière consultation — badge topbar + menu
// déroulant (AppLayout). count = total réel (non plafonné), items = liste plafonnée
// renvoyée par le backend pour le menu.
export const useNewContentStore = defineStore('newContent', () => {
  const count = ref(0)
  const items = ref([])

  async function refresh() {
    try {
      const { data } = await notificationsApi.get()
      count.value = data.count
      items.value = data.items
    } catch { /* pas bloquant */ }
  }

  async function markSeen() {
    try {
      await notificationsApi.markSeen()
      // On vide le badge (compteur), mais pas `items` : l'utilisateur vient d'ouvrir le
      // menu pour VOIR ces nouveautés — les faire disparaître à l'instant même de
      // l'ouverture serait contre-productif. La liste se videra naturellement au prochain
      // refresh() une fois que le backend n'aura plus rien de postérieur à "vu la dernière fois".
      count.value = 0
    } catch { /* pas bloquant */ }
  }

  return { count, items, refresh, markSeen }
})
