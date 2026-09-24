<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import ScraperResultCard from './ScraperResultCard.vue'
import SvgIcon from '../SvgIcon.vue'
import { scraperApi } from '../../api/scraper'

const props = defineProps({
  series: String,
  number: String,
  // Série locale déjà identifiée (édition d'un album existant, ou import dans une série
  // existante) — permet à la recherche Bedetheque d'utiliser directement son URL confirmée
  // au lieu de deviner la bonne série par son nom.
  seriesId: { type: Number, default: null },
  // Titre propre du tome — utilisé comme requête par défaut à la place de série+numéro
  // quand isOneshot est vrai (série+numéro n'a aucun sens pour un album indépendant, voir
  // Tome.is_oneshot).
  title: { type: String, default: '' },
  isOneshot: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'close'])

const tab = ref('bedetheque')
const query = ref('')
const results = ref([])
const loading = ref(false)
const error = ref('')
const selectedResult = ref(null)
// Tant que l'utilisateur n'a pas modifié la requête pré-remplie, la série/son id confirmé
// peuvent servir de raccourci (voir search()). Dès qu'il tape lui-même quelque chose, sa
// saisie doit être LA recherche réelle — plus aucun terme caché (série) injecté en douce,
// même si elle reste correctement renseignée pour d'autres usages (préremplissage du champ
// Série au moment d'appliquer un résultat, etc.). Un set() programmatique (v-model depuis
// le script) ne déclenche pas l'évènement natif "input" du champ — seule une vraie saisie
// au clavier passe cet indicateur à true.
const userEdited = ref(false)

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  // Un one-shot n'a ni série ni numéro (voir Tome.is_oneshot) — jamais de repli sur ces
  // champs ici, même si le titre n'a pas pu être déterminé (le champ reste alors vide,
  // modifiable à la main, plutôt que de chercher sur un nom de série qui n'a pas de sens).
  query.value = props.isOneshot
    ? (props.title || '')
    : [props.series, props.number].filter(Boolean).join(' ')
  if (query.value) search()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

async function search() {
  if (!query.value.trim()) return
  loading.value = true
  results.value = []
  error.value = ''
  // Raccourci "série déjà confirmée" (voir routers/scraper.py::scrape_bedetheque) réservé à
  // la recherche automatique initiale — dès que l'utilisateur a modifié la requête, une
  // recherche libre réelle est forcée, jamais silencieusement remplacée par les albums
  // d'une série qui n'a plus forcément de rapport avec ce qu'il tape.
  const series = userEdited.value ? undefined : props.series
  const seriesId = userEdited.value ? undefined : props.seriesId
  try {
    const { data } = tab.value === 'google'
      ? await scraperApi.searchGoogleBooks(query.value, series, props.number)
      : tab.value === 'comicvine'
      ? await scraperApi.searchComicVine(query.value, series)
      : await scraperApi.searchBedetheque(query.value, series, seriesId)
    results.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erreur de connexion à l\'API'
  } finally {
    loading.value = false
  }
}

function select(result) {
  selectedResult.value = result
}

function apply() {
  if (!selectedResult.value) return
  emit('select', selectedResult.value)
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">Rechercher en ligne</h2>
        <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
      </div>

      <!-- Tabs -->
      <div class="modal-tabs">
        <button
          v-for="t in [{id:'bedetheque', label:'Bedetheque'}, {id:'google', label:'Google Books'}, {id:'comicvine', label:'ComicVine'}]"
          :key="t.id"
          @click="tab = t.id; search()"
          :class="['modal-tab', { 'modal-tab-active': tab === t.id }]"
        >{{ t.label }}</button>
      </div>

      <!-- Search bar -->
      <div class="modal-search">
        <input
          v-model="query"
          type="text"
          class="form-control"
          placeholder="Titre de la série…"
          @input="userEdited = true"
          @keydown.enter="search"
        />
        <button @click="search" class="btn btn-primary btn-sm"><SvgIcon name="search" /></button>
      </div>

      <!-- Results -->
      <div class="modal-results">
        <div v-if="loading" class="modal-empty loading-pulse">Recherche…</div>
        <div v-else-if="error" class="modal-error">⚠ {{ error }}</div>
        <div v-else-if="!results.length" class="modal-empty">Aucun résultat</div>
        <ScraperResultCard
          v-for="(r, i) in results"
          :key="i"
          :result="r"
          :selected="selectedResult === r"
          @select="select"
        />
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
        <button @click="apply" :disabled="!selectedResult" class="btn btn-primary btn-sm">Appliquer</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: var(--overlay-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.modal {
  background: var(--surface-raised);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 520px;
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-title {
  flex: 1;
  font-size: 1rem;
  font-weight: 600;
}

/* Tabs */
.modal-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-tab {
  flex: 1;
  padding: 10px;
  font-size: 0.875rem;
  font-family: var(--font);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  color: var(--muted);
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}
.modal-tab:hover { color: var(--text); }
.modal-tab-active {
  color: var(--primary);
  border-bottom-color: var(--primary);
  font-weight: 500;
}

/* Search bar */
.modal-search {
  display: flex;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

/* Results */
.modal-results {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.modal-empty {
  text-align: center;
  color: var(--muted);
  font-size: 0.875rem;
  padding: 32px 0;
}

.modal-error {
  text-align: center;
  color: var(--danger);
  font-size: 0.875rem;
  padding: 24px 16px;
  background: #fff5f5;
  border-radius: var(--radius);
  border: 1px solid #ffd0d0;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.loading-pulse { animation: pulse 1.4s ease-in-out infinite; }

/* Footer */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--light);
}
</style>
