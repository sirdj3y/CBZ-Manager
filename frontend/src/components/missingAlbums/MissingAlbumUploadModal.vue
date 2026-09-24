<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import SvgIcon from '../SvgIcon.vue'
import ConversionProgress from '../converter/ConversionProgress.vue'
import { importApi } from '../../api/import'
import { missingAlbumsApi } from '../../api/missingAlbums'
import { settingsApi } from '../../api/settings'
import client from '../../api/client'
import { useNotificationStore } from '../../stores/notifications'
import { applyRenamePattern } from '../../utils/renamePattern'
import { normalizeSearch } from '../../utils/text'

// album: { id, series_id, series_name, number, title, year }
const props = defineProps({
  album: { type: Object, required: true },
})
const emit = defineEmits(['close', 'uploaded'])

const notif = useNotificationStore()

const CONVERT_EXTS = new Set(['.cbr', '.pdf', '.cbz', '.zip'])
const PRESETS = ['Light', 'Medium', 'HQ', 'Original']
const PRESET_DESC = { Light: 'max 1200px', Medium: 'max 1600px', HQ: 'max 2048px', Original: 'Taille originale' }

const albumLabel = computed(() => `${props.album.series_name} T${props.album.number}`)

// Bedetheque titre souvent juste "Tome N" (mangas notamment) — redondant avec le numéro
// déjà affiché à côté, donc masqué. Même logique que displayTitle() sur la page Albums
// manquants, sinon la popup affiche par ex. « T89 · Tome 89 » qui ne veut rien dire de plus.
const realTitle = computed(() => {
  const t = (props.album.title || '').trim()
  if (!t) return ''
  if (normalizeSearch(t) === normalizeSearch(`Tome ${props.album.number}`)) return ''
  return t
})

// Même modèle de renommage que l'assistant d'import — récupéré une fois à l'ouverture.
const renamePattern = ref('')
settingsApi.get().then(({ data }) => { renamePattern.value = data.rename_pattern || '' }).catch(() => {})

const fileInput = ref(null)
const dragging = ref(false)
const file = ref(null)
const filename = ref('')
const filenameEdited = ref(false)
const duplicateWarning = ref(false)
const convertChecked = ref(false)
const convertPreset = ref('HQ')

const phase = ref('select') // select | uploading | converting
const uploadProgress = ref(0)
const jobId = ref(null)
const errorMsg = ref('')
const convertLabels = ref({})

function extOf(f) {
  const parts = f.name.split('.')
  return parts.length > 1 ? '.' + parts.pop().toLowerCase() : ''
}

function formatSize(bytes) {
  if (!bytes) return '0 Ko'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

function computeFilename(f) {
  const ext = extOf(f)
  const stem = f.name.slice(0, f.name.length - ext.length)
  const values = {
    stem, ext,
    series: props.album.series_name || '', number: props.album.number || '',
    title: realTitle.value, year: props.album.year || '',
    penciller: props.album.penciller || '', writer: props.album.writer || '',
    publisher: props.album.publisher || '',
  }
  return renamePattern.value ? applyRenamePattern(renamePattern.value, values) : f.name
}

function pickFile(f) {
  file.value = f
  convertChecked.value = CONVERT_EXTS.has(extOf(f))
  filenameEdited.value = false
  filename.value = computeFilename(f)
  checkDuplicate()
}

function onFilesSelected(e) {
  const f = e.target.files?.[0]
  if (f) pickFile(f)
}
function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer.files?.[0]
  if (f) pickFile(f)
}

let dupTimer = null
watch(filename, (val, old) => {
  if (val === old) return
  filenameEdited.value = true
  clearTimeout(dupTimer)
  dupTimer = setTimeout(checkDuplicate, 400)
})

async function checkDuplicate() {
  if (!filename.value.trim()) { duplicateWarning.value = false; return }
  try {
    const { data } = await importApi.checkFile(filename.value.trim(), props.album.series_id, null)
    duplicateWarning.value = !!data.duplicate
  } catch {
    duplicateWarning.value = false
  }
}

const showConvertOptions = computed(() => file.value && CONVERT_EXTS.has(extOf(file.value)))
const canSubmit = computed(() => phase.value === 'select' && !!file.value && !!filename.value.trim())

