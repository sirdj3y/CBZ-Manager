<script setup>
import { ref, computed, watch } from 'vue'
import imgLight from '../assets/images/quality-light.jpg'
import imgOriginal from '../assets/images/quality-originale.jpg'
import { useRouter, useRoute } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import ScraperModal from '../components/metadata/ScraperModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import AutocompleteInput from '../components/ui/AutocompleteInput.vue'
import { importApi } from '../api/import'
import client from '../api/client'
import { useNotificationStore } from '../stores/notifications'
import { useLibraryStore } from '../stores/library'

const router = useRouter()
const route = useRoute()
const notif = useNotificationStore()
const libraryStore = useLibraryStore()

// ── Étape courante ──────────────────────────────────────────────────────────
const step = ref(1)

// ── Étape 1 — Sélection ─────────────────────────────────────────────────────
const fileInput = ref(null)
const rawFiles = ref([])
const existingSeries = ref([])
const destMode = ref('new')
const destSeriesId = ref(null)
const destSeriesName = ref('')

const ALLOWED = new Set(['.cbz', '.cbr', '.pdf', '.zip', '.rar'])
const dragging = ref(false)
// Sélection étape 1 : filename → boolean (true = à importer)
const rawFileSelection = ref({})

function filterFiles(files) {
  return Array.from(files)
    .filter(f => ALLOWED.has('.' + f.name.split('.').pop().toLowerCase()))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }))
}

function detectFolderName(files) {
  // webkitRelativePath = "DossierParent/fichier.cbz" — on prend le premier segment
  for (const f of files) {
    if (f.webkitRelativePath) {
      const folder = f.webkitRelativePath.split('/')[0]
      if (folder) return folder
    }
  }
  return null
}

function initSelection(files) {
  const sel = {}
  for (const f of files) sel[f.name] = true
  rawFileSelection.value = sel
}

function onFilesSelected(e) {
  const files = e.target.files
  rawFiles.value = filterFiles(files)
  initSelection(rawFiles.value)
  const folder = detectFolderName(files)
  if (folder && !destSeriesName.value) destSeriesName.value = folder
}

function onDrop(e) {
  dragging.value = false
  const files = e.dataTransfer?.files
  if (files?.length) {
    rawFiles.value = filterFiles(files)
    initSelection(rawFiles.value)
    const folder = detectFolderName(files)
    if (folder && !destSeriesName.value) destSeriesName.value = folder
  }
}

const allStep1Selected = computed(() => rawFiles.value.every(f => rawFileSelection.value[f.name]))
const selectedRawCount = computed(() => rawFiles.value.filter(f => rawFileSelection.value[f.name]).length)

function toggleAllStep1(checked) {
  const sel = {}
  for (const f of rawFiles.value) sel[f.name] = checked
  rawFileSelection.value = sel
}

async function goToStep2() {
  if (!rawFiles.value.length) return
  if (destMode.value === 'new' && !destSeriesName.value.trim()) return
  if (destMode.value === 'existing' && !destSeriesId.value) return

  // Filtrer uniquement les fichiers cochés en étape 1
  const selectedFiles = rawFiles.value.filter(f => rawFileSelection.value[f.name])
  if (!selectedFiles.length) return

  // Récupérer les infos parsées de chaque fichier
  const parsed = await Promise.all(selectedFiles.map(async f => {
    try {
      const { data } = await importApi.parseFilename(f.name)
      return data
    } catch { return {} }
  }))

  overrides.value = {}
  const mapped = selectedFiles.map((f, i) => ({
    file: f,
    originalName: f.name,
    finalName: f.name,
    size: f.size,
    duplicate: false,
    parsed: parsed[i],
  }))
  // Tri alphabétique par nom de fichier
  mapped.sort((a, b) => a.originalName.localeCompare(b.originalName, undefined, { numeric: true, sensitivity: 'base' }))
  items.value = mapped

  await checkDuplicates()
  step.value = 2

  // Charger les résolutions en arrière-plan (CBZ/CBR uniquement)
  imageSizes.value = {}
  for (const f of rawFiles.value) {
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    if (ext === '.cbz' || ext === '.cbr' || ext === '.zip') {
      importApi.getImageSize(f).then(({ data }) => {
        if (data.width) imageSizes.value = { ...imageSizes.value, [f.name]: data }
      }).catch(() => {})
    }
  }
}

// ── Étape 2 — Renommage ──────────────────────────────────────────────────────
const items = ref([])
// imageSizes[originalName] = { width, height } | null
const imageSizes = ref({})
const pattern = ref('{Série} - T{Numéro} - {Titre}')
const patternInputRef = ref(null)
const TOKENS = ['{Fichier}', '{Série}', '{Numéro}', '{Titre}', '{Année}', '{Dessinateur}', '{Scénariste}', '{Éditeur}']
const rules = ref([{ enabled: false, search: '', replace: '' }])
const showRules = ref(false)
const showMeta = ref(true)

function toggleBlock(block) {
  const next = { meta: false, rules: false, convert: false }
  // Si déjà ouvert → fermer, sinon ouvrir uniquement celui-ci
  if (block === 'meta')    next.meta    = !showMeta.value
  if (block === 'rules')   next.rules   = !showRules.value
  if (block === 'convert') next.convert = !showConvert.value
  showMeta.value    = next.meta
  showRules.value   = next.rules
  showConvert.value = next.convert
}
const overrides = ref({})

const hasDuplicates = computed(() => items.value.some(i => i.duplicate))

function formatNumber(n) {
  if (!n) return ''
  const extracted = String(n).replace(/\D.*/, '').trim()
  if (!extracted) return String(n)
  const num = parseInt(extracted, 10)
  if (isNaN(num)) return String(n)
  if (/^\d+$/.test(extracted) && num < 10 && extracted.length === 1) return String(num).padStart(2, '0')
  return extracted
}

function applyRules(s) {
  for (const rule of rules.value) {
    if (!rule.enabled || !rule.search) continue
    s = s.split(rule.search).join(rule.replace)
  }
  return s
}

