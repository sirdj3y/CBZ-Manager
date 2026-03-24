<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../../components/layout/AppLayout.vue'
import client from '../../api/client'
import { useNotificationStore } from '../../stores/notifications'

const notif = useNotificationStore()
const router = useRouter()

const loading = ref(false)
const result = ref(null)
const activeFilter = ref('all')

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

onMounted(() => analyze())

const filteredIssues = computed(() => {
  if (!result.value) return []
  const issues = [...result.value.issues].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
  )
  if (activeFilter.value === 'all') return issues
  return issues.filter(i => i.severity === activeFilter.value || i.type === activeFilter.value)
})
</script>

<template>
  <AppLayout>
    <main class="health-main">
      <div class="health-header">
        <div>
          <h1 class="settings-heading">Diagnostic</h1>
          <p class="page-hint">Analyse la bibliothèque et liste les albums problématiques : fichiers manquants, doublons, métadonnées absentes, etc.</p>
        </div>
        <button class="btn btn-primary btn-sm" :disabled="loading" @click="analyze">
          <span v-if="loading">Analyse en cours…</span>
          <span v-else>Relancer l'analyse</span>
        </button>
      </div>

      <!-- Loading state -->
      <div v-if="loading && !result" class="health-loading">
        <span class="scan-spinner"></span>
        Analyse en cours…
      </div>

      <!-- Résumé -->
      <div v-if="result" class="health-summary">
        <div :class="['summary-badge', 'badge-info', { 'badge-inactive': result.summary.info === 0 }]" @click="activeFilter = activeFilter === 'info' ? 'all' : 'info'">
          {{ result.summary.info }} info{{ result.summary.info > 1 ? 's' : '' }}
        </div>
        <div :class="['summary-badge', 'badge-warning', { 'badge-inactive': result.summary.warning === 0 }]" @click="activeFilter = activeFilter === 'warning' ? 'all' : 'warning'">
          {{ result.summary.warning }} avertissement{{ result.summary.warning > 1 ? 's' : '' }}
        </div>
        <div :class="['summary-badge', 'badge-error', { 'badge-inactive': result.summary.error === 0 }]" @click="activeFilter = activeFilter === 'error' ? 'all' : 'error'">
          {{ result.summary.error }} erreur{{ result.summary.error > 1 ? 's' : '' }}
        </div>
        <div v-if="result.summary.total === 0" class="summary-ok">
          ✅ Aucun problème détecté
        </div>
      </div>

      <!-- Tableau -->
      <div v-if="result && filteredIssues.length > 0" class="health-table-wrap">
        <table class="health-table">
          <thead>
            <tr>
              <th>Sévérité</th>
              <th>Problème</th>
              <th>Série</th>
              <th>Album</th>
              <th>Format</th>
              <th>Détail</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="issue in filteredIssues" :key="`${issue.type}-${issue.tome_id}`" :class="`row-${issue.severity}`">
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
                <span class="issue-tome" @click="router.push(`/tomes/${issue.tome_id}`)" title="Voir l'album">
                  {{ issue.tome_title }}
                </span>
              </td>
              <td class="issue-format">
                <span v-if="issue.file_format" class="format-badge">{{ issue.file_format.toUpperCase() }}</span>
                <span v-else class="issue-na">—</span>
              </td>
              <td class="issue-detail">{{ issue.detail || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="result && filteredIssues.length === 0 && result.summary.total > 0" class="health-empty">
        Aucun problème dans cette catégorie.
      </div>
    </main>
  </AppLayout>
</template>

<style scoped>
.health-main {
  flex: 1; padding: 24px 20px;
  max-width: 900px; margin: 0 auto; width: 100%;
}
.health-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.settings-heading {
  font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; color: var(--text);
}
.page-hint { font-size: 0.8rem; color: var(--muted); margin: 0; }

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
.health-table tr:last-child td { border-bottom: none; }
.health-table tr:hover td { background: var(--light); }
.row-error td   { background: var(--danger-bg-light); }
.row-error:hover td { background: var(--danger-bg); }
.row-warning td { background: color-mix(in srgb, var(--warning-bg) 30%, transparent); }
.row-warning:hover td { background: color-mix(in srgb, var(--warning-bg) 50%, transparent); }

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
.issue-series:hover { color: var(--primary); text-decoration: underline; }
.issue-tome {
  color: var(--primary); cursor: pointer;
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

.health-empty { text-align: center; color: var(--muted); font-size: 0.85rem; padding: 20px 0; }

.scan-spinner { width: 14px; height: 14px; flex-shrink: 0; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
