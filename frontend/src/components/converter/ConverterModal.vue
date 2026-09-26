<script setup>
import { ref, computed, watch } from 'vue'
import ConversionProgress from './ConversionProgress.vue'
import { useNotificationStore } from '../../stores/notifications'
import client from '../../api/client'

// tomes: array of { id, filename, title, file_size, file_format }
const props = defineProps({
  tomes: { type: Array, required: true },
})
const emit = defineEmits(['close', 'done'])

const notif = useNotificationStore()
const preset = ref('Medium')
// Comparateur de qualité : HoverCard de shadcn-vue (survol ou focus clavier sur l'icône),
// rendu dans <body> et positionné par Reka UI — au-dessus de la modale, jamais hors écran.
const jobId = ref(null)
const starting = ref(false)

// Checked tome IDs — all checked by default
const checked = ref(new Set(props.tomes.map(t => t.id)))


function toggleTome(id) {
  if (checked.value.has(id)) { checked.value.delete(id) }
  else { checked.value.add(id) }
  checked.value = new Set(checked.value)
}
function toggleAll() {
  checked.value = checked.value.size === props.tomes.length
    ? new Set()
    : new Set(props.tomes.map(t => t.id))
}

// Destination folder
const destMode = ref('same')   // 'same' | 'custom'
const destPath = ref('')
const destPathError = ref('')
const destPathValid = ref(false)
const checkingPath = ref(false)

async function validatePath() {
  destPathError.value = ''
  destPathValid.value = false
  if (!destPath.value.trim()) return
  checkingPath.value = true
  try {
    await client.post('/api/convert/check-path', { path: destPath.value.trim() })
    destPathValid.value = true
  } catch (e) {
    destPathError.value = e.response?.data?.detail || 'Chemin invalide'
  } finally {
    checkingPath.value = false
  }
}

const PRESETS = ['Light', 'Medium', 'HQ', 'Original']
const PRESET_DESC = {
  'Light':    'max 1200px · ~60%',
  'Medium':   'max 1600px · ~75%',
  'HQ':       'max 2048px · ~85%',
  'Original': 'taille originale',
}

import imgLight    from '../../assets/images/quality-light.jpg'
import imgOriginal from '../../assets/images/quality-originale.jpg'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/shadcn/hover-card'
import AppDialog from '../ui/AppDialog.vue'