function applyPattern(pat, item) {
  const ext = item.originalName.includes('.') ? '.' + item.originalName.split('.').pop() : ''
  const stem = item.originalName.includes('.') ? item.originalName.slice(0, item.originalName.lastIndexOf('.')) : item.originalName
  // Priorité : metaRows (édités) > parsed > fallback
  const m = metaRows.value[item.originalName] || {}
  const p = item.parsed || {}
  const seriesName = destMode.value === 'new' ? destSeriesName.value.trim()
    : existingSeries.value.find(s => s.id === destSeriesId.value)?.name || ''
  let r = pat
  r = r.replace(/{Fichier}/g, stem)
  r = r.replace(/{Série}/g, m.Series || p.series || seriesName || '')
  r = r.replace(/{Numéro}/g, formatNumber(m.Number || p.number || ''))
  r = r.replace(/{Titre}/g, m.Title || p.title || '')
  r = r.replace(/{Année}/g, m.Year || p.year || '')
  r = r.replace(/{Dessinateur}/g, m.Penciller || p.penciller || '')
  r = r.replace(/{Scénariste}/g, m.Writer || p.writer || '')
  r = r.replace(/{Éditeur}/g, m.Publisher || p.publisher || '')
  r = r.replace(/[<>:"/\\|?*]/g, '_')
  // Supprimer les séparateurs orphelins dus aux tokens vides : " - - " → " - ", " - " en début/fin
  r = r.replace(/(\s*-\s*){2,}/g, ' - ')
  r = r.replace(/^\s*-\s*/, '').replace(/\s*-\s*$/, '')
  r = r.replace(/\s{2,}/g, ' ').trim()
  r = r.replace(/_+/g, '_').replace(/^_+|_+$/g, '').trim()
  if (!r) r = stem
  r = applyRules(r)
  return r + ext
}

const preview = computed(() => {
  const rows = items.value.map(item => {
    const computed_ = applyPattern(pattern.value, item)
    const final = overrides.value[item.originalName] !== undefined ? overrides.value[item.originalName] : computed_
    return { item, computed: computed_, final }
  })
  const finalNames = rows.map(r => r.final)
  return rows.map((r, i) => {
    const unchanged = r.final === r.item.originalName && overrides.value[r.item.originalName] === undefined
    const conflict = finalNames.filter((n, j) => n === r.final && j !== i).length > 0
    return { ...r, unchanged, conflict }
  })
})

function applyPatternToAll() {
  overrides.value = {}
}

function onFinalNameInput(item, value) {
  const row = preview.value.find(r => r.item.originalName === item.originalName)
  if (row && value === row.computed) {
    const o = { ...overrides.value }
    delete o[item.originalName]
    overrides.value = o
  } else {
    overrides.value = { ...overrides.value, [item.originalName]: value }
  }
  item.finalName = value
}

function onFinalNameBlur(item, value) {
  if (!value.trim()) {
    const o = { ...overrides.value }
    delete o[item.originalName]
    overrides.value = o
    item.finalName = applyPattern(pattern.value, item)
  }
  onRenameBlur(item)
}

async function checkDuplicates() {
  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null
  // Sync finalName from preview before checking
  preview.value.forEach(r => { r.item.finalName = r.final })
  await Promise.all(items.value.map(async item => {
    try {
      const { data } = await importApi.checkFile(item.finalName, sid, sname)
      item.duplicate = data.duplicate
    } catch { item.duplicate = false }
  }))
}

async function onRenameBlur(item) {
  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null
  try {
    const { data } = await importApi.checkFile(item.finalName, sid, sname)
    item.duplicate = data.duplicate
  } catch { item.duplicate = false }
}

function insertToken(token) {
  if (!patternInputRef.value) { pattern.value += token; return }
  patternInputRef.value.focus()
  const start = patternInputRef.value.selectionStart ?? pattern.value.length
  const end = patternInputRef.value.selectionEnd ?? pattern.value.length
  pattern.value = pattern.value.slice(0, start) + token + pattern.value.slice(end)
  const pos = start + token.length
  patternInputRef.value.setSelectionRange(pos, pos)
}

function addRule() {
  rules.value.push({ enabled: true, search: '', replace: '' })
}

function removeRule(i) {
  rules.value.splice(i, 1)
}

// Navigation clavier verticale dans les tableaux (↑/↓)
function onTableKeydown(e) {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  const input = e.target
  const table = input.closest('table')
  if (!table) return
  const inputs = Array.from(table.querySelectorAll('input[type="text"]'))
  const idx = inputs.indexOf(input)
  if (idx === -1) return
  const cols = input.closest('tr')?.querySelectorAll('input[type="text"]').length || 1
  const next = e.key === 'ArrowDown' ? inputs[idx + cols] : inputs[idx - cols]
  if (next) { e.preventDefault(); next.focus(); next.select() }
}

// ── Étape 2 — Métadonnées ────────────────────────────────────────────────────
const META_FIELDS = ['Series', 'Number', 'Title', 'Writer', 'Penciller', 'Publisher', 'LanguageISO']
const META_LABELS = { Series: 'Série', Number: 'N°', Title: 'Titre', Writer: 'Scénariste', Penciller: 'Dessinateur', Publisher: 'Éditeur', LanguageISO: 'Langue' }
const BATCH_FIELDS = ['Series', 'Writer', 'Penciller', 'Publisher', 'LanguageISO']
const batchRow = ref({ Series: '', Writer: '', Penciller: '', Publisher: '', LanguageISO: '' })
const batchOnlyEmpty = ref(true)
// Valeurs originales avant tout remplissage par lot (pour distinguer "vide d'origine" de "rempli par le lot")
const metaOriginal = ref({})

// metaRows[originalName][field] = valeur saisie
const metaRows = ref({})

watch(items, (newItems) => {
  const next = {}
  const seriesName = destMode.value === 'new'
    ? destSeriesName.value.trim()
    : existingSeries.value.find(s => s.id === destSeriesId.value)?.name || ''
  for (const item of newItems) {
    const p = item.parsed || {}
    next[item.originalName] = {
      Series: p.series || seriesName,
      Number: p.number || '',
      Title: p.title || '',
      Writer: p.writer || '',
      Penciller: p.penciller || '',
      Publisher: p.publisher || '',
      LanguageISO: p.languageiso || 'fr',
    }
  }
  metaRows.value = next
  // Snapshot des valeurs originales pour le filtre "seulement si vide"
  metaOriginal.value = JSON.parse(JSON.stringify(next))
}, { immediate: true })

function applyBatch() {
  const next = { ...metaRows.value }
  for (const item of items.value) {
    const row = next[item.originalName]
    if (!row) continue
    const orig = metaOriginal.value[item.originalName] || {}
    let changed = false
    for (const f of BATCH_FIELDS) {
      if (!batchRow.value[f]) continue
      // "Seulement si vide" : on regarde la valeur ORIGINALE (avant lot), pas la valeur courante
      if (batchOnlyEmpty.value && orig[f]) continue
      row[f] = batchRow.value[f]
      changed = true
    }
    if (changed) next[item.originalName] = { ...row }
  }
  metaRows.value = next
}

// Watcher réactif : dès qu'on tape dans le lot OU qu'on change "seulement si vide"
watch(batchRow, applyBatch, { deep: true })
watch(batchOnlyEmpty, applyBatch)

// Quand les métadonnées changent, recalculer l'aperçu du renommage
watch([pattern, rules, metaRows], applyPatternToAll, { deep: true })

// Scraper par fichier
const scraperTarget = ref(null) // { originalName, series, number }

function openScraper(item) {
  const row = metaRows.value[item.originalName] || {}
  scraperTarget.value = {
    originalName: item.originalName,
    series: row.Series || '',
    number: row.Number || '',
  }
}

function applyScraperResult(result) {
  if (!scraperTarget.value) return
  const row = metaRows.value[scraperTarget.value.originalName]
  if (!row) return
  if (result.title)            row.Title     = result.title
  if (result.authors?.length)  row.Writer    = result.authors.join(', ')
  if (result.publisher)        row.Publisher = result.publisher
  if (result.year)             row.Year      = String(result.year)
  scraperTarget.value = null
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' Ko'
  return (bytes / 1024 / 1024).toFixed(1) + ' Mo'
}

// ── Étape 2 — Conversion ─────────────────────────────────────────────────────
const CONVERT_EXTS = new Set(['.cbr', '.pdf', '.cbz', '.zip'])
const PRESETS = ['Light', 'Medium', 'HQ', 'Original']
const PRESET_DESC = { 'Light': 'max 1200px', 'Medium': 'max 1600px', 'HQ': 'max 2048px', 'Original': 'Taille originale' }
const PRESET_QUALITY = { 'Light': 60, 'Medium': 75, 'HQ': 85, 'Original': 95 }

// Popover comparateur qualité
const qualityInfoRef = ref(null)
const showQualityCompare = ref(false)
const popoverStyle = ref({})

function onInfoEnter() {
  if (qualityInfoRef.value) {
    const rect = qualityInfoRef.value.getBoundingClientRect()
    popoverStyle.value = {
      position: 'fixed',
      top: (rect.bottom + 8) + 'px',
      left: Math.min(rect.left, window.innerWidth - 420) + 'px',
    }
  }
  showQualityCompare.value = true
}

function onInfoLeave() {
  showQualityCompare.value = false
}

const showConvert = ref(false)
const convertPreset = ref(null) // null = aucune qualité sélectionnée par défaut
// convertChecked[originalName] = true/false
const convertChecked = ref({})

// Fichiers éligibles à la conversion (CBR ou PDF)
const convertibleItems = computed(() =>
  items.value.filter(i => CONVERT_EXTS.has('.' + i.originalName.split('.').pop().toLowerCase()))
)


// Initialiser convertChecked quand les items changent, et ouvrir le bloc si des fichiers convertibles
watch(items, (newItems) => {
  const next = {}
  convertChecked.value = next
}, { immediate: true })

const convertCount = computed(() => Object.values(convertChecked.value).filter(Boolean).length)

const showMetaWarnModal = ref(false)

function handleImportClick() {
  if (itemsMetaLost.value.length) {
    showMetaWarnModal.value = true
  } else {
    startImport()
  }
}

// Fichiers non-CBZ avec métadonnées renseignées mais sans conversion activée
const META_WRITE_EXTS = new Set(['.cbz', '.zip'])
const itemsMetaLost = computed(() => {
  return items.value.filter(item => {
    const ext = '.' + item.originalName.split('.').pop().toLowerCase()
    if (META_WRITE_EXTS.has(ext)) return false // CBZ : métadonnées écrites, pas de souci
    const hasMeta = Object.values(metaRows.value[item.originalName] || {}).some(v => v && String(v).trim())
    const willConvert = convertChecked.value[item.originalName] && convertPreset.value
    return hasMeta && !willConvert
  })
})

// Quand on sélectionne un preset, cocher automatiquement tous les fichiers
watch(convertPreset, (val) => {
  if (!val) return
  const next = {}
  for (const item of convertibleItems.value) next[item.originalName] = true
  convertChecked.value = next
})

// Quand on coche un fichier sans preset sélectionné, sélectionner "Original"
watch(convertChecked, (val) => {
  if (!convertPreset.value && Object.values(val).some(Boolean)) {
    convertPreset.value = 'Original'
  }
}, { deep: true })

function estimateSize(bytes, preset) {
  const quality = PRESET_QUALITY[preset] ?? 95
  return Math.round(bytes * quality / 95)
}

// ── Étape 3 — Upload ─────────────────────────────────────────────────────────
const uploadTotal = computed(() => items.value.length)
const uploadDone = ref(0)
const uploading = ref(false)
const importedSeriesId = ref(null)
const allDoneFlag = ref(false)
const cancelRequested = ref(false)
const activeJobIds = ref([])

// Tableau unifié : une entrée par fichier importé
// { name, uploadStatus: 'pending'|'ok'|'error', uploadError, convertStatus: null|'pending'|'running'|'done'|'error', convertProgress, convertPagesNow, convertPagesTotal }
const fileStatuses = ref([])

const uploadErrors = computed(() => fileStatuses.value.filter(f => f.uploadStatus === 'error'))
const allDone = computed(() => allDoneFlag.value)

async function startImport() {
  uploading.value = true
  uploadDone.value = 0
  allDoneFlag.value = false
  cancelRequested.value = false
  activeJobIds.value = []
  step.value = 3

  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null

  preview.value.forEach(r => { r.item.finalName = r.final })

  const willConvert = (item) => {
    const ext = '.' + item.originalName.split('.').pop().toLowerCase()
    return CONVERT_EXTS.has(ext) && convertChecked.value[item.originalName] && convertPreset.value
  }

  fileStatuses.value = items.value.map(item => ({
    name: item.finalName,
    uploadStatus: 'pending',
    uploadError: null,
    convertStatus: willConvert(item) ? 'pending' : null,
    convertProgress: 0,
    convertPagesNow: 0,
    convertPagesTotal: 0,
    destPath: null,
    cancelled: false,
  }))

  // Traitement séquentiel : upload → conversion → fichier suivant
  for (let i = 0; i < items.value.length; i++) {
    if (cancelRequested.value) {
      // Marquer les fichiers restants comme annulés
      for (let j = i; j < items.value.length; j++) {
        if (fileStatuses.value[j].uploadStatus === 'pending') {
          fileStatuses.value[j].uploadStatus = 'error'
          fileStatuses.value[j].uploadError = 'Annulé'
          fileStatuses.value[j].convertStatus = null
          fileStatuses.value[j].cancelled = true
        }
      }
      break
    }
    const item = items.value[i]

    // Upload
    fileStatuses.value[i].uploadStatus = 'running'
    let destPath = null
    try {
      const meta = metaRows.value[item.originalName] || {}
      const { data } = await importApi.uploadFile(item.file, item.finalName, sid, sname, meta)
      fileStatuses.value[i].uploadStatus = 'ok'
      fileStatuses.value[i].destPath = data.path
      destPath = data.path
    } catch (e) {
      fileStatuses.value[i].uploadStatus = 'error'
      fileStatuses.value[i].uploadError = e.response?.data?.detail || e.message || 'Erreur'
      fileStatuses.value[i].convertStatus = null
      uploadDone.value++
      continue
    }
    uploadDone.value++

    // Conversion immédiate si nécessaire
    if (willConvert(item) && destPath) {
      await convertOne(i, destPath)
    }
  }

  // Nettoyage si annulation : supprimer les fichiers uploadés
  if (cancelRequested.value) {
    const uploadedPaths = fileStatuses.value
      .filter(f => f.destPath)
      .map(f => f.destPath)
    if (uploadedPaths.length) {
      const isNewSeries = destMode.value === 'new'
      try {
        await client.post('/api/import/cancel-cleanup', {
          paths: uploadedPaths,
          is_new_series: isNewSeries,
          new_series_name: isNewSeries ? destSeriesName.value.trim() : null,
        })
      } catch { /* ignoré */ }
    }
    allDoneFlag.value = true
    return
  }

  // Scan final
  await libraryStore.triggerScan()
  await waitForScan()

  // Trouver l'ID de la série importée
  const seriesName = sname || existingSeries.value.find(s => s.id === sid)?.name
  if (seriesName) {
    const { data } = await importApi.getSeries()
    const found = data.find(s => s.name === seriesName)
    if (found) importedSeriesId.value = found.id
  } else if (sid) {
    importedSeriesId.value = sid
  }

  allDoneFlag.value = true
  const okCount = fileStatuses.value.filter(f => f.uploadStatus === 'ok').length
  notif.success(`Import terminé — ${okCount} fichier(s) importé(s)`)
}

async function convertOne(idx, destPath) {
  // Déclencher un scan pour indexer le fichier uploadé
  await libraryStore.triggerScan()
  await waitForScan()

  // Lookup avec retry au cas où le scan serait encore en cours
  let tomeId = null
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const { data } = await importApi.lookupTomes([destPath])
      tomeId = data[destPath]
    } catch { break }
    if (tomeId) break
    await new Promise(r => setTimeout(r, 800))
  }
  if (!tomeId) { fileStatuses.value[idx].convertStatus = 'error'; return }

  // Lancer la conversion
  let jobId = null
  try {
    const { data } = await client.post('/api/convert', {
      tome_ids: [tomeId], preset: convertPreset.value, dest_path: null, delete_source: true
    })
    jobId = data.job_id
    activeJobIds.value.push(jobId)
    fileStatuses.value[idx].convertStatus = 'running'
    fileStatuses.value[idx].convertProgress = 0
  } catch { fileStatuses.value[idx].convertStatus = 'error'; return }

  // Polling jusqu'à done/error
  while (true) {
    if (cancelRequested.value) {
      fileStatuses.value[idx].convertStatus = 'error'
      fileStatuses.value[idx].cancelled = true
      break
    }
    await new Promise(r => setTimeout(r, 600))
    try {
      const { data } = await client.get(`/api/convert/${jobId}`)
      fileStatuses.value[idx].convertPagesNow = data.progress
      fileStatuses.value[idx].convertPagesTotal = data.total
      fileStatuses.value[idx].convertProgress = data.total > 0 ? Math.round(data.progress / data.total * 100) : 0
      if (data.status === 'done' || data.status === 'error') {
        fileStatuses.value[idx].convertStatus = data.status
        if (data.status === 'error' && cancelRequested.value) {
          fileStatuses.value[idx].cancelled = true
        }
        break
      }
    } catch { fileStatuses.value[idx].convertStatus = 'error'; break }
  }
  activeJobIds.value = activeJobIds.value.filter(id => id !== jobId)
}

