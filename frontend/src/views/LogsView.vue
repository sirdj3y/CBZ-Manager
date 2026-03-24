<script setup>
import { ref, onMounted } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { logsApi } from '../api/logs'
import { useNotificationStore } from '../stores/notifications'

const notif = useNotificationStore()
const logs = ref([])
const loading = ref(false)
const confirmClear = ref(false)

const ACTION_LABELS = {
  scan: 'Scan',
  convert: 'Conversion',
  delete_series: 'Suppression série',
  delete_tome: 'Suppression album',
  rename: 'Renommage',
  edit_metadata: 'Métadonnées',
  import: 'Import',
  reset_db: 'Réinitialisation DB',
}

const ACTION_ICONS = {
  scan: 'refresh',
  convert: 'convert',
  delete_series: 'hide',
  delete_tome: 'hide',
  rename: 'rename',
  edit_metadata: 'edit',
  import: 'import2',
  reset_db: 'database',
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const { data } = await logsApi.get()
    logs.value = data
  } finally {
    loading.value = false
  }
}

async function clearLogs() {
  await logsApi.clear()
  logs.value = []
  confirmClear.value = false
  notif.success('Historique effacé')
}

onMounted(load)
</script>

<template>
  <AppLayout>
    <main class="logs-main">
      <div class="logs-header">
        <h1 class="logs-heading">Historique</h1>
        <button v-if="logs.length" class="btn btn-ghost btn-sm" @click="confirmClear = true">Effacer l'historique</button>
      </div>

      <div v-if="loading" class="logs-state">Chargement…</div>
      <div v-else-if="!logs.length" class="logs-state">
        <div class="logs-empty-icon">📋</div>
        <p>Aucun événement enregistré.</p>
        <p class="logs-empty-hint">Les scans, conversions, suppressions et renommages apparaîtront ici.</p>
      </div>

      <div v-else class="logs-table-wrap">
        <table class="logs-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Action</th>
              <th>Détail</th>
              <th>Statut</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" :class="'log-row-' + log.status">
              <td class="log-date">{{ fmtDate(log.created_at) }}</td>
              <td class="log-action">
                <SvgIcon v-if="ACTION_ICONS[log.action]" :name="ACTION_ICONS[log.action]" class="log-icon" />
                {{ ACTION_LABELS[log.action] || log.action }}
              </td>
              <td class="log-desc">{{ log.description }}</td>
              <td class="log-status">
                <span :class="'log-badge log-badge-' + log.status">
                  {{ log.status === 'ok' ? 'OK' : 'Erreur' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>

    <!-- Confirmation effacement -->
    <div v-if="confirmClear" class="confirm-backdrop" @click.self="confirmClear = false">
      <div class="confirm-box">
        <p class="confirm-title">Effacer l'historique ?</p>
        <p class="confirm-desc">Toutes les entrées seront supprimées définitivement.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmClear = false">Annuler</button>
          <button class="btn btn-danger btn-sm" @click="clearLogs">Effacer</button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.logs-main {
  flex: 1; padding: 24px 20px;
  max-width: 900px; margin: 0 auto; width: 100%;
}
.logs-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.logs-heading { font-size: 1.4rem; font-weight: 700; color: var(--text); }

.logs-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 8px; padding: 60px 20px; color: var(--muted);
  font-size: 0.875rem; text-align: center;
}
.logs-empty-icon { font-size: 3rem; }
.logs-empty-hint { font-size: 0.8rem; color: var(--muted); }

.logs-table-wrap { overflow-x: auto; }
.logs-table {
  width: 100%; border-collapse: collapse;
  font-size: 0.82rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.logs-table th {
  text-align: left; padding: 10px 14px;
  background: var(--light); color: var(--muted);
  font-weight: 600; font-size: 0.75rem; text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.logs-table td { padding: 9px 14px; border-bottom: 1px solid var(--border); }
.logs-table tr:last-child td { border-bottom: none; }
.logs-table tr:hover td { background: var(--light); }

.log-row-error td { background: var(--danger-bg-light); }
.log-row-error:hover td { background: var(--danger-bg); }

.log-date { color: var(--muted); white-space: nowrap; }
.log-action { white-space: nowrap; font-weight: 500; display: flex; align-items: center; }
.log-icon { width: 14px; height: 14px; font-size: 14px; margin-right: 6px; flex-shrink: 0; color: var(--muted); }
.log-desc { color: var(--text); }

.log-badge {
  display: inline-block; padding: 2px 8px;
  border-radius: 20px; font-size: 0.72rem; font-weight: 600;
}
.log-badge-ok { background: var(--success-bg-light); color: var(--success); }
.log-badge-error { background: var(--danger-bg-light); color: var(--danger); }

/* Confirm */
.confirm-backdrop {
  position: fixed; inset: 0; z-index: 500;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.confirm-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  padding: 24px; max-width: 400px; width: 100%;
}
.confirm-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.confirm-desc { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.confirm-btns { display: flex; justify-content: flex-end; gap: 8px; }
</style>
