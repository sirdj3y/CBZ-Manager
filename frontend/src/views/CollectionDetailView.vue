<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { smartListsApi } from '../api/smartLists'
import { useSmartListsStore } from '../stores/smartLists'
import { useNotificationStore } from '../stores/notifications'
import { describeRules, groupsToFlat } from '../utils/smartListRules'

const route = useRoute()
const router = useRouter()
const notif = useNotificationStore()
const smartListsStore = useSmartListsStore()

const items = ref([]) // tomes ou séries, selon viewMode
// La suppression vit dans la barre latérale (AppLayout) ; la modale d'édition, elle, est
// partagée via le store (voir stores/smartLists.js) pour pouvoir s'ouvrir aussi depuis ce
// bouton "Modifier", pas seulement depuis le menu "⋮" de la sidebar.
const listMeta = computed(() => smartListsStore.lists.find(l => l.id === Number(route.params.id)) || null)
// Affichage Albums/Séries : un choix de présentation ponctuel pour CETTE page, pas une
// propriété enregistrée de la liste — les mêmes règles peuvent se regarder des deux façons
// sans dupliquer la liste (voir SmartListEditModal, qui ne demande plus ce choix à la
// création). Repart toujours sur "Albums" à l'ouverture d'une liste, pas de mémorisation.
const viewMode = ref('tome')
const isSeriesMode = computed(() => viewMode.value === 'series')
const loading = ref(true)
const loadError = ref(false)
// Catalogue de champs (pour des libellés lisibles dans le résumé des règles, ex. "Genre"
// plutôt que "Genre" brut du backend) — statique, récupéré une seule fois, indépendant de la
// liste consultée.
const fieldsCatalog = ref([])
const rulesSummary = computed(() => listMeta.value ? describeRules(listMeta.value.rules, fieldsCatalog.value) : '')
// Rappel affiché seulement si au moins un critère porte sur le fichier/les métadonnées d'un
// album (pas uniquement des critères déjà série par nature, ex. classification) — c'est dans
// ce cas précis qu'une série peut apparaître à cause d'un seul album isolé, contre-intuitif
// si on ne s'y attend pas (voir retour utilisateur : un album "one-shot" isolé faisait
// apparaître toute sa série).
const hasAlbumLevelCriteria = computed(() =>
  isSeriesMode.value && groupsToFlat(listMeta.value?.rules?.groups).some(c => c.source !== 'series')
)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    await smartListsStore.refresh()
    const { data } = isSeriesMode.value ? await smartListsApi.series(route.params.id) : await smartListsApi.tomes(route.params.id)
    items.value = data
  } catch (e) {
    loadError.value = true
    notif.error(e.response?.data?.detail || 'Liste introuvable')
  } finally {
    loading.value = false
  }
}
function setViewMode(mode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  load()
}
onMounted(async () => {
  try {
    const { data } = await smartListsApi.fields()
    fieldsCatalog.value = data
  } catch { /* résumé dégradé (noms de champs bruts) si indisponible, pas bloquant */ }
  load()
})
watch(() => route.params.id, () => { viewMode.value = 'tome'; load() })
// La modale de la fiche liste (partagée avec la sidebar) peut fermer après une sauvegarde
// qui a changé les règles (ou le type de résultat) — recharge pour rester à jour. Se
// redéclenche aussi sur une simple annulation (rien n'a changé côté serveur), sans
// conséquence autre qu'un aller-retour réseau superflu.
watch(() => smartListsStore.editorOpen, (open) => { if (!open) load() })

function fmtNumber(n) {
  if (!n) return n
  const s = String(n).trim()
  if (/^\d+$/.test(s)) return s.padStart(2, '0')
  return s
}
</script>

