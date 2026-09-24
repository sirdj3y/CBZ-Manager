<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import SvgIcon from '../components/SvgIcon.vue'
import { logsApi } from '../api/logs'
import { useNotificationStore } from '../stores/notifications'
import { useSecurityAlertsStore } from '../stores/securityAlerts'

const route = useRoute()
const notif = useNotificationStore()
const securityAlertsStore = useSecurityAlertsStore()
const logs = ref([])
const loading = ref(false)
const confirmClear = ref(false)

function fmtAlertDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const ACTION_LABELS = {
  scan: 'Scan',
  convert: 'Conversion',
  delete_series: 'Suppression série',
  delete_tome: 'Suppression album',
  rename: 'Renommage',
  edit_metadata: 'Métadonnées',
  import: 'Import',
  reset_db: 'Réinitialisation DB',
  login: 'Connexion',
  user_create: 'Création utilisateur',
  user_update: 'Modification utilisateur',
  user_delete: 'Suppression utilisateur',
  user_hidden_series: 'Séries masquées',
  profile_create: 'Création profil',
  profile_update: 'Modification profil',
  profile_delete: 'Suppression profil',
  restore_backup: 'Restauration sauvegarde',
  clear_logs: 'Historique effacé',
  cleanup_orphans: 'Nettoyage diagnostic',
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
  login: 'key',
  user_create: 'author',
  user_update: 'author',
  user_delete: 'author',
  user_hidden_series: 'author',
  profile_create: 'filter',
  profile_update: 'filter',
  profile_delete: 'filter',
  restore_backup: 'database',
  clear_logs: 'history',
  cleanup_orphans: 'health',
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

// ── Filtres d'en-tête — filtrage côté client (les 500 entrées max sont déjà toutes
// chargées, voir logsApi.get()), pas besoin d'aller-retour serveur. ──
const filterDate = ref('')
const filterAction = ref('')
// Pré-rempli via ?user=xxx — voir le lien "Historique" sur la fiche d'un compte
// (SettingsUsersView.vue), qui pointe directement ici avec ce paramètre.
const filterUser = ref(typeof route.query.user === 'string' ? route.query.user : '')
const filterStatus = ref('')
const filterDetail = ref('')
const filterIp = ref('')

const distinctActions = computed(() => [...new Set(logs.value.map(l => l.action))].sort())
const distinctUsers = computed(() => [...new Set(logs.value.map(l => l.username_snapshot).filter(Boolean))].sort((a, b) => a.localeCompare(b)))

const hasActiveFilters = computed(() =>
  !!(filterDate.value || filterAction.value || filterUser.value || filterStatus.value || filterDetail.value || filterIp.value)
)

function resetFilters() {
  filterDate.value = ''
  filterAction.value = ''
  filterUser.value = ''
  filterStatus.value = ''
  filterDetail.value = ''
  filterIp.value = ''
}

// Comparaison en date LOCALE (celle affichée par fmtDate, celle que l'utilisateur choisit
// dans le sélecteur natif <input type="date">) plutôt qu'en UTC — un événement à 23h50 UTC
// n'est pas forcément affiché sous la même date qu'un simple découpage de la chaîne ISO.
function localDateStr(iso) {
  const d = new Date(iso)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const filteredLogs = computed(() => logs.value.filter(l => {
  if (filterDate.value && localDateStr(l.created_at) !== filterDate.value) return false
  if (filterAction.value && l.action !== filterAction.value) return false
  if (filterUser.value && l.username_snapshot !== filterUser.value) return false
  if (filterStatus.value && l.status !== filterStatus.value) return false
  if (filterDetail.value && !(l.description || '').toLowerCase().includes(filterDetail.value.toLowerCase())) return false
  if (filterIp.value && !(l.ip_address || '').includes(filterIp.value)) return false
  return true
}))
</script>

<template>
  <AppLayout>
    <main class="logs-main">
      <div class="logs-header">
        <h1 class="logs-heading">Historique</h1>
        <button v-if="logs.length" class="btn btn-ghost btn-sm" @click="confirmClear = true">Effacer l'historique</button>
      </div>

      <div v-if="securityAlertsStore.alerts.length" class="alerts-box">
        <div v-for="(a, i) in securityAlertsStore.alerts" :key="i" :class="['alert-row', 'alert-' + a.severity]">
          <span class="alert-label">{{ a.label }}</span>
          <span class="alert-detail">{{ a.detail }}</span>
          <span class="alert-date">{{ fmtAlertDate(a.created_at) }}</span>
        </div>
      </div>

      <div v-if="loading" class="logs-state">Chargement…</div>
      <div v-else-if="!logs.length" class="logs-state">
        <div class="logs-empty-icon">📋</div>
        <p>Aucun événement enregistré.</p>
        <p class="logs-empty-hint">Les scans, conversions, suppressions et renommages apparaîtront ici.</p>
      </div>

      <div v-else class="logs-table-wrap">
        <table class="logs-table">
          <colgroup>
            <col style="width: 15%">
            <col style="width: 16%">
            <col style="width: 34%">
            <col style="width: 12%">
            <col style="width: 13%">
            <col style="width: 10%">
          </colgroup>
          <thead>
            <tr>
              <th>Date</th>
              <th>Action</th>
              <th>Détail</th>
              <th>Utilisateur</th>
              <th>IP</th>
              <th>Statut</th>
            </tr>
            <tr class="logs-filter-row">
              <th>
                <div class="logs-filter-date-cell">
                  <input v-model="filterDate" type="date" class="logs-filter-input" />
                  <button v-if="hasActiveFilters" class="logs-filter-reset" @click="resetFilters" title="Réinitialiser les filtres">✕</button>
                </div>
              </th>
              <th>
                <select v-model="filterAction" class="logs-filter-select">
                  <option value="">Tous</option>
                  <option v-for="a in distinctActions" :key="a" :value="a">{{ ACTION_LABELS[a] || a }}</option>
                </select>
              </th>
              <th>
                <input v-model="filterDetail" type="search" class="logs-filter-input" placeholder="Rechercher…" />
              </th>
              <th>
                <select v-model="filterUser" class="logs-filter-select">
                  <option value="">Tous</option>
                  <option v-for="u in distinctUsers" :key="u" :value="u">{{ u }}</option>
                </select>
              </th>
              <th>
                <input v-model="filterIp" type="search" class="logs-filter-input" placeholder="IP…" />
              </th>
              <th>
                <select v-model="filterStatus" class="logs-filter-select">
                  <option value="">Tous</option>
                  <option value="ok">OK</option>
                  <option value="error">Erreur</option>
                </select>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredLogs.length">
              <td colspan="6" class="logs-no-match">Aucune entrée ne correspond à ces filtres.</td>
            </tr>
            <tr v-for="log in filteredLogs" :key="log.id" :class="'log-row-' + log.status">
              <td class="log-date">{{ fmtDate(log.created_at) }}</td>
              <td class="log-action">
                <div class="log-action-inner">
                  <SvgIcon v-if="ACTION_ICONS[log.action]" :name="ACTION_ICONS[log.action]" class="log-icon" />
                  <span class="log-action-text">{{ ACTION_LABELS[log.action] || log.action }}</span>
                </div>
              </td>
              <td class="log-desc">{{ log.description }}</td>
              <td class="log-user">{{ log.username_snapshot || '—' }}</td>
              <td class="log-ip">{{ log.ip_address || '—' }}</td>
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
  max-width: 1100px; margin: 0 auto; width: 100%;
}
.logs-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.logs-heading {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 1.4rem; color: var(--text);
}

.logs-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 8px; padding: 60px 20px; color: var(--muted);
  font-size: 0.875rem; text-align: center;
}
.logs-empty-icon { font-size: 3rem; }
.logs-empty-hint { font-size: 0.8rem; color: var(--muted); }

