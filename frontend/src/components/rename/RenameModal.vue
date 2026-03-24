<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { tomesApi } from '../../api/tomes'

const props = defineProps({
  tomes: { type: Array, required: true },
  seriesName: { type: String, default: '' },
})
const emit = defineEmits(['close', 'done'])

const TOKENS = ['{Fichier}', '{Série}', '{Numéro}', '{Titre}', '{Année}', '{Dessinateur}', '{Scénariste}', '{Éditeur}']

const rules = ref([
  { enabled: false, search: '', replace: '' },
])
const showRules = ref(true)
const pattern = ref('{Série} - {Numéro} - {Titre}')
const inputRef = ref(null)
const saving = ref(false)
const result = ref(null)
const metaMap = ref({})
const loadingMeta = ref(true)
const overrides = ref({})

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  await Promise.all(props.tomes.map(async t => {
    try {
      const { data } = await tomesApi.getMetadata(t.id)
      metaMap.value[t.id] = data
    } catch { metaMap.value[t.id] = {} }
  }))
  loadingMeta.value = false
})

onUnmounted(() => window.removeEventListener('keydown', onKey))

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}

function applyRules(s) {
  for (const rule of rules.value) {
    if (!rule.enabled || !rule.search) continue
    s = s.split(rule.search).join(rule.replace)
  }
  return s
}

function formatNumber(n) {
  if (!n) return ''
  const extracted = n.replace(/\D.*/, '').trim()
  if (!extracted) return n
  const num = parseInt(extracted, 10)
  if (isNaN(num)) return n
  if (/^\d+$/.test(extracted) && num < 10 && extracted.length === 1) {
    return String(num).padStart(2, '0')
  }
  return extracted
}