async function cancelAll() {
  cancelRequested.value = true
  // Marquer les fichiers en cours comme annulés (pour l'affichage)
  for (const f of fileStatuses.value) {
    if (f.uploadStatus === 'running' || f.uploadStatus === 'pending') f.cancelled = true
    if (f.convertStatus === 'running' || f.convertStatus === 'pending') f.cancelled = true
  }
  // Annuler les conversions actives
  for (const jobId of activeJobIds.value) {
    try { await client.delete(`/api/convert/${jobId}`) } catch { /* ignoré */ }
  }
  // Le cleanup des fichiers est fait dans startImport() après la boucle
}

async function waitForScan() {
  // Attendre d'abord que le scan démarre (statut != idle/done initial)
  await new Promise(r => setTimeout(r, 800))
  // Attendre max 30s que le scan se termine
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 500))
    if (libraryStore.scanProgress.status === 'done' || libraryStore.scanProgress.status === 'error') break
  }
  // Petit délai pour s'assurer que la BDD est bien commitée
  await new Promise(r => setTimeout(r, 500))
  await libraryStore.fetchSeries()
}


function goToSeries() {
  if (importedSeriesId.value) {
    router.push(`/series/${importedSeriesId.value}`)
  } else {
    router.push('/series')
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
importApi.getSeries().then(({ data }) => { existingSeries.value = data })
libraryStore.fetchAuthors()

const AUTOCOMPLETE_FIELDS = new Set(['Writer', 'Penciller', 'Publisher'])
const authorPool = computed(() => {
  const all = new Set([...libraryStore.authorNames.writers, ...libraryStore.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})
function fieldSuggestions(f) {
  if (f === 'Writer' || f === 'Penciller') return authorPool.value
  if (f === 'Publisher') return libraryStore.authorNames.publishers
  return []
}

// Reset à l'étape 1 si on navigue vers /import depuis une autre étape
watch(() => route.path, (path) => {
  if (path === '/import' && step.value > 1) {
    step.value = 1
    rawFiles.value = []
    rawFileSelection.value = {}
    items.value = []
    fileStatuses.value = []
    destMode.value = 'new'
    destSeriesName.value = ''
    destSeriesId.value = null
    uploading.value = false
    allDoneFlag.value = false
    cancelRequested.value = false
    activeJobIds.value = []
    importedSeriesId.value = null
  }
})
</script>

<template>
  <AppLayout>
    <main class="import-main">
      <!-- Header -->
      <div class="import-header">
        <h1 class="import-title">Importer une série</h1>
        <!-- Steps indicator -->
        <div class="steps">
          <div v-for="n in 3" :key="n" :class="['step', { active: step === n, done: step > n }]">
            <span class="step-num">{{ step > n ? '✓' : n }}</span>
            <span class="step-label">{{ ['Sélection', 'Options', 'Import'][n-1] }}</span>
          </div>
          <div class="step-line" />
        </div>
      </div>

      <!-- ── Étape 1 ── -->
      <div v-if="step === 1" class="card step-card">
        <div class="card-body">
          <h2 class="section-title">1. Choisir les fichiers</h2>

          <div
            :class="['file-drop-zone', { dragging }]"
            @click="fileInput.click()"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="onDrop"
          >
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".cbz,.cbr,.pdf,.zip,.rar"
              webkitdirectory
              style="display:none"
              @change="onFilesSelected"
            />
            <SvgIcon :name="dragging ? 'upload' : 'folder-open'" class="drop-icon" />
            <p class="drop-label">{{ dragging ? 'Déposer les fichiers ici' : 'Cliquer ou glisser-déposer des fichiers' }}</p>
            <p class="drop-hint">Formats acceptés : CBZ, CBR, PDF — dossier ou fichiers individuels</p>
          </div>

          <div v-if="rawFiles.length" class="files-preview">
            <div class="files-count-row">
              <label class="files-select-all">
                <input type="checkbox" :checked="allStep1Selected" @change="e => toggleAllStep1(e.target.checked)" />
                <strong>{{ selectedRawCount }}/{{ rawFiles.length }}</strong> fichier(s) sélectionné(s)
              </label>
            </div>
            <ul class="files-list">
              <li v-for="f in rawFiles" :key="f.name" class="files-item">
                <label class="files-item-label">
                  <input type="checkbox" v-model="rawFileSelection[f.name]" />
                  <span class="files-name" :class="{ 'files-name-unchecked': !rawFileSelection[f.name] }">{{ f.name }}</span>
                </label>
                <span class="files-size">{{ formatSize(f.size) }}</span>
              </li>
            </ul>
          </div>

          <h2 class="section-title" style="margin-top: 24px">2. Choisir la destination</h2>

          <div class="dest-tabs">
            <button :class="['dest-tab', { active: destMode === 'new' }]" @click="destMode = 'new'">Nouvelle série</button>
            <button :class="['dest-tab', { active: destMode === 'existing' }]" @click="destMode = 'existing'">Série existante</button>
          </div>

          <div v-if="destMode === 'new'" class="field">
            <label class="form-label">Nom de la nouvelle série</label>
            <input v-model="destSeriesName" type="text" class="form-control" placeholder="ex: Astérix" />
          </div>

          <div v-if="destMode === 'existing'" class="field">
            <label class="form-label">Série existante</label>
            <select v-model="destSeriesId" class="form-control">
              <option :value="null">— Choisir une série —</option>
              <option v-for="s in existingSeries" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>

          <div class="step-actions">
            <button @click="router.push('/series')" class="btn btn-ghost btn-sm">Annuler</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!selectedRawCount || (destMode === 'new' && !destSeriesName.trim()) || (destMode === 'existing' && !destSeriesId)"
              @click="goToStep2"
            >Suivant →</button>
          </div>
        </div>
      </div>

      <!-- ── Étape 2 ── -->
      <div v-if="step === 2" class="card step-card">
        <div class="card-body">

          <!-- ① Bloc métadonnées -->
          <div class="collapsible-block">
            <button class="collapsible-toggle" type="button" @click="toggleBlock('meta')">
              <span class="toggle-arrow" :class="{ open: showMeta }">▶</span>
              Métadonnées <span class="collapsible-hint">(optionnel — écrit dans le CBZ)</span>
            </button>
            <div v-if="showMeta" class="collapsible-body">

              <!-- Édition par lot -->
              <div class="batch-row">
                <span class="batch-label">Par lot :</span>
                <template v-for="f in BATCH_FIELDS" :key="f">
                  <AutocompleteInput
                    v-if="AUTOCOMPLETE_FIELDS.has(f)"
                    v-model="batchRow[f]"
                    :suggestions="fieldSuggestions(f)"
                    :placeholder="META_LABELS[f]"
                    class="batch-input"
                  />
                  <input v-else type="text" class="form-control batch-input" :placeholder="META_LABELS[f]" v-model="batchRow[f]" />
                </template>
                <label class="batch-only-empty">
                  <input type="checkbox" v-model="batchOnlyEmpty" />
                  Seulement si vide
                </label>
              </div>

              <!-- Tableau métadonnées par fichier -->
              <div class="inner-table-wrap">
                <table class="inner-table meta-table">
                  <thead>
                    <tr>
                      <th class="col-meta-file">Fichier</th>
                      <th v-for="f in META_FIELDS" :key="f" :class="`col-meta-${f.toLowerCase()}`">{{ META_LABELS[f] }}</th>
                      <th class="col-meta-scrape"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in items" :key="item.originalName">
                      <td class="td-meta-file" :title="item.originalName">{{ item.originalName }}</td>
                      <td v-for="f in META_FIELDS" :key="f" class="td-meta">
                        <template v-if="metaRows[item.originalName]">
                          <AutocompleteInput
                            v-if="AUTOCOMPLETE_FIELDS.has(f)"
                            v-model="metaRows[item.originalName][f]"
                            :suggestions="fieldSuggestions(f)"
                            class="meta-input"
                          />
                          <input
                            v-else
                            type="text"
                            class="meta-input"
                            v-model="metaRows[item.originalName][f]"
                            @keydown="onTableKeydown"
                          />
                        </template>
                      </td>
                      <td class="td-meta-scrape">
                        <button class="scrape-btn" type="button" title="Rechercher en ligne" @click="openScraper(item)">🔍</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ② Bloc renommage -->
          <div class="collapsible-block">
            <button class="collapsible-toggle" type="button" @click="toggleBlock('rules')">
              <span class="toggle-arrow" :class="{ open: showRules }">▶</span>
              Renommer les fichiers <span class="collapsible-hint">(optionnel)</span>
            </button>
            <div v-if="showRules" class="collapsible-body">
              <div class="field-row">
                <label class="form-label">Modèle :</label>
                <input
                  ref="patternInputRef"
                  v-model="pattern"
                  type="text"
                  class="form-control pattern-input"
                  placeholder="{Série} - {Numéro} - {Titre}"
                />
              </div>
              <div class="tokens-row">
                <button v-for="t in TOKENS" :key="t" class="token-btn" type="button" @click="insertToken(t)">{{ t }}</button>
              </div>
              <div class="sub-section">
                <p class="sub-section-label">Rechercher / Remplacer</p>
                <div v-for="(rule, i) in rules" :key="i" class="rule-row">
                  <input type="checkbox" v-model="rule.enabled" class="rule-checkbox" />
                  <input type="text" v-model="rule.search" class="form-control rule-input" placeholder="Rechercher" />
                  <span class="rule-arrow">→</span>
                  <input type="text" v-model="rule.replace" class="form-control rule-input" placeholder="vide = supprimer" />
                  <button type="button" class="btn btn-ghost btn-icon btn-sm" @click="removeRule(i)">🗑</button>
                </div>
                <button type="button" class="btn btn-ghost btn-sm add-rule-btn" @click="addRule">+ Ajouter une règle</button>
              </div>
              <div v-if="hasDuplicates" class="alert-warning">
                ⚠ Certains fichiers existent déjà dans la destination. Ils seront écrasés.
              </div>
              <div class="inner-table-wrap">
                <table class="inner-table">
                  <thead>
                    <tr>
                      <th class="col-original">Nom actuel</th>
                      <th class="col-rename">Nouveau nom</th>
                      <th class="col-size">Taille</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="row in preview"
                      :key="row.item.originalName"
                      :class="{ 'row-unchanged': row.unchanged, 'row-duplicate': row.item.duplicate }"
                    >
                      <td class="td-original" :title="row.item.originalName">{{ row.item.originalName }}</td>
                      <td class="td-final">
                        <span v-if="row.conflict" class="conflict-icon" title="Conflit : deux fichiers auraient le même nom">⚠</span>
                        <input
                          type="text"
                          class="rename-input"
                          :class="{ 'rename-input-conflict': row.conflict }"
                          :value="row.final"
                          @input="onFinalNameInput(row.item, $event.target.value)"
                          @blur="onFinalNameBlur(row.item, $event.target.value)"
                          @keydown="onTableKeydown"
                        />
                        <span v-if="row.item.duplicate" class="badge-dup">doublon</span>
                      </td>
                      <td class="td-size">{{ formatSize(row.item.size) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ③ Bloc conversion -->
          <div class="collapsible-block">
            <button class="collapsible-toggle" type="button" @click="toggleBlock('convert')">
              <span class="toggle-arrow" :class="{ open: showConvert }">▶</span>
              Convertir / Recompresser en CBZ <span class="collapsible-hint">(optionnel)</span>
            </button>
            <div v-if="showConvert" class="collapsible-body">
              <!-- Indicateur si aucune qualité / aucun fichier coché -->
              <div v-if="!convertPreset || convertCount === 0" class="convert-no-convert">
                ✓ Les fichiers seront importés sans modification
              </div>
              <!-- Preset qualité -->
              <div class="convert-presets">
                <span class="form-label">Qualité :</span>
                <span class="quality-info-wrap" ref="qualityInfoRef" @mouseenter="onInfoEnter" @mouseleave="onInfoLeave">
                  <SvgIcon name="info" class="quality-info-icon" />
                  <div v-if="showQualityCompare" class="quality-popover" :style="popoverStyle">
                    <p class="quality-popover-title">Comparaison de qualité</p>
                    <div class="quality-popover-images">
                      <div class="quality-popover-img-wrap">
                        <img :src="imgLight" alt="Light" />
                        <span>Light</span>
                      </div>
                      <div class="quality-popover-img-wrap">
                        <img :src="imgOriginal" alt="Original" />
                        <span>Original</span>
                      </div>
                    </div>
                  </div>
                </span>
                <label
                  v-for="p in PRESETS"
                  :key="p"
                  :class="['convert-preset-option', { 'convert-preset-selected': convertPreset === p }]"
                >
                  <input type="radio" v-model="convertPreset" :value="p" style="display:none" />
                  <span class="convert-preset-name">{{ p }}</span>
                  <span class="convert-preset-desc">{{ PRESET_DESC[p] }}</span>
                </label>
              </div>
              <!-- Liste des fichiers -->
              <div class="inner-table-wrap">
                <table class="inner-table">
                  <thead>
                    <tr>
                      <th style="width:32px">
                        <input
                          type="checkbox"
                          :checked="convertibleItems.length > 0 && convertibleItems.every(i => convertChecked[i.originalName])"
                          @change="e => { const v = e.target.checked; convertibleItems.forEach(i => convertChecked[i.originalName] = v) }"
                        />
                      </th>
                      <th>Fichier</th>
                      <th style="width:55px">Format</th>
                      <th style="width:90px">Résolution</th>
                      <th class="col-size">Taille actuelle</th>
                      <th class="col-size">Taille estimée</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in convertibleItems" :key="item.originalName">
                      <td><input type="checkbox" v-model="convertChecked[item.originalName]" /></td>
                      <td>{{ item.originalName }}</td>
                      <td><span :class="['fmt-badge', `fmt-${item.originalName.split('.').pop().toLowerCase()}`]">{{ item.originalName.split('.').pop().toUpperCase() }}</span></td>
                      <td class="td-size">
                        <span v-if="imageSizes[item.originalName]">{{ imageSizes[item.originalName].width }}×{{ imageSizes[item.originalName].height }}</span>
                        <span v-else class="td-muted">—</span>
                      </td>
                      <td class="td-size">{{ formatSize(item.size) }}</td>
                      <td class="td-size">
                        <template v-if="convertChecked[item.originalName] && convertPreset">
                          <span :class="estimateSize(item.size, convertPreset) < item.size ? 'estimate-smaller' : 'estimate-same'">
                            {{ formatSize(estimateSize(item.size, convertPreset)) }}
                          </span>
                        </template>
                        <span v-else class="td-no-convert">—&nbsp;non modifié</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>


          <div class="step-actions">
            <button @click="step = 1" class="btn btn-ghost btn-sm">← Retour</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!items.length"
              @click="handleImportClick"
            >Importer {{ items.length }} fichier(s)</button>
          </div>
        </div>
      </div>

      <!-- ScraperModal (teleport géré par le composant) -->
      <ScraperModal
        v-if="scraperTarget"
        :series="scraperTarget.series"
        :number="scraperTarget.number"
        @select="applyScraperResult"
        @close="scraperTarget = null"
      />

      <!-- ── Étape 3 ── -->
      <div v-if="step === 3" class="card step-card">
        <div class="card-body">
          <h2 class="section-title">{{ allDone ? 'Import terminé' : 'Import en cours…' }}</h2>

          <!-- Liste des fichiers -->
          <div class="import-file-list" style="margin-bottom: 16px">
            <div v-for="f in fileStatuses" :key="f.name" class="import-file-row">
              <!-- Ligne principale : nom + statut upload -->
              <div class="import-file-main">
                <span class="import-file-name" :title="f.name">{{ f.name }}</span>
                <div class="import-file-statuses">
                  <span v-if="f.uploadStatus === 'pending'" class="status-pending">En attente</span>
                  <span v-else-if="f.uploadStatus === 'running'" class="status-running">↑ Upload…</span>
                  <span v-else-if="f.uploadStatus === 'error'" class="status-error" :title="f.uploadError">{{ f.cancelled ? 'Annulé' : '✕ ' + f.uploadError }}</span>
                  <template v-else-if="f.uploadStatus === 'ok'">
                    <template v-if="f.convertStatus === null">
                      <span class="status-done">✓ Terminé</span>
                    </template>
                    <template v-else-if="f.convertStatus === 'pending'">
                      <span class="status-pending">Conversion en attente</span>
                    </template>
                    <template v-else-if="f.convertStatus === 'running'">
                      <span class="status-running">
                        Conversion
                        <span v-if="f.convertPagesTotal > 0" class="convert-pages">{{ f.convertPagesNow }}/{{ f.convertPagesTotal }}</span>
                      </span>
                    </template>
                    <template v-else-if="f.convertStatus === 'done'">
                      <span class="status-done">✓ Terminé</span>
                    </template>
                    <template v-else>
                      <span class="status-error">{{ f.cancelled ? 'Annulé' : '✕ Erreur conversion' }}</span>
                    </template>
                  </template>
                </div>
              </div>
              <!-- Barre de progression uniquement pour la conversion -->
              <div v-if="f.convertStatus !== null" class="import-progress-bar">
                <div class="import-progress-fill" :class="{
                  'fill-error':         f.convertStatus === 'error',
                  'fill-no-transition': f.convertStatus === 'pending',
                }" :style="{
                  width: f.convertStatus === 'pending' ? '0%'
                       : f.convertStatus === 'running' ? f.convertProgress + '%'
                       : '100%'
                }"></div>
              </div>
            </div>
          </div>

          <!-- Actions : Annuler pendant le traitement, Voir la série quand terminé -->
          <div class="step-actions" style="display:flex; justify-content:flex-end; margin-top:16px;">
            <button v-if="uploading && !allDone" class="btn btn-danger btn-sm" @click="cancelAll" :disabled="cancelRequested">
              {{ cancelRequested ? 'Annulation…' : 'Annuler' }}
            </button>
            <template v-if="allDone">
              <p class="progress-count">
                {{ fileStatuses.filter(f => f.uploadStatus === 'ok').length }} fichier(s) importé(s)
                <template v-if="uploadErrors.length"> — {{ uploadErrors.length }} erreur(s)</template>
              </p>
              <button @click="goToSeries" class="btn btn-primary btn-sm">Voir la série →</button>
            </template>
          </div>
        </div>
      </div>
    </main>

    <!-- Modale alerte métadonnées perdues -->
    <Teleport to="body">
      <div v-if="showMetaWarnModal" class="modal-backdrop" @click.self="showMetaWarnModal = false">
        <div class="modal-box">
          <p class="modal-title">⚠️ Métadonnées non enregistrées</p>
          <p class="modal-body">
            Au moins un fichier n'est pas au format CBZ — les métadonnées saisies ne seront pas enregistrées.
            Voulez-vous activer la conversion en CBZ, ou continuer sans métadonnées ?
          </p>
          <div class="modal-actions">
            <button class="btn btn-ghost btn-sm" @click="showMetaWarnModal = false; showConvert = true">Activer la conversion</button>
            <button class="btn btn-primary btn-sm" @click="showMetaWarnModal = false; startImport()">Importer sans métadonnées</button>
          </div>
        </div>
      </div>
    </Teleport>
  </AppLayout>
</template>

<style scoped>
.import-main {
  flex: 1;
  padding: 20px;
  max-width: 1100px;
}

.import-header {
  margin-bottom: 24px;
}

.import-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 16px;
}

/* Steps indicator */
.steps {
  display: flex;
  align-items: center;
  gap: 0;
  position: relative;
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px 6px 0;
  z-index: 1;
}
.step-num {
  width: 26px; height: 26px;
  border-radius: 50%;
  background: var(--border);
  color: var(--muted);
  font-size: 0.8rem; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.step.active .step-num { background: var(--primary); color: #fff; }
.step.done .step-num { background: #4caf50; color: #fff; }
.step-label { font-size: 0.8125rem; color: var(--muted); }
.step.active .step-label { color: var(--text); font-weight: 600; }
.step-line {
  position: absolute; left: 0; right: 0; bottom: 0;
  height: 1px; background: var(--border); z-index: 0;
}

/* Card */
.step-card { margin-top: 0; }

/* File drop */
.file-drop-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 32px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  margin-bottom: 16px;
}
.file-drop-zone:hover { border-color: var(--primary); background: var(--primary-light); }
.file-drop-zone.dragging { border-color: var(--primary); background: var(--primary-light); border-style: solid; }
.drop-icon { margin-bottom: 8px; color: var(--muted); font-size: 80px; }
.drop-icon :deep(svg) { width: 1em; height: 1em; }
.file-drop-zone:hover .drop-icon,
.file-drop-zone.dragging .drop-icon { color: var(--primary); }
.drop-label { font-size: 0.9rem; font-weight: 500; color: var(--text); margin-bottom: 4px; }
.drop-hint { font-size: 0.8rem; color: var(--muted); }

/* Files preview */
.files-preview { margin-bottom: 8px; }
.files-count-row { margin-bottom: 6px; }
.files-select-all { display: flex; align-items: center; gap: 6px; font-size: 0.875rem; color: var(--text); cursor: pointer; user-select: none; }
.files-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 3px; max-height: 260px; overflow-y: auto; }
.files-item { display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem; padding: 4px 8px; background: var(--light); border-radius: var(--radius-sm); }
.files-item-label { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; cursor: pointer; }
.files-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.files-name-unchecked { color: var(--muted); text-decoration: line-through; }
.files-size { color: var(--muted); flex-shrink: 0; margin-left: 8px; }

/* Destination tabs */
.dest-tabs { display: flex; gap: 0; margin-bottom: 14px; border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; width: fit-content; }
.dest-tab { padding: 7px 18px; font-size: 0.8125rem; font-family: var(--font); cursor: pointer; background: none; border: none; color: var(--muted); }
.dest-tab.active { background: var(--primary); color: #fff; }

/* Section title */
.section-title { font-size: 0.9rem; font-weight: 600; color: var(--text); margin-bottom: 14px; }

/* ── Step 2 ── */
.alert-warning { background: var(--warning-bg-light); border: 1px solid var(--warning-border); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 0.8125rem; color: var(--warning-text); margin-bottom: 10px; }

/* Blocs pliables */
.collapsible-block { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; margin-bottom: 12px; }
.modal-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
}
.modal-box {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 24px 28px;
  max-width: 420px; width: 90%;
}
.modal-title { font-size: 1rem; font-weight: 700; margin-bottom: 10px; }
.modal-body { font-size: 0.875rem; color: var(--text); margin-bottom: 8px; line-height: 1.5; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }
.import-file-list { display: flex; flex-direction: column; gap: 6px; }
.import-file-row {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--surface);
}
.import-file-main {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; gap: 12px;
}
.import-file-name {
  font-size: 0.85rem; color: var(--text); font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.import-file-statuses {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.8rem; flex-shrink: 0;
}
.import-progress-bar {
  height: 4px; background: var(--border); width: 100%;
}
.import-progress-fill {
  height: 100%;
  transition: width 0.4s ease, background-color 0.3s ease;
}
.import-progress-fill { background: var(--primary); }
.fill-error { background: var(--danger); }
.fill-no-transition { transition: none !important; }
.collapsible-toggle { display: flex; align-items: center; gap: 8px; width: 100%; padding: 9px 14px; background: var(--light); border: none; cursor: pointer; font-size: 0.8125rem; font-weight: 600; color: var(--text); text-align: left; }
.collapsible-toggle:hover { background: var(--border); }
.collapsible-hint { font-size: 0.75rem; font-weight: 400; color: var(--muted); margin-left: 4px; }
.toggle-arrow { font-size: 0.65rem; color: var(--muted); transition: transform 0.15s; display: inline-block; flex-shrink: 0; }
.toggle-arrow.open { transform: rotate(90deg); }
.collapsible-body { padding: 12px 14px 14px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }

/* Renommage - outillage */
.field-row { display: flex; align-items: center; gap: 10px; }
.form-label { font-size: 0.8125rem; color: var(--muted); white-space: nowrap; font-weight: 500; }
.pattern-input { flex: 1; }
.tokens-row { display: flex; flex-wrap: wrap; gap: 6px; }
.token-btn { font-size: 0.75rem; padding: 2px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface); cursor: pointer; color: var(--primary); font-family: monospace; }
.token-btn:hover { background: var(--primary); color: #fff; border-color: var(--primary); }
.sub-section { border-top: 1px solid var(--border); padding-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.sub-section-label { font-size: 0.75rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
.rule-row { display: flex; align-items: center; gap: 6px; }
.rule-checkbox { flex-shrink: 0; width: 15px; height: 15px; cursor: pointer; }
.rule-input { flex: 1; font-size: 0.78rem; padding: 4px 7px; min-width: 0; }
.rule-arrow { flex-shrink: 0; color: var(--muted); font-size: 0.8rem; }
.add-rule-btn { align-self: flex-start; font-size: 0.78rem; }

/* Tableaux internes (communs aux deux blocs) */
.inner-table-wrap { overflow-x: auto; overflow-y: auto; max-height: 320px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.inner-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
.inner-table th { text-align: left; padding: 6px 10px; background: var(--light); color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; position: sticky; top: 0; z-index: 1; }
.inner-table td { padding: 4px 10px; border-bottom: 1px solid var(--light); vertical-align: middle; }
.inner-table tr:last-child td { border-bottom: none; }
.row-duplicate td { background: var(--warning-bg-light); }
.row-unchecked td { opacity: 0.45; }

/* Tableau renommage */
.col-original { width: 42%; }
.col-rename { width: 46%; }
.col-size { width: 10%; white-space: nowrap; }
.td-original { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
.td-final { display: flex; align-items: center; gap: 4px; padding: 2px 10px; }
.td-size { color: var(--muted); }
.rename-input { flex: 1; min-width: 0; border: none; background: transparent; font-size: 0.78rem; color: var(--text); padding: 2px 0; outline: none; font-family: inherit; border-bottom: 1px solid transparent; }
.rename-input:focus { border-bottom: 1px solid var(--primary); }
.rename-input-conflict { color: var(--danger); }
.conflict-icon { flex-shrink: 0; font-size: 0.78rem; font-weight: 600; color: var(--danger); }
.badge-dup { flex-shrink: 0; background: #ff8f00; color: #fff; font-size: 0.68rem; padding: 1px 5px; border-radius: 8px; }

/* Édition par lot */
.batch-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 10px; background: var(--light); border-radius: var(--radius-sm); }
.batch-label { font-size: 0.75rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.batch-input { flex: 1; min-width: 80px; max-width: 160px; font-size: 0.78rem; }
.batch-only-empty { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--muted); white-space: nowrap; cursor: pointer; margin-left: 4px; }

/* Tableau métadonnées */
.meta-table { min-width: 700px; }
.col-meta-file { width: 26%; }
.col-meta-series { width: 12%; }
.col-meta-number { width: 5%; }
.col-meta-title { width: 14%; }
.col-meta-writer { width: 11%; }
.col-meta-penciller { width: 11%; }
.col-meta-publisher { width: 11%; }
.col-meta-languageiso { width: 3%; }
.col-meta-scrape { width: 28px; }
.td-meta-file { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
.td-meta { padding: 2px 6px; }
.td-meta-scrape { padding: 2px 4px; text-align: center; }
.meta-input { width: 100%; border: none; background: transparent; font-size: 0.78rem; color: var(--text); padding: 2px 3px; outline: none; font-family: inherit; border-bottom: 1px solid transparent; min-width: 0; }
.meta-input:focus { border-bottom: 1px solid var(--primary); background: var(--primary-light); }
.scrape-btn { background: none; border: none; cursor: pointer; font-size: 0.85rem; padding: 2px 4px; border-radius: var(--radius-sm); opacity: 0.5; transition: opacity 0.15s; }
.scrape-btn:hover { opacity: 1; background: var(--light); }


/* Step actions */
.step-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }

/* Progress */
.progress-count { font-size: 0.875rem; color: var(--muted); margin-bottom: 8px; }
.import-done-icon { font-size: 3rem; margin-bottom: 12px; }
.error-list { list-style: none; padding: 0; margin: 16px 0; text-align: left; display: flex; flex-direction: column; gap: 4px; }
.error-item { font-size: 0.8125rem; color: var(--danger); background: var(--danger-bg-light); padding: 6px 10px; border-radius: var(--radius-sm); }

.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }

/* Formats badge (partagé avec ConverterModal) */
.fmt-badge { font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }

/* Bloc conversion — preset */
.convert-presets { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.convert-preset-option {
  display: flex; flex-direction: column; align-items: center;
  padding: 6px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; transition: border-color 0.15s, background 0.15s; min-width: 80px;
}
.convert-preset-option:hover { border-color: var(--border); background: var(--light); }
.convert-preset-selected { border-color: var(--primary); background: var(--primary-light); box-shadow: 0 0 0 2px var(--primary-focus); }
.convert-preset-name { font-size: 0.8rem; font-weight: 600; color: var(--text); }
.convert-preset-desc { font-size: 0.7rem; color: var(--muted); }

/* Conversion — indicateur non modifié */
.convert-no-convert { font-size: 0.8125rem; color: var(--success); background: var(--success-bg-light); border: 1px solid var(--success-border); border-radius: var(--radius-sm); padding: 7px 12px; }
.estimate-smaller { color: var(--success); font-weight: 600; }
.estimate-same { color: var(--muted); }
.td-no-convert { color: var(--muted); font-style: italic; font-size: 0.75rem; }
.td-muted { color: var(--muted); }

/* Étape 3 — statuts */
.td-status { font-size: 0.78rem; white-space: nowrap; }
.status-pending { color: var(--muted); }
.status-running { color: var(--primary); font-style: italic; }
.btn-danger { background: var(--danger); color: #fff; border: none; }
.btn-danger:hover:not(:disabled) { opacity: 0.88; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
.status-done { color: var(--success); font-weight: 700; }
.status-error { color: var(--danger); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; display: inline-block; }
.status-skip { color: var(--muted); }
.convert-pages { font-style: normal; font-weight: 600; margin-left: 4px; font-size: 0.75rem; }

/* Quality info icon + popover */
.quality-info-wrap { position: relative; display: inline-flex; align-items: center; }
.quality-info-icon {
  width: 15px; height: 15px; color: var(--muted);
  cursor: default; flex-shrink: 0;
  transition: color 0.15s;
}
.quality-info-wrap:hover .quality-info-icon { color: var(--primary); }
.quality-popover {
  z-index: 9999;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 12px;
  width: 400px;
}
.quality-popover-title { font-size: 0.75rem; font-weight: 600; color: var(--muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.04em; }
.quality-popover-images { display: flex; gap: 10px; }
.quality-popover-img-wrap { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.quality-popover-img-wrap img { width: 100%; border-radius: var(--radius-sm); border: 1px solid var(--border); }
.quality-popover-img-wrap span { font-size: 0.72rem; color: var(--muted); }
</style>
