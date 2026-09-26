<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../../components/layout/AppLayout.vue'
import client from '../../api/client'
import { tomesApi } from '../../api/tomes'
import { useNotificationStore } from '../../stores/notifications'
import Hint from '../../components/ui/Hint.vue'

const notif = useNotificationStore()
const router = useRouter()

const loading = ref(false)
const result = ref(null)
const scanProgress = ref({ status: 'idle', processed: 0, total: 0 })
const deletingIds = ref(new Set())
let pollTimer = null

const SEVERITY_LABEL = { error: 'Erreur', warning: 'Attention', info: 'Info' }
const SEVERITY_ORDER = { info: 0, warning: 1, error: 2 }

async function analyze() {
  loading.value = true
  try {
    const { data } = await client.get('/api/health-check')
    result.value = data
  } catch (e) {
    notif.error('Erreur lors de l\'analyse')
  } finally {
    loading.value = false
  }
}

const isScanning = () => scanProgress.value.status === 'running' || scanProgress.value.status === 'pending'

function pollScan(jobId) {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const { data } = await client.get(`/api/health-check/scan/${jobId}`)
      scanProgress.value = data
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(pollTimer)
        if (data.status === 'error') notif.error(data.error_msg || "Erreur pendant l'analyse")
        await analyze()
      }
    } catch {
      clearInterval(pollTimer)
    }
  }, 2000)
}

// Analyse complète : relance à la fois les vérifications bon marché (fichiers manquants,
// métadonnées absentes...) et le hashing de contenu pour les doublons (coûteux — seuls les
// fichiers pas encore hachés ou modifiés depuis sont retraités, jamais toute la bibliothèque
// à chaque clic).
async function startFullScan() {
  try {
    const { data } = await client.post('/api/health-check/scan')
    scanProgress.value = { status: 'pending', processed: 0, total: 0 }
    pollScan(data.job_id)
  } catch (e) {
    notif.error(e.response?.data?.detail || "Impossible de démarrer l'analyse")
  }
}

async function deleteDuplicate(tomeId) {
  deletingIds.value.add(tomeId)
  deletingIds.value = new Set(deletingIds.value)
  try {
    await tomesApi.deleteFile(tomeId)
    result.value.issues = result.value.issues.filter(i => i.tome_id !== tomeId)
    result.value.summary.warning = Math.max(0, result.value.summary.warning - 1)
    result.value.summary.total = Math.max(0, result.value.summary.total - 1)
    notif.success('Album supprimé')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deletingIds.value.delete(tomeId)
    deletingIds.value = new Set(deletingIds.value)
  }
}

// Données orphelines : une ligne par type (pas d'album associé), nettoyée d'un coup côté
// serveur — voir backend/services/orphaned_data.py.
async function cleanOrphans(issue) {
  const id = issue.orphan_key
  deletingIds.value.add(id)
  deletingIds.value = new Set(deletingIds.value)
  try {
    const { data } = await client.delete(`/api/health-check/orphaned-data/${id}`)
    result.value.issues = result.value.issues.filter(i => i.orphan_key !== id)
    result.value.summary.warning = Math.max(0, result.value.summary.warning - 1)
    result.value.summary.total = Math.max(0, result.value.summary.total - 1)
    notif.success(`${data.deleted} ligne(s) orpheline(s) supprimée(s)`)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors du nettoyage')
  } finally {
    deletingIds.value.delete(id)
    deletingIds.value = new Set(deletingIds.value)
  }
}

onMounted(async () => {
  await analyze()
  try {
    const { data } = await client.get('/api/health-check/scan/last')
    scanProgress.value = data
    if (isScanning()) pollScan(data.job_id)
  } catch { /* pas bloquant */ }
})
onUnmounted(() => clearInterval(pollTimer))

// ── Filtres d'en-tête — même pattern que la page Historique (LogsView.vue) : filtrage
// côté client, une entrée par colonne, réinitialisables en un clic. ──
const filterSeverity = ref('')
const filterType = ref('')
const filterSeries = ref('')
const filterAlbum = ref('')
const filterFormat = ref('')
const filterDetail = ref('')