function applyPatternJS(pat, tome) {
  const ext = tome.filename.includes('.') ? '.' + tome.filename.split('.').pop() : ''
  const stem = tome.filename.includes('.')
    ? tome.filename.slice(0, tome.filename.lastIndexOf('.'))
    : tome.filename
  const m = metaMap.value[tome.id] || {}
  let r = pat
  r = r.replace(/{Fichier}/g, stem)
  r = r.replace(/{Filename}/g, stem)
  r = r.replace(/{Série}/g, m.Series || props.seriesName || '')
  r = r.replace(/{Series}/g, m.Series || props.seriesName || '')
  r = r.replace(/{Numéro}/g, formatNumber(m.Number || tome.number || ''))
  r = r.replace(/{Number}/g, formatNumber(m.Number || tome.number || ''))
  r = r.replace(/{Titre}/g, m.Title || tome.title || '')
  r = r.replace(/{Title}/g, m.Title || tome.title || '')
  r = r.replace(/{Année}/g, m.Year || '')
  r = r.replace(/{Year}/g, m.Year || '')
  r = r.replace(/{Dessinateur}/g, m.Penciller || tome.penciller || '')
  r = r.replace(/{Scénariste}/g, m.Writer || tome.writer || '')
  r = r.replace(/{Writer}/g, m.Writer || tome.writer || '')
  r = r.replace(/{Éditeur}/g, m.Publisher || tome.publisher || '')
  r = r.replace(/{Publisher}/g, m.Publisher || tome.publisher || '')
  r = r.replace(/[<>:"/\\|?*]/g, '_')
  r = r.replace(/\s{2,}/g, ' ').trim()
  r = r.replace(/_+/g, '_').replace(/^_+|_+$/g, '').trim()
  if (!r) r = stem
  // Appliquer les règles après sanitisation pour préserver les remplacements manuels
  r = applyRules(r)
  return r + ext
}

const sortedTomes = computed(() =>
  [...props.tomes].sort((a, b) => a.filename.localeCompare(b.filename, 'fr', { numeric: true }))
)

const preview = computed(() => {
  const rows = sortedTomes.value.map(t => {
    const computed_ = applyPatternJS(pattern.value, t)
    const final = overrides.value[t.id] !== undefined ? overrides.value[t.id] : computed_
    return { tome: t, current: t.filename, computed: computed_, final }
  })
  const finalNames = rows.map(r => r.final)
  return rows.map((r, i) => {
    const unchanged = r.final === r.current && overrides.value[r.tome.id] === undefined
    const conflict = finalNames.filter((n, j) => n === r.final && j !== i).length > 0
    return { ...r, unchanged, conflict }
  })
})

function onInputChange(tomeId, value) {
  const row = preview.value.find(r => r.tome.id === tomeId)
  if (row && value === row.computed) {
    const o = { ...overrides.value }
    delete o[tomeId]
    overrides.value = o
  } else {
    overrides.value = { ...overrides.value, [tomeId]: value }
  }
}

function onInputBlur(tomeId, value) {
  if (!value.trim()) {
    const o = { ...overrides.value }
    delete o[tomeId]
    overrides.value = o
  }
}

function insertToken(token) {
  if (!inputRef.value) { pattern.value += token; return }
  inputRef.value.focus()
  const start = inputRef.value.selectionStart ?? pattern.value.length
  const end = inputRef.value.selectionEnd ?? pattern.value.length
  pattern.value = pattern.value.slice(0, start) + token + pattern.value.slice(end)
  const pos = start + token.length
  inputRef.value.setSelectionRange(pos, pos)
}

function addRule() {
  rules.value.push({ enabled: true, search: '', replace: '' })
}

function removeRule(i) {
  rules.value.splice(i, 1)
}

async function doRename() {
  saving.value = true
  result.value = null
  try {
    const renames = preview.value
      .filter(r => r.final !== r.current)
      .map(r => ({ id: r.tome.id, new_filename: r.final }))
    if (renames.length === 0) {
      result.value = { ok: 0, errors: ['Aucun fichier à renommer'] }
      return
    }
    const { data } = await tomesApi.renameBulkToNames(renames)
    result.value = data
  } catch (e) {
    result.value = { ok: 0, errors: [e.response?.data?.detail || String(e)] }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-backdrop" @click="$emit('close')" />

    <div class="modal-wrap">
      <div class="modal-box">
        <div class="modal-header">
          <div class="modal-header-info">
            <p class="modal-title">Renommer {{ tomes.length }} fichier{{ tomes.length !== 1 ? 's' : '' }}</p>
          </div>
          <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
        </div>

        <div class="modal-body">
          <div v-if="loadingMeta" class="loading-meta">Chargement des métadonnées…</div>

          <template v-else>
            <div class="rules-section">
              <button class="rules-toggle" type="button" @click="showRules = !showRules">
                <span class="rules-toggle-arrow" :class="{ open: showRules }">▶</span>
                Rechercher / Remplacer
              </button>

              <div v-if="showRules" class="rules-list">
                <div v-for="(rule, i) in rules" :key="i" class="rule-row">
                  <input type="checkbox" v-model="rule.enabled" class="rule-checkbox" />
                  <input type="text" v-model="rule.search" class="form-control rule-input" placeholder="Rechercher" />
                  <span class="rule-arrow">→</span>
                  <input type="text" v-model="rule.replace" class="form-control rule-input" placeholder="vide = supprimer" />
                  <button type="button" class="btn btn-ghost btn-icon btn-sm" @click="removeRule(i)">🗑</button>
                </div>
                <button type="button" class="btn btn-ghost btn-sm add-rule-btn" @click="addRule">+ Ajouter une règle</button>
              </div>
            </div>

            <div class="field-row">
              <label class="form-label">Modèle :</label>
              <input
                ref="inputRef"
                v-model="pattern"
                class="form-control pattern-input"
                type="text"
                placeholder="{Série} - {Numéro} - {Titre}"
              />
            </div>

            <div class="tokens-row">
              <button
                v-for="token in TOKENS"
                :key="token"
                class="btn btn-ghost btn-sm token-btn"
                @click="insertToken(token)"
                type="button"
              >{{ token }}</button>
            </div>

            <div class="preview-table-wrap">
              <table class="preview-table">
                <thead>
                  <tr>
                    <th class="col-current">Nom actuel</th>
                    <th class="col-next">Nouveau nom</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in preview"
                    :key="row.tome.id"
                    :class="{ 'row-unchanged': row.unchanged, 'row-conflict': row.conflict }"
                  >
                    <td class="cell-current">{{ row.current }}</td>
                    <td class="cell-next">
                      <span v-if="row.conflict" class="conflict-icon" title="Conflit : deux fichiers auraient le même nom">⚠</span>
                      <input
                        type="text"
                        class="next-input"
                        :class="{ 'next-input-conflict': row.conflict }"
                        :value="row.final"
                        @input="onInputChange(row.tome.id, $event.target.value)"
                        @blur="onInputBlur(row.tome.id, $event.target.value)"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="result" class="result-summary">
              <span v-if="result.ok" class="result-ok">✓ {{ result.ok }} renommé{{ result.ok !== 1 ? 's' : '' }}</span>
              <ul v-if="result.errors?.length" class="result-errors">
                <li v-for="(err, i) in result.errors" :key="i">{{ err }}</li>
              </ul>
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <div class="modal-footer-spacer" />
          <template v-if="result">
            <button @click="emit('done'); emit('close')" class="btn btn-primary btn-sm">Fermer</button>
          </template>
          <template v-else>
            <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
            <button @click="doRename" :disabled="saving || loadingMeta" class="btn btn-primary btn-sm">
              {{ saving ? 'Renommage…' : 'Renommer' }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--overlay-bg);
}

.modal-wrap {
  position: fixed;
  inset: 0;
  z-index: 201;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  pointer-events: none;
}

.modal-box {
  pointer-events: auto;
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 680px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.modal-header-info { flex: 1; min-width: 0; }

.modal-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}

.modal-footer-spacer { flex: 1; }

.loading-meta {
  font-size: 0.8125rem;
  color: var(--muted);
  text-align: center;
  padding: 24px 0;
}

.rules-section {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.rules-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: var(--light);
  border: none;
  cursor: pointer;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text);
  text-align: left;
}

.rules-toggle:hover { background: var(--border); }

.rules-toggle-arrow {
  font-size: 0.65rem;
  color: var(--muted);
  transition: transform 0.15s;
  display: inline-block;
}

.rules-toggle-arrow.open { transform: rotate(90deg); }

.rules-list {
  padding: 8px 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px solid var(--border);
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.rule-checkbox {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.rule-input {
  flex: 1;
  font-size: 0.78rem;
  padding: 4px 7px;
  min-width: 0;
}

.rule-arrow {
  flex-shrink: 0;
  color: var(--muted);
  font-size: 0.8rem;
}

.regex-badge {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-family: monospace;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--border);
  cursor: pointer;
  background: var(--light);
  color: var(--muted);
  line-height: 1.4;
}

.regex-badge.active {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}

.add-rule-btn {
  align-self: flex-start;
  margin-top: 2px;
  font-size: 0.78rem;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.form-label {
  font-size: 0.8125rem;
  color: var(--muted);
  white-space: nowrap;
  font-weight: 500;
}

.pattern-input { flex: 1; }

.tokens-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.token-btn {
  font-size: 0.75rem;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--light);
  cursor: pointer;
  color: var(--primary);
  font-family: monospace;
}

.token-btn:hover { background: var(--primary-light); }

.preview-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}

.preview-table th {
  padding: 6px 10px;
  text-align: left;
  background: var(--light);
  color: var(--muted);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.col-current { width: 45%; }
.col-next { width: 55%; }

.preview-table td {
  padding: 4px 10px;
  border-bottom: 1px solid var(--light);
  word-break: break-all;
}

.preview-table tr:last-child td { border-bottom: none; }

.cell-current { color: var(--muted); }

.cell-next {
  padding: 3px 10px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.row-unchanged td { color: var(--muted); opacity: 0.6; }

.next-input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 0.78rem;
  color: var(--text);
  padding: 2px 0;
  outline: none;
  font-family: inherit;
  border-bottom: 1px solid transparent;
}

.next-input:focus {
  border-bottom: 1px solid var(--primary);
  background: transparent;
}

.next-input-conflict {
  color: var(--danger);
}

.conflict-icon {
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--danger);
  white-space: nowrap;
}

.result-summary {
  font-size: 0.8125rem;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--light);
  border: 1px solid var(--border);
}

.result-ok { color: var(--success); font-weight: 600; }

.result-errors {
  margin: 6px 0 0 0;
  padding-left: 16px;
  color: var(--danger);
}

.result-errors li { margin-bottom: 2px; }
</style>