function formatSize(bytes) {
  if (!bytes) return '?'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

const selectedTomes = computed(() => props.tomes.filter(t => checked.value.has(t.id)))
const tomeLabels = computed(() => Object.fromEntries(props.tomes.map(t => [t.id, t.filename])))
const totalBefore = computed(() => selectedTomes.value.reduce((s, t) => s + (t.file_size || 0), 0))

// Real estimate from backend
const estimatedBytes = ref(null)
const estimating = ref(false)

async function fetchEstimate() {
  if (checked.value.size === 0) { estimatedBytes.value = null; return }
  estimating.value = true
  try {
    const { data } = await client.post('/api/convert/estimate', {
      tome_ids: [...checked.value],
      preset: preset.value,
    })
    estimatedBytes.value = data.estimated_bytes
  } catch {
    estimatedBytes.value = null
  } finally {
    estimating.value = false
  }
}

// Fetch estimate when preset or selection changes (debounced)
let estimateTimer = null
watch([preset, checked], () => {
  clearTimeout(estimateTimer)
  estimateTimer = setTimeout(fetchEstimate, 400)
}, { immediate: true })

const savings = computed(() => {
  if (!totalBefore.value || !estimatedBytes.value) return null
  const p = Math.round((1 - estimatedBytes.value / totalBefore.value) * 100)
  return p > 0 ? p : null
})

const canStart = computed(() => {
  if (checked.value.size === 0) return false
  if (destMode.value === 'custom' && !destPathValid.value) return false
  return true
})

async function start() {
  starting.value = true
  try {
    const { data } = await client.post('/api/convert', {
      tome_ids: [...checked.value],
      preset: preset.value,
      dest_path: destMode.value === 'custom' ? destPath.value.trim() : null,
    })
    jobId.value = data.job_id
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors du démarrage')
    starting.value = false
  }
}
</script>

<template>
  <AppDialog title="Convertir en CBZ" @close="$emit('close')">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">Convertir en CBZ</h2>
        <button @click="$emit('close')" class="btn btn-ghost btn-icon btn-sm">✕</button>
      </div>

      <!-- Config -->
      <div v-if="!jobId" class="modal-body">

        <!-- Tome list -->
        <div class="section">
          <div class="section-header">
            <span class="form-label" style="margin:0">Fichiers</span>
            <button class="btn btn-ghost btn-sm" @click="toggleAll">
              {{ checked.size === tomes.length ? 'Tout décocher' : 'Tout cocher' }}
            </button>
          </div>
          <div class="tome-list">
            <label
              v-for="t in tomes"
              :key="t.id"
              :class="['tome-row', { 'tome-row-checked': checked.has(t.id) }]"
            >
              <input type="checkbox" :checked="checked.has(t.id)" @change="toggleTome(t.id)" class="tome-checkbox" />
              <span class="tome-filename">{{ t.filename }}</span>
              <span class="tome-size">{{ formatSize(t.file_size) }}</span>
              <span :class="['fmt-badge', `fmt-${t.file_format}`]">{{ t.file_format.toUpperCase() }}</span>
            </label>
          </div>
        </div>

        <!-- Preset selector -->
        <div class="section">
          <div class="section-header">
            <span class="form-label" style="margin:0">Qualité</span>
            <HoverCard :open-delay="100" :close-delay="100">
              <HoverCardTrigger as-child>
                <span class="quality-info-icon" tabindex="0" aria-label="Comparer les qualités">i</span>
              </HoverCardTrigger>
              <HoverCardContent align="end" class="w-auto border-0 bg-transparent p-0 shadow-none">
                <div class="quality-popover">
                <p class="compare-hint">Exemple : <strong>Light</strong> vs <strong>Original</strong></p>
                <div class="compare-images">
                  <div class="compare-col">
                    <div class="compare-label compare-label-light">Light</div>
                    <img :src="imgLight" class="compare-img" alt="Light" />
                  </div>
                  <div class="compare-divider" />
                  <div class="compare-col">
                    <div class="compare-label compare-label-original">Original</div>
                    <img :src="imgOriginal" class="compare-img" alt="Original" />
                  </div>
                </div>
                </div>
              </HoverCardContent>
            </HoverCard>
          </div>
          <div class="preset-list">
            <label
              v-for="p in PRESETS"
              :key="p"
              :class="['preset-option', { 'preset-option-selected': preset === p }]"
            >
              <input type="radio" v-model="preset" :value="p" class="preset-radio" />
              <span class="preset-name">{{ p }}</span>
              <span class="preset-desc">{{ PRESET_DESC[p] }}</span>
            </label>
          </div>
        </div>

        <!-- Size estimate -->
        <div v-if="selectedTomes.length > 0 && totalBefore > 0" class="estimate">
          <div class="estimate-row">
            <span class="estimate-label">Taille actuelle</span>
            <span class="estimate-value">{{ formatSize(totalBefore) }}</span>
          </div>
          <div class="estimate-row">
            <span class="estimate-label">Taille estimée</span>
            <span v-if="estimating" class="estimate-value estimate-loading">Calcul…</span>
            <span v-else-if="estimatedBytes" class="estimate-value estimate-after">
              {{ formatSize(estimatedBytes) }}
              <span v-if="savings" class="estimate-savings">−{{ savings }}%</span>
            </span>
            <span v-else class="estimate-value" style="color:var(--muted)">—</span>
          </div>
        </div>

        <!-- Destination -->
        <div class="section">
          <span class="form-label">Dossier de destination</span>
          <div class="dest-options">
            <label :class="['dest-option', { 'dest-option-selected': destMode === 'same' }]">
              <input type="radio" v-model="destMode" value="same" class="preset-radio" />
              <div>
                <p class="preset-name">Même dossier</p>
                <p class="preset-desc">Fichier converti à côté de l'original</p>
              </div>
            </label>
            <label :class="['dest-option', { 'dest-option-selected': destMode === 'custom' }]">
              <input type="radio" v-model="destMode" value="custom" class="preset-radio" />
              <div>
                <p class="preset-name">Dossier personnalisé</p>
                <p class="preset-desc">Choisir un dossier de sortie</p>
              </div>
            </label>
          </div>

          <!-- Custom path input -->
          <div v-if="destMode === 'custom'" class="dest-path-wrap">
            <div class="dest-path-row">
              <input
                v-model="destPath"
                type="text"
                class="form-control dest-path-input"
                placeholder="/chemin/vers/dossier"
                @blur="validatePath"
                @keyup.enter="validatePath"
              />
              <button
                class="btn btn-secondary btn-sm"
                @click="validatePath"
                :disabled="checkingPath || !destPath.trim()"
              >{{ checkingPath ? '…' : 'Vérifier' }}</button>
            </div>
            <p v-if="destPathError" class="dest-path-msg dest-path-error">✕ {{ destPathError }}</p>
            <p v-else-if="destPathValid" class="dest-path-msg dest-path-ok">✓ Dossier valide</p>
            <p v-else class="dest-path-msg dest-path-hint">Entrez le chemin absolu du dossier sur le serveur, puis cliquez Vérifier.</p>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <span class="footer-count">{{ checked.size }} fichier{{ checked.size > 1 ? 's' : '' }} sélectionné{{ checked.size > 1 ? 's' : '' }}</span>
          <button @click="$emit('close')" class="btn btn-ghost btn-sm">Annuler</button>
          <button @click="start" :disabled="starting || !canStart" class="btn btn-primary btn-sm">
            {{ starting ? 'Démarrage…' : 'Convertir' }}
          </button>
        </div>
      </div>

      <!-- Progress -->
      <ConversionProgress v-else :job-id="jobId" :labels="tomeLabels" @done="emit('done'); emit('close')" />
    </div>
  </AppDialog>
</template>

<style scoped>
.modal {
  background: var(--surface-raised); border-radius: var(--radius-lg);
  width: 100%; max-width: 500px; max-height: 90vh;
  box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column; overflow: hidden;
}
.modal-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.modal-title { flex: 1; font-size: 1rem; font-weight: 600; }
.modal-body {
  padding: 16px 18px; display: flex; flex-direction: column; gap: 16px;
  overflow-y: auto;
}

.section { display: flex; flex-direction: column; gap: 8px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }

/* Tome list */
.tome-list {
  display: flex; flex-direction: column; gap: 3px;
  max-height: 180px; overflow-y: auto;
  border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 4px;
}
.tome-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px; border-radius: var(--radius-sm);
  cursor: pointer; transition: background 0.1s; font-size: 0.8125rem;
}
.tome-row:hover { background: var(--light); }
.tome-row-checked { background: var(--primary-light); }
.tome-checkbox { flex-shrink: 0; accent-color: var(--primary); }
.tome-filename {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tome-size { color: var(--muted); font-size: 0.72rem; flex-shrink: 0; }
.fmt-badge { font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; }
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }

/* Presets */
.preset-list { display: flex; gap: 6px; }
.preset-option {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 8px 6px; border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; transition: border-color 0.15s, background 0.15s; text-align: center;
}
.preset-option:hover { border-color: var(--border); background: var(--light); }
.preset-option-selected { border-color: var(--primary); background: var(--primary-light); box-shadow: 0 0 0 2px var(--primary-focus); }
.preset-radio { display: none; }
.preset-name { font-size: 0.8125rem; font-weight: 600; color: var(--text); }
.preset-desc { font-size: 0.7rem; color: var(--muted); }

/* Estimate */
.estimate {
  background: var(--light); border-radius: var(--radius-sm);
  padding: 10px 14px; display: flex; flex-direction: column; gap: 5px;
}
.estimate-row { display: flex; justify-content: space-between; font-size: 0.8125rem; }
.estimate-label { color: var(--muted); }
.estimate-value { font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 6px; }
.estimate-after   { color: var(--primary); }
.estimate-loading { color: var(--muted); font-style: italic; font-weight: 400; }
.estimate-savings {
  font-size: 0.72rem; font-weight: 700;
  background: var(--success-bg-light); color: var(--success); padding: 1px 6px; border-radius: 10px;
}

/* Destination */
.dest-options { display: flex; flex-direction: column; gap: 6px; }
.dest-option {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; transition: border-color 0.15s, background 0.15s;
}
.dest-option:hover { border-color: var(--border); background: var(--light); }
.dest-option-selected { border-color: var(--primary); background: var(--primary-light); box-shadow: 0 0 0 2px var(--primary-focus); }

.dest-path-wrap { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.dest-path-row { display: flex; gap: 8px; }
.dest-path-input { flex: 1; font-size: 0.8125rem; font-family: monospace; }
.dest-path-msg { font-size: 0.8rem; }
.dest-path-error { color: var(--danger); }
.dest-path-ok    { color: var(--success); }
.dest-path-hint  { color: var(--muted); }

/* Icône info + popover qualité */
.quality-info-wrap {
  position: relative; display: inline-flex; align-items: center;
}
.quality-info-icon {
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--primary); color: #fff;
  font-size: 0.7rem; font-weight: 700; font-style: italic;
  display: flex; align-items: center; justify-content: center;
  cursor: default; user-select: none; flex-shrink: 0;
}
.quality-popover {
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
  padding: 14px; width: 480px; max-width: calc(100vw - 16px);
}
.compare-hint { font-size: 0.78rem; color: var(--muted); margin-bottom: 10px; }
.compare-images {
  display: flex; align-items: flex-start;
  border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden;
}
.compare-col { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.compare-label {
  padding: 4px 8px; font-size: 0.7rem; font-weight: 700;
  text-align: center; text-transform: uppercase; letter-spacing: 0.05em;
}
.compare-label-light    { background: var(--warning-bg); color: var(--orange-bar); }
.compare-label-original { background: var(--success-bg); color: var(--success-text); }
.compare-img { width: 100%; height: auto; display: block; }
.compare-divider { width: 2px; background: var(--border); flex-shrink: 0; }

/* Footer */
.modal-footer {
  display: flex; align-items: center; gap: 8px;
  padding-top: 4px; flex-shrink: 0;
}
.footer-count { flex: 1; font-size: 0.8125rem; color: var(--muted); }
</style>
