import { defineStore } from 'pinia'
import { ref } from 'vue'
import { smartListsApi } from '../api/smartLists'

// Partagé entre AppLayout (section "Smart list" de la barre latérale, seule surface de
// gestion — pas de page dédiée) et CollectionDetailView (fiche d'une liste, bouton
// Modifier). L'état de l'éditeur (editorOpen/editorTarget) vit ici plutôt que dans
// AppLayout : la modale elle-même n'est instanciée qu'une fois, dans AppLayout (présent sur
// toutes les pages), mais n'importe quelle page doit pouvoir l'ouvrir sans lien parent/enfant
// direct avec AppLayout.
export const useSmartListsStore = defineStore('smartLists', () => {
  const lists = ref([])
  const loaded = ref(false)

  async function refresh() {
    try {
      const { data } = await smartListsApi.list()
      lists.value = data
      loaded.value = true
    } catch { /* pas bloquant */ }
  }

  const editorOpen = ref(false)
  const editorTarget = ref(null) // null = création, objet = édition

  function openCreate() {
    editorTarget.value = null
    editorOpen.value = true
  }
  function openEdit(sl) {
    editorTarget.value = sl
    editorOpen.value = true
  }
  function closeEditor() {
    editorOpen.value = false
  }

  // Réordonnancement par glisser-déposer — optimiste (l'ordre local est déjà à jour côté
  // appelant avant que cette fonction ne soit appelée, voir AppLayout::onDrop), on persiste
  // juste côté serveur ; en cas d'échec, un refresh() restaure l'ordre serveur réel.
  async function reorder(ids) {
    try {
      await smartListsApi.reorder(ids)
    } catch {
      await refresh()
    }
  }

  return { lists, loaded, refresh, editorOpen, editorTarget, openCreate, openEdit, closeEditor, reorder }
})