<template>
  <AppLayout>
    <main class="cd-main">
      <div v-if="listMeta" class="cd-header">
        <div class="cd-header-top">
          <h1 class="cd-title">{{ listMeta.name }}</h1>
          <div class="cd-view-toggle">
            <button type="button" :class="['cd-view-btn', { 'cd-view-btn-active': viewMode === 'tome' }]" @click="setViewMode('tome')">Albums</button>
            <button type="button" :class="['cd-view-btn', { 'cd-view-btn-active': viewMode === 'series' }]" @click="setViewMode('series')">Séries</button>
          </div>
          <button v-if="listMeta.can_edit" class="btn btn-secondary btn-sm" @click="smartListsStore.openEdit(listMeta)">Modifier</button>
        </div>
        <p class="cd-subtitle">
          {{ items.length }} {{ isSeriesMode ? 'série' : 'album' }}{{ items.length > 1 ? 's' : '' }}
          <span v-if="listMeta.shared"> · Partagée</span>
          <span v-if="listMeta.owner_username"> · par {{ listMeta.owner_username }}</span>
        </p>
        <p v-if="rulesSummary" class="cd-rules-summary" :title="rulesSummary">{{ rulesSummary }}</p>
        <p v-if="hasAlbumLevelCriteria" class="cd-note">Un seul album correspondant suffit à faire apparaître toute sa série.</p>
      </div>

      <div v-if="loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>
      <div v-else-if="loadError" class="state-box">
        <p class="state-desc">Cette liste est introuvable ou n'est plus accessible</p>
      </div>
      <div v-else-if="items.length === 0" class="state-box">
        <p class="state-desc">{{ isSeriesMode ? 'Aucune série ne correspond aux règles de cette liste' : 'Aucun album ne correspond aux règles de cette liste' }}</p>
      </div>

      <!-- Résultat "Albums" -->
      <div v-else-if="!isSeriesMode" class="cd-grid">
        <div
          v-for="tome in items"
          :key="tome.id"
          class="cd-card"
          :title="tome.title || tome.filename"
          @click="router.push(`/tomes/${tome.id}`)"
        >
          <div class="cd-cover">
            <img
              v-if="tome.cover_url"
              :src="tome.cover_url"
              :alt="tome.title"
              class="cd-cover-img"
              loading="lazy"
              @error="$event.target.style.display='none'"
            />
            <div v-else class="cd-cover-placeholder">📖</div>
            <span v-if="tome.is_oneshot" class="cd-badge cd-badge-oneshot">One-shot</span>
            <span v-else-if="tome.number" class="cd-badge">T{{ fmtNumber(tome.number) }}</span>
            <div class="cd-overlay" @click.stop="router.push(`/read/${tome.id}`)">
              <SvgIcon name="read" class="cd-read-icon" />
            </div>
          </div>
          <div class="cd-info">
            <p class="cd-name">{{ tome.title || tome.filename }}</p>
            <p class="cd-series">{{ tome.series_name }}</p>
            <p class="cd-meta">
              <span v-if="tome.year" class="year-badge">{{ tome.year }}</span>
              <span v-if="tome.file_format !== 'cbz'" :class="['fmt-badge', `fmt-${tome.file_format}`]">{{ tome.file_format.toUpperCase() }}</span>
              <span v-if="tome.page_count" class="cd-pages">{{ tome.page_count }} pages</span>
            </p>
          </div>
        </div>
      </div>

      <!-- Résultat "Séries" -->
      <div v-else class="cd-grid">
        <div
          v-for="series in items"
          :key="series.id"
          class="cd-card"
          :title="series.name"
          @click="router.push(`/series/${series.id}`)"
        >
          <div class="cd-cover">
            <img
              v-if="series.cover_url"
              :src="series.cover_url"
              :alt="series.name"
              class="cd-cover-img"
              loading="lazy"
              @error="$event.target.style.display='none'"
            />
            <div v-else class="cd-cover-placeholder">📚</div>
            <span v-if="series.classification" class="cd-badge">{{ series.classification }}</span>
          </div>
          <div class="cd-info">
            <p class="cd-name">{{ series.name }}</p>
            <p class="cd-meta">
              <span class="cd-pages">{{ series.tome_count }} album{{ series.tome_count > 1 ? 's' : '' }}</span>
            </p>
          </div>
        </div>
      </div>
    </main>
  </AppLayout>