const distinctTypes = computed(() => {
  if (!result.value) return []
  const seen = new Map()
  for (const i of result.value.issues) if (!seen.has(i.type)) seen.set(i.type, i.label)
  return [...seen.entries()].map(([type, label]) => ({ type, label }))
})
const distinctFormats = computed(() => {
  if (!result.value) return []
  return [...new Set(result.value.issues.map(i => i.file_format).filter(Boolean))].sort()
})

const hasActiveFilters = computed(() =>
  !!(filterSeverity.value || filterType.value || filterSeries.value || filterAlbum.value || filterFormat.value || filterDetail.value)
)
function resetFilters() {
  filterSeverity.value = ''
  filterType.value = ''
  filterSeries.value = ''
  filterAlbum.value = ''
  filterFormat.value = ''
  filterDetail.value = ''
}

// Bouton résumé (info/avertissement/erreur) — bascule le même filtre que le sélecteur
// Sévérité de l'en-tête plutôt qu'un état séparé, pour rester cohérent avec un seul et même
// filtre affiché aux deux endroits.
function toggleSeverityBadge(sev) {
  filterSeverity.value = filterSeverity.value === sev ? '' : sev
}

const filteredIssues = computed(() => {
  if (!result.value) return []
  const issues = [...result.value.issues].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
  )
  return issues.filter(i => {
    if (filterSeverity.value && i.severity !== filterSeverity.value) return false
    if (filterType.value && i.type !== filterType.value) return false
    if (filterSeries.value && !(i.series_title || '').toLowerCase().includes(filterSeries.value.toLowerCase())) return false
    if (filterAlbum.value && !(i.tome_title || '').toLowerCase().includes(filterAlbum.value.toLowerCase())) return false
    if (filterFormat.value && i.file_format !== filterFormat.value) return false
    if (filterDetail.value && !(i.detail || '').toLowerCase().includes(filterDetail.value.toLowerCase())) return false
    return true
  })
})
</script>