function onKey(e) { if (e.key === 'Escape' && phase.value !== 'converting') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

async function submit() {
  if (!canSubmit.value) return
  phase.value = 'uploading'
  uploadProgress.value = 0
  errorMsg.value = ''

  // realTitle (masque "Tome N") ne sert qu'à l'affichage/nom de fichier, pas au contenu
  // ComicInfo.xml — le vrai titre Bedetheque, même redondant avec le numéro, reste une
  // métadonnée légitime pour un lecteur externe.
  const metadata = {}
  const rawTitle = (props.album.title || '').trim()
  if (rawTitle) metadata.Title = rawTitle
  metadata.Series = props.album.series_name
  if (props.album.number) metadata.Number = props.album.number
  if (props.album.year) metadata.Year = props.album.year
  if (props.album.writer) metadata.Writer = props.album.writer
  if (props.album.penciller) metadata.Penciller = props.album.penciller
  if (props.album.publisher) metadata.Publisher = props.album.publisher
  if (props.album.bedetheque_url) metadata.Web = props.album.bedetheque_url

  try {
    const { data } = await importApi.uploadFile(
      file.value, filename.value.trim(), props.album.series_id, null, metadata, false,
      (evt) => { uploadProgress.value = evt.total ? Math.round((evt.loaded / evt.total) * 100) : 0 }
    )
    if (convertChecked.value && data.tome_id) {
      phase.value = 'converting'
      convertLabels.value = { [data.tome_id]: filename.value.trim() }
      const { data: convData } = await client.post('/api/convert', {
        tome_ids: [data.tome_id], preset: convertPreset.value, dest_path: null, delete_source: true,
      })
      jobId.value = convData.job_id
    } else {
      await finalize()
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || "Erreur pendant l'envoi"
    phase.value = 'select'
  }
}

async function onConvertDone() {
  await finalize()
}

async function finalize() {
  // Suppression directe et fiable de CET album manquant précis (pas de dépendance réseau,
  // ne peut pas échouer silencieusement) — auparavant la disparition de la carte reposait
  // uniquement sur la revérification Bedetheque ci-dessous, qui échoue sans bruit en cas de
  // souci réseau (site injoignable, ralenti...), laissant l'album affiché comme manquant
  // alors qu'il vient d'être ajouté.
  try { await missingAlbumsApi.fulfilled(props.album.id) } catch { /* la revérification ci-dessous prend le relais */ }
  // Best-effort : revérifie aussi la série côté Bedetheque (autres albums potentiellement
  // devenus disponibles, métadonnées rafraîchies) — un échec réseau ici n'invalide pas
  // l'import, qui a déjà réussi.
  try { await missingAlbumsApi.recheckSeries(props.album.series_id) } catch { /* best-effort */ }
  notif.success(`« ${albumLabel.value} » ajouté à la série`)
  emit('uploaded', props.album.id)
  emit('close')
}
</script>

<template>
  <div class="mau-backdrop" @click.self="phase !== 'converting' && $emit('close')">
    <div class="mau-modal">
      <div class="mau-header">
        <h2 class="mau-title">Ajouter — {{ albumLabel }}<span v-if="realTitle"> · {{ realTitle }}</span></h2>
        <button class="btn btn-ghost btn-icon btn-sm" @click="$emit('close')">✕</button>
      </div>

      <div v-if="phase === 'select'" class="mau-body">
        <div
          :class="['mau-drop', { dragging }]"
          @click="fileInput.click()"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input ref="fileInput" type="file" accept=".cbz,.cbr,.pdf,.zip,.rar" style="display:none" @change="onFilesSelected" />
          <SvgIcon :name="dragging ? 'upload' : 'folder-up'" class="mau-drop-icon" />
          <template v-if="!file">
            <p class="mau-drop-label">Cliquer ou glisser-déposer un fichier</p>
            <p class="mau-drop-hint">CBZ, CBR, PDF</p>
          </template>
          <template v-else>
            <p class="mau-drop-label">{{ file.name }}</p>
            <p class="mau-drop-hint">{{ formatSize(file.size) }} — cliquer pour changer</p>
          </template>
        </div>

        <div v-if="file" class="form-group">
          <label class="form-label">Nom du fichier final</label>
          <input v-model="filename" type="text" class="form-control" />
          <p v-if="duplicateWarning" class="mau-warn">⚠ Un fichier porte déjà ce nom dans cette série</p>
        </div>

        <div v-if="showConvertOptions" class="mau-convert">
          <label class="mau-convert-toggle">
            <input type="checkbox" v-model="convertChecked" />
            Convertir en CBZ
          </label>
          <div v-if="convertChecked" class="mau-presets">
            <label
              v-for="p in PRESETS"
              :key="p"
              :class="['mau-preset-option', { 'mau-preset-selected': convertPreset === p }]"
            >
              <input type="radio" v-model="convertPreset" :value="p" style="display:none" />
              <span class="mau-preset-name">{{ p }}</span>
              <span class="mau-preset-desc">{{ PRESET_DESC[p] }}</span>
            </label>
          </div>
        </div>

        <p v-if="errorMsg" class="mau-error">{{ errorMsg }}</p>

        <div class="mau-footer">
          <button class="btn btn-ghost btn-sm" @click="$emit('close')">Annuler</button>
          <button class="btn btn-primary btn-sm" :disabled="!canSubmit" @click="submit">Importer</button>
        </div>
      </div>

      <div v-else-if="phase === 'uploading'" class="mau-body">
        <p class="mau-progress-label">Envoi en cours… {{ uploadProgress }}%</p>
        <div class="mau-progress-track"><div class="mau-progress-fill" :style="{ width: uploadProgress + '%' }" /></div>
      </div>

      <ConversionProgress v-else-if="phase === 'converting' && jobId" :job-id="jobId" :labels="convertLabels" @done="onConvertDone" />
    </div>
  </div>
</template>

<style scoped>
.mau-backdrop {
  position: fixed; inset: 0; z-index: 500;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.mau-modal {
  background: var(--surface-raised); border-radius: var(--radius-lg);
  width: 100%; max-width: 460px; max-height: 90vh;
  box-shadow: var(--shadow-lg);
  display: flex; flex-direction: column; overflow: hidden;
}
.mau-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.mau-title { flex: 1; font-size: 0.95rem; font-weight: 600; line-height: 1.3; }
.mau-body {
  padding: 16px 18px; display: flex; flex-direction: column; gap: 14px;
  overflow-y: auto;
}

.mau-drop {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 22px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.mau-drop:hover { border-color: var(--primary); background: var(--primary-light); }
.mau-drop.dragging { border-color: var(--primary); background: var(--primary-light); border-style: solid; }
.mau-drop-icon { margin-bottom: 6px; color: var(--muted); font-size: 44px; }
.mau-drop-icon :deep(svg) { width: 1em; height: 1em; }
.mau-drop:hover .mau-drop-icon, .mau-drop.dragging .mau-drop-icon { color: var(--primary); }
.mau-drop-label { font-size: 0.85rem; font-weight: 500; color: var(--text); margin-bottom: 2px; overflow-wrap: anywhere; }
.mau-drop-hint { font-size: 0.75rem; color: var(--muted); }

.mau-warn { font-size: 0.78rem; color: var(--warning-text, var(--danger)); margin-top: 4px; }
.mau-error { font-size: 0.82rem; color: var(--danger); }

.mau-convert { display: flex; flex-direction: column; gap: 8px; }
.mau-convert-toggle { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--text); cursor: pointer; }
.mau-presets { display: flex; gap: 6px; flex-wrap: wrap; }
.mau-preset-option {
  display: flex; flex-direction: column; align-items: center;
  padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; transition: border-color 0.15s, background 0.15s; min-width: 72px;
}
.mau-preset-option:hover { border-color: var(--border); background: var(--light); }
.mau-preset-selected { border-color: var(--primary); background: var(--primary-light); box-shadow: 0 0 0 2px var(--primary-focus); }
.mau-preset-name { font-size: 0.78rem; font-weight: 600; color: var(--text); }
.mau-preset-desc { font-size: 0.68rem; color: var(--muted); }

.mau-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 2px; }

.mau-progress-label { text-align: center; font-size: 0.85rem; color: var(--muted); }
.mau-progress-track {
  height: 6px; background-color: var(--light); border: 1px solid var(--border);
  border-radius: 4px; overflow: hidden;
}
.mau-progress-fill { height: 100%; background-color: var(--primary); border-radius: 4px; transition: width 0.2s ease; }
</style>