</template>

<style scoped>
.cd-main {
  flex: 1;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.cd-header { display: flex; flex-direction: column; }
.cd-header-top { display: flex; align-items: center; gap: 12px; }
/* Même gabarit que le bascule Séries/Albums de ContentToolbar.vue (.view-toggle/.view-btn)
   — un choix de présentation ponctuel pour cette page, pas une propriété de la liste. */
.cd-view-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}
.cd-view-btn {
  padding: 4px 12px;
  font-size: 0.75rem; font-weight: 700; font-family: var(--font); letter-spacing: 0.06em;
  background: var(--surface); border: none; border-right: 1px solid var(--border);
  cursor: pointer; color: var(--muted);
  transition: background 0.12s, color 0.12s;
}
.cd-view-btn:last-child { border-right: none; }
.cd-view-btn:hover { background: var(--light); color: var(--text); }
.cd-view-btn-active { background: var(--primary); color: #fff; }
.cd-view-btn-active:hover { background: var(--primary-dark); color: #fff; }
.cd-title { flex: 1; min-width: 0; font-family: var(--font-display); font-weight: 400; text-transform: uppercase; font-size: 1.3rem; color: var(--text); }
.cd-subtitle { font-size: 0.82rem; color: var(--muted); margin-top: 4px; }
.cd-rules-summary {
  font-size: 0.75rem; color: var(--muted); margin-top: 4px; max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-style: italic;
}
.cd-note {
  font-size: 0.75rem; margin-top: 6px; align-self: flex-start;
  padding: 4px 10px; border-radius: var(--radius-sm);
  background: var(--info-bg); color: var(--info-text);
}

.cd-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px)  { .cd-grid { grid-template-columns: repeat(3, 1fr); } }
@media (min-width: 700px)  { .cd-grid { grid-template-columns: repeat(4, 1fr); } }
@media (min-width: 960px)  { .cd-grid { grid-template-columns: repeat(5, 1fr); } }
@media (min-width: 1200px) { .cd-grid { grid-template-columns: repeat(6, 1fr); } }
@media (min-width: 1500px) { .cd-grid { grid-template-columns: repeat(8, 1fr); } }

.cd-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.18s, transform 0.18s;
}
.cd-card:hover {
  box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg);
  transform: translateY(-2px);
}
.cd-cover {
  aspect-ratio: 0.71;
  position: relative;
  background: var(--light);
}
.cd-cover-img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s; }
.cd-card:hover .cd-cover-img { transform: scale(1.04); }
.cd-cover-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 2rem; color: var(--placeholder); }
.cd-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  padding: 1px 6px; background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.7rem; font-weight: 700; border-radius: 4px;
}
.cd-badge-oneshot { background: var(--vermilion); color: #fff; }
.cd-overlay {
  position: absolute; inset: 0; z-index: 3;
  opacity: 0; transition: opacity 0.18s;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.35);
}
.cd-card:hover .cd-overlay { opacity: 1; }
.cd-read-icon { font-size: 40px; color: #fff; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }

.cd-info { padding: 7px 9px; border-top: 1px solid var(--border); }
.cd-name {
  font-size: 0.78rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.cd-series { font-size: 0.7rem; color: var(--muted); margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cd-meta { display: flex; align-items: center; gap: 6px; min-width: 0; }
.year-badge {
  font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px;
  background: var(--light); color: var(--muted); border: 1px solid var(--border);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
}
.fmt-badge { font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }
.cd-pages { font-size: 0.72rem; color: var(--muted); }

.state-box {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; min-height: 260px; padding: 40px;
}
.state-desc  { font-size: 0.875rem; color: var(--muted); text-align: center; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }
</style>