<template>
  <AppLayout>
    <main class="health-main">
      <div class="health-header">
        <div>
          <h1 class="settings-heading">Diagnostic</h1>
          <p class="page-hint">Analyse complète de la bibliothèque : fichiers manquants, métadonnées absentes, doublons (comparaison du contenu réel des fichiers), données orphelines, etc.</p>
        </div>
        <button class="btn btn-primary btn-sm" :disabled="isScanning()" @click="startFullScan">
          {{ isScanning() ? 'Analyse en cours…' : 'Lancer une analyse complète' }}
        </button>
      </div>

      <div v-if="isScanning()" class="health-progress-bar">
        <div class="health-progress-fill" :style="{ width: scanProgress.total ? (scanProgress.processed / scanProgress.total * 100) + '%' : '2%' }" />
      </div>
      <p v-if="isScanning() && scanProgress.total" class="page-hint" style="margin-bottom:16px;">
        {{ scanProgress.processed }} / {{ scanProgress.total }} fichier(s) — comparaison du contenu pour les doublons
      </p>

      <!-- Loading state -->
      <div v-if="loading && !result" class="health-loading">
        <span class="scan-spinner"></span>
        Analyse en cours…
      </div>

      <!-- Résumé -->
      <div v-if="result" class="health-summary">
        <div :class="['summary-badge', 'badge-info', { 'badge-inactive': result.summary.info === 0 }]" @click="toggleSeverityBadge('info')">
          {{ result.summary.info }} info{{ result.summary.info > 1 ? 's' : '' }}
        </div>
        <div :class="['summary-badge', 'badge-warning', { 'badge-inactive': result.summary.warning === 0 }]" @click="toggleSeverityBadge('warning')">
          {{ result.summary.warning }} avertissement{{ result.summary.warning > 1 ? 's' : '' }}
        </div>
        <div :class="['summary-badge', 'badge-error', { 'badge-inactive': result.summary.error === 0 }]" @click="toggleSeverityBadge('error')">
          {{ result.summary.error }} erreur{{ result.summary.error > 1 ? 's' : '' }}
        </div>
        <div v-if="result.summary.total === 0" class="summary-ok">
          ✅ Aucun problème détecté
        </div>
      </div>

      <!-- Tableau -->
      <div v-if="result && result.issues.length > 0" class="health-table-wrap">
        <table class="health-table">
          <thead>
            <tr>
              <th>Sévérité</th>
              <th>Problème</th>
              <th>Série</th>
              <th>Album</th>
              <th>Format</th>
              <th>Détail</th>
              <th></th>
            </tr>
            <tr class="health-filter-row">
              <th>
                <div class="health-filter-severity-cell">
                  <select v-model="filterSeverity" class="health-filter-select">
                    <option value="">Toutes</option>
                    <option value="error">Erreur</option>
                    <option value="warning">Attention</option>
                    <option value="info">Info</option>
                  </select>
                  <Hint v-if="hasActiveFilters" label="Réinitialiser les filtres">
                    <button class="health-filter-reset" @click="resetFilters">✕</button>
                  </Hint>
                </div>
              </th>
              <th>
                <select v-model="filterType" class="health-filter-select">
                  <option value="">Tous</option>
                  <option v-for="t in distinctTypes" :key="t.type" :value="t.type">{{ t.label }}</option>
                </select>
              </th>
              <th><input v-model="filterSeries" type="search" class="health-filter-input" placeholder="Rechercher…" /></th>
              <th><input v-model="filterAlbum" type="search" class="health-filter-input" placeholder="Rechercher…" /></th>
              <th>
                <select v-model="filterFormat" class="health-filter-select">
                  <option value="">Tous</option>
                  <option v-for="f in distinctFormats" :key="f" :value="f">{{ f.toUpperCase() }}</option>
                </select>
              </th>
              <th><input v-model="filterDetail" type="search" class="health-filter-input" placeholder="Rechercher…" /></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredIssues.length">
              <td colspan="7" class="health-no-match">Aucune entrée ne correspond à ces filtres.</td>
            </tr>
            <tr v-for="issue in filteredIssues" :key="`${issue.type}-${issue.tome_id ?? issue.orphan_key}`">
              <td>
                <span :class="['sev-badge', `sev-${issue.severity}`]">{{ SEVERITY_LABEL[issue.severity] }}</span>
              </td>
              <td class="issue-label">{{ issue.label }}</td>
              <td>
                <span v-if="issue.series_title" class="issue-series" @click="router.push(`/series/${issue.series_id}`)" title="Voir la série">
                  {{ issue.series_title }}
                </span>
                <span v-else class="issue-na">—</span>
              </td>
              <td>
                <span v-if="issue.tome_id" class="issue-tome" @click="router.push(`/tomes/${issue.tome_id}`)" title="Voir l'album">
                  {{ issue.tome_title }}
                </span>
                <span v-else>{{ issue.tome_title }}</span>
              </td>
              <td class="issue-format">
                <span v-if="issue.file_format" class="format-badge">{{ issue.file_format.toUpperCase() }}</span>
                <span v-else class="issue-na">—</span>
              </td>
              <td class="issue-detail">{{ issue.detail || '—' }}</td>
              <td class="issue-actions">
                <button
                  v-if="issue.type === 'duplicate'"
                  class="btn btn-danger btn-xs"
                  :disabled="deletingIds.has(issue.tome_id)"
                  @click="deleteDuplicate(issue.tome_id)"
                >
                  {{ deletingIds.has(issue.tome_id) ? 'Suppression…' : 'Supprimer' }}
                </button>
                <button
                  v-else-if="issue.type === 'orphaned_data'"
                  class="btn btn-danger btn-xs"
                  :disabled="deletingIds.has(issue.orphan_key)"
                  title="Supprime ces lignes de la base — elles ne se rattachent plus à rien"
                  @click="cleanOrphans(issue)"
                >
                  {{ deletingIds.has(issue.orphan_key) ? 'Nettoyage…' : 'Nettoyer' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </AppLayout>
</template>

<style scoped>
.health-main {
  flex: 1; padding: 24px 20px;
  max-width: 1100px; margin: 0 auto; width: 100%;
}
.health-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.settings-heading {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 1.4rem; margin-bottom: 4px; color: var(--text);
}
.page-hint { font-size: 0.8rem; color: var(--muted); margin: 0; }

.health-progress-bar {
  height: 4px; margin-bottom: 16px;
  background: var(--border); border-radius: 2px; overflow: hidden;
}
.health-progress-fill { height: 100%; background: var(--primary); transition: width 0.4s ease; }

.health-loading {
  display: flex; align-items: center; gap: 10px;
  font-size: 0.85rem; color: var(--muted); padding: 24px 0;
}

.health-summary {
  display: flex; gap: 8px; flex-wrap: wrap;
  margin-bottom: 16px; align-items: center;
}
.summary-badge {
  padding: 4px 12px; border-radius: 20px;
  font-size: 0.8rem; font-weight: 600; cursor: pointer;
  transition: opacity 0.15s;
}
.badge-error   { background: var(--danger-bg);  color: var(--danger); }
.badge-warning { background: var(--warning-bg); color: var(--orange-bar); }
.badge-info    { background: var(--info-bg);    color: var(--info-text); }
.badge-inactive { opacity: 0.4; cursor: default; }
.summary-ok { font-size: 0.85rem; color: var(--success); font-weight: 600; }

.health-table-wrap { overflow-x: auto; }
.health-table {
  width: 100%; border-collapse: collapse;
  font-size: 0.82rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.health-table th {
  text-align: left; padding: 10px 14px;
  background: var(--light); color: var(--muted);
  font-weight: 600; font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.health-table td { padding: 9px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.health-table tbody tr:last-child td { border-bottom: none; }
.health-table tbody tr:hover td { background: var(--light); }

/* Lignes blanches — seule la sévérité (badge coloré) porte la couleur, plus de teinte de
   fond par ligne (retour utilisateur, uniformisé avec la page Historique). */
.health-filter-row th {
  padding: 6px 10px 10px;
  text-transform: none; font-weight: 400;
  background: var(--light);
}
.health-filter-select, .health-filter-input {
  width: 100%; box-sizing: border-box;
  padding: 4px 8px;
  font-family: var(--font); font-size: 0.78rem;
  color: var(--text); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.health-filter-select:focus, .health-filter-input:focus {
  outline: none; border-color: var(--primary-focus-border); box-shadow: 0 0 0 2px var(--primary-focus);
}
.health-filter-severity-cell { display: flex; align-items: center; gap: 4px; }
.health-filter-reset {
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 0.85rem; line-height: 1;
  padding: 4px; flex-shrink: 0;
}
.health-filter-reset:hover { color: var(--vermilion); }
.health-no-match { text-align: center; color: var(--muted); font-size: 0.85rem; padding: 24px 14px !important; }

.sev-badge { padding: 1px 7px; border-radius: 20px; font-size: 0.7rem; font-weight: 700; white-space: nowrap; }
.sev-error   { background: var(--danger-bg);  color: var(--danger); }
.sev-warning { background: var(--warning-bg); color: var(--orange-bar); }
.sev-info    { background: var(--info-bg);    color: var(--info-text); }

.issue-label { font-weight: 600; white-space: nowrap; }
.issue-series {
  color: var(--muted); cursor: pointer;
  max-width: 160px; display: inline-block;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 0.78rem;
}
.issue-series:hover { color: var(--vermilion); text-decoration: underline; }
.issue-tome {
  color: var(--vermilion); cursor: pointer;
  max-width: 240px; display: inline-block;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.issue-tome:hover { text-decoration: underline; }
.issue-format { white-space: nowrap; }
.format-badge {
  font-size: 0.68rem; font-weight: 700; padding: 1px 6px;
  border-radius: 4px; background: var(--light);
  color: var(--muted); border: 1px solid var(--border);
  font-family: monospace; letter-spacing: 0.03em;
}
.issue-na { color: var(--muted); }
.issue-detail { color: var(--muted); font-family: monospace; font-size: 0.72rem; max-width: 200px; word-break: break-all; }
.issue-actions { white-space: nowrap; }
.btn-xs { padding: 3px 10px; font-size: 0.75rem; }

.scan-spinner { width: 14px; height: 14px; flex-shrink: 0; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