.alerts-box {
  display: flex; flex-direction: column; gap: 6px;
  margin-bottom: 20px;
}
.alert-row {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
}
.alert-warning { background: var(--warning-bg, #fffbeb); color: var(--orange-bar, #b45309); }
.alert-error { background: var(--danger-bg-light); color: var(--danger); }
.alert-info { background: var(--info-bg); color: var(--info-text); }
.alert-label { font-weight: 700; flex-shrink: 0; }
.alert-detail { flex: 1; min-width: 0; }
.alert-date { font-size: 0.75rem; opacity: 0.8; flex-shrink: 0; }

.logs-table-wrap { overflow-x: auto; }
.logs-table {
  /* Sans min-width, table-layout:fixed + colgroup en % réduit chaque colonne à néant sur un
     petit écran au lieu de faire défiler horizontalement (le wrapper a overflow-x:auto, mais
     il ne se déclenche jamais tant que la table peut encore rétrécir pour tenir à 100%). En
     dessous de cette largeur, la table garde des colonnes lisibles et déborde dans le
     wrapper, qui prend le relais avec un défilement horizontal. */
  min-width: 760px;
  width: 100%; border-collapse: collapse;
  table-layout: fixed;
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
.logs-table tbody tr:last-child td { border-bottom: none; }
.logs-table tbody tr:hover td { background: var(--light); }

.logs-filter-row th {
  padding: 6px 10px 10px;
  text-transform: none; font-weight: 400;
  background: var(--light);
}
.logs-filter-select, .logs-filter-input {
  width: 100%; box-sizing: border-box;
  padding: 4px 8px;
  font-family: var(--font); font-size: 0.78rem;
  color: var(--text); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.logs-filter-select:focus, .logs-filter-input:focus {
  outline: none; border-color: var(--primary-focus-border); box-shadow: 0 0 0 2px var(--primary-focus);
}
.logs-filter-date-cell { display: flex; align-items: center; gap: 4px; }
.logs-filter-reset {
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 0.85rem; line-height: 1;
  padding: 4px; flex-shrink: 0;
}
.logs-filter-reset:hover { color: var(--vermilion); }

.logs-no-match { text-align: center; color: var(--muted); font-size: 0.85rem; padding: 24px 14px !important; }

.log-row-error td { background: var(--danger-bg-light); }
.log-row-error:hover td { background: var(--danger-bg); }

.log-date { color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* .log-action reste une cellule normale (pas display:flex directement dessus) — un <td> en
   flex casse le calcul de largeur de table-layout:fixed dans certains navigateurs, ce qui
   laissait le contenu déborder visuellement sur la colonne Détail au lieu d'être contenu
   dans sa cellule. Le flex vit uniquement sur .log-action-inner, un simple bloc enfant qui
   hérite correctement de la largeur figée de la cellule. */
.log-action { font-weight: 500; overflow: hidden; }
.log-action-inner { display: flex; align-items: center; min-width: 0; }
.log-icon { width: 14px; height: 14px; font-size: 14px; margin-right: 6px; flex-shrink: 0; color: var(--muted); }
.log-action-text {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0; /* sans ça, un enfant flex ne rétrécit jamais sous sa taille de contenu —
    text-overflow n'a alors jamais l'occasion de s'appliquer. */
}
.log-desc { color: var(--text); overflow-wrap: break-word; word-break: break-word; }
.log-user { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.log-ip { color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; }

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
