<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import imgLight from '../assets/images/quality-light.jpg'
import imgOriginal from '../assets/images/quality-originale.jpg'
import { useRouter, useRoute } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import ScraperModal from '../components/metadata/ScraperModal.vue'
import SvgIcon from '../components/SvgIcon.vue'
import AutocompleteInput from '../components/ui/AutocompleteInput.vue'
import { importApi } from '../api/import'
import { libraryApi } from '../api/library'
import { scraperApi } from '../api/scraper'
import { missingAlbumsApi } from '../api/missingAlbums'
import client from '../api/client'
import { useNotificationStore } from '../stores/notifications'
import { useLibraryStore } from '../stores/library'
import { mapWithConcurrency } from '../utils/concurrency'
import { applyRenamePattern, formatTomeNumber } from '../utils/renamePattern'
import { normalizeSearch, sortTitle } from '../utils/text'
import { settingsApi } from '../api/settings'
import { tomesApi } from '../api/tomes'
import Hint from '../components/ui/Hint.vue'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/shadcn/hover-card'
import AppDialog from '../components/ui/AppDialog.vue'

const router = useRouter()
const route = useRoute()
const notif = useNotificationStore()
const libraryStore = useLibraryStore()

// ── Étape courante ──────────────────────────────────────────────────────────
const step = ref(1)

// ── Étape 1 — Sélection ─────────────────────────────────────────────────────
const fileInput = ref(null)
const folderInput = ref(null)
const rawFiles = ref([])
const existingSeries = ref([])
// destMode reste 'new' | 'existing', mais n'est plus choisi via des onglets — c'est une
// conséquence de la sélection faite dans le champ de recherche unique ci-dessous.
// null tant qu'aucune destination n'a été choisie.
const destMode = ref(null)
const destSeriesId = ref(null)
const destSeriesName = ref('')
// URL Bedetheque.com saisie pour une nouvelle série — permet de compléter les métadonnées
// de tous les albums en une fois à l'étape 2 (voir completeFromBedetheque), puis d'attacher
// l'URL à la série une fois créée (voir startImport) pour bénéficier aussi du suivi des
// albums manquants, comme une série dont l'URL est renseignée depuis sa fiche.
const newSeriesBedethequeUrl = ref('')

// Modèle de renommage configuré dans Configuration → Bibliothèque (fetch dans ── Init
// ── plus bas). Vide = pas de renommage.
const renamePattern = ref('')

// Recherche de série (combobox unique : input texte + liste filtrée + "créer nouvelle série")
const seriesSearch = ref('')
const showSeriesDropdown = ref(false)
const showCreateSeriesConfirm = ref(false)
const pendingNewSeriesName = ref('')

const filteredExistingSeries = computed(() => {
  const q = normalizeSearch(seriesSearch.value.trim())
  if (!q) return existingSeries.value
  return existingSeries.value.filter(s => normalizeSearch(s.name).includes(q))
})

// On ne propose "créer une nouvelle série" que s'il n'existe pas déjà une série au nom
// identique (à accents/casse près) — évite de créer un doublon par accident.
const canOfferCreateNew = computed(() => {
  const q = seriesSearch.value.trim()
  if (!q) return false
  const nq = normalizeSearch(q)
  return !existingSeries.value.some(s => normalizeSearch(s.name) === nq)
})

function onSeriesSearchInput() {
  // Si l'utilisateur retape après avoir choisi une destination, on invalide la sélection
  // précédente tant qu'il n'en reconfirme pas une (existante ou nouvelle).
  if (destMode.value === 'existing') {
    const cur = existingSeries.value.find(s => s.id === destSeriesId.value)
    if (!cur || cur.name !== seriesSearch.value) { destSeriesId.value = null; destMode.value = null }
  } else if (destMode.value === 'new') {
    if (destSeriesName.value !== seriesSearch.value) { destSeriesName.value = ''; destMode.value = null; newSeriesBedethequeUrl.value = '' }
  }
  showSeriesDropdown.value = true
}

function onSeriesSearchBlur() {
  // Délai pour laisser le @mousedown d'une option s'exécuter avant la fermeture
  setTimeout(() => { showSeriesDropdown.value = false }, 150)
}

function selectExistingSeries(s) {
  destMode.value = 'existing'
  destSeriesId.value = s.id
  destSeriesName.value = ''
  newSeriesBedethequeUrl.value = ''
  seriesSearch.value = s.name
  showSeriesDropdown.value = false
  // Préremplir les métadonnées par lot (étape 2) avec ce qu'on sait déjà de la série
  batchRow.value.Series = s.name
  if (s.writers?.length)    batchRow.value.Writer    = s.writers.join(', ')
  if (s.pencillers?.length) batchRow.value.Penciller = s.pencillers.join(', ')
  if (s.publishers?.length) batchRow.value.Publisher = s.publishers.join(', ')
}

// Séries dont le nom contient (ou est contenu dans) la saisie sans l'égaler exactement —
// ex. "Agent 212" tapé alors que "L'agent 212" existe déjà. Piège réel repéré en usage :
// la recherche affichait à la fois la bonne suggestion existante ET le bouton "créer une
// nouvelle série", menant à créer par erreur un doublon plutôt que d'ajouter à l'existante.
const similarSeriesForNew = ref([])
// URL retenue dans la popup de confirmation de création — copiée dans newSeriesBedethequeUrl
// seulement si l'utilisateur confirme (voir confirmCreateSeries). Peut venir d'une carte
// suggérée (bedeSuggestions) ou d'une saisie manuelle.
const pendingNewSeriesBedethequeUrl = ref('')
// Suggestions Bedetheque (nom + nombre d'albums + statut + années) pour aider à choisir la
// bonne série sans avoir à ouvrir Bedetheque.com — voir bedetheque-suggest côté backend.
const bedeSuggestions = ref([])       // candidats enrichis (nom, nb albums, statut, années)
const bedeSuggestLoading = ref(false)
// Champ URL manuel replié tant que l'utilisateur ne le demande pas explicitement — cliquer
// sur une carte suggérée ne doit pas faire apparaître l'URL en clair (alourdit la popup).
const showManualBedeUrl = ref(false)

function askCreateSeries() {
  pendingNewSeriesName.value = seriesSearch.value.trim()
  pendingNewSeriesBedethequeUrl.value = ''
  showManualBedeUrl.value = false
  similarSeriesForNew.value = filteredExistingSeries.value
  showSeriesDropdown.value = false
  showCreateSeriesConfirm.value = true

  bedeSuggestions.value = []
  bedeSuggestLoading.value = true
  scraperApi.bedethequeSuggest(pendingNewSeriesName.value)
    .then(({ data }) => { bedeSuggestions.value = data })
    .catch(() => { bedeSuggestions.value = [] })
    .finally(() => { bedeSuggestLoading.value = false })
}

function pickSimilarSeries(s) {
  selectExistingSeries(s)
  showCreateSeriesConfirm.value = false
}

async function confirmCreateSeries() {
  destMode.value = 'new'
  destSeriesName.value = pendingNewSeriesName.value
  destSeriesId.value = null
  newSeriesBedethequeUrl.value = pendingNewSeriesBedethequeUrl.value.trim()
  seriesSearch.value = pendingNewSeriesName.value
  showCreateSeriesConfirm.value = false
  // Si des fichiers sont déjà sélectionnés (cas courant — la destination se choisit après),
  // valider la popup suffit à avancer directement, sans clic "Suivant →" en plus.
  // goToStep2() ne fait rien si aucun fichier n'est encore sélectionné.
  await goToStep2()
}

function cancelCreateSeries() {
  showCreateSeriesConfirm.value = false
}

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
  // Pré-remplit juste le champ de recherche — l'utilisateur choisit ensuite une série
  // existante correspondante ou confirme la création via le combobox.
  if (folder && !seriesSearch.value) seriesSearch.value = folder
}

function onDrop(e) {
  dragging.value = false
  const files = e.dataTransfer?.files
  if (files?.length) {
    rawFiles.value = filterFiles(files)
    initSelection(rawFiles.value)
    const folder = detectFolderName(files)
    if (folder && !seriesSearch.value) seriesSearch.value = folder
  }
}

const allStep1Selected = computed(() => rawFiles.value.every(f => rawFileSelection.value[f.name]))
const selectedRawCount = computed(() => rawFiles.value.filter(f => rawFileSelection.value[f.name]).length)

function toggleAllStep1(checked) {
  const sel = {}
  for (const f of rawFiles.value) sel[f.name] = checked
  rawFileSelection.value = sel
}

// ── Étape 1 — indicateur de conflit/doublon (avant même de passer à l'étape 2) ──────
// rawFileWarnings[filename] = { conflict, duplicate }. conflict = deux fichiers
// sélectionnés donneraient le même nom une fois renommés. duplicate = ce nom existe
// déjà dans la destination choisie.
const rawFileWarnings = ref({})
let step1WarnTimer = null

function scheduleStep1Warnings() {
  clearTimeout(step1WarnTimer)
  step1WarnTimer = setTimeout(refreshStep1Warnings, 400)
}

async function refreshStep1Warnings() {
  const selected = rawFiles.value.filter(f => rawFileSelection.value[f.name])
  if (!selected.length) { rawFileWarnings.value = {}; return }

  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null
  const seriesFallback = destMode.value === 'new' ? destSeriesName.value.trim()
    : existingSeries.value.find(s => s.id === destSeriesId.value)?.name || ''

  const computedNames = await mapWithConcurrency(selected, 6, async f => {
    let p = {}
    try {
      const { data } = await importApi.parseFilename(f.name)
      p = data
    } catch { /* ignoré */ }
    const ext = f.name.includes('.') ? '.' + f.name.split('.').pop() : ''
    const stem = f.name.includes('.') ? f.name.slice(0, f.name.lastIndexOf('.')) : f.name
    const finalName = renamePattern.value
      ? applyRenamePattern(renamePattern.value, {
          stem, ext,
          series: p.series || seriesFallback,
          number: p.number || '',
          title: p.title || '',
          year: p.year || '',
          penciller: p.penciller || '',
          writer: p.writer || '',
          publisher: p.publisher || '',
        }, [])
      : f.name
    return { name: f.name, finalName }
  })

  // Conflit : deux fichiers sélectionnés qui donneraient le même nom final
  const counts = {}
  for (const { finalName } of computedNames) counts[finalName] = (counts[finalName] || 0) + 1

  const warnings = {}
  await mapWithConcurrency(computedNames, 6, async ({ name, finalName }) => {
    const conflict = counts[finalName] > 1
    let duplicate = false
    if (sid || sname) {
      try {
        const { data } = await importApi.checkFile(finalName, sid, sname)
        duplicate = data.duplicate
      } catch { /* ignoré */ }
    }
    if (conflict || duplicate) warnings[name] = { conflict, duplicate }
  })
  rawFileWarnings.value = warnings
}

watch([rawFiles, rawFileSelection, destMode, destSeriesId, destSeriesName, renamePattern], scheduleStep1Warnings, { deep: true })

async function goToStep2() {
  if (!rawFiles.value.length) return
  if (!destMode.value) return

  // Filtrer uniquement les fichiers cochés en étape 1
  const selectedFiles = rawFiles.value.filter(f => rawFileSelection.value[f.name])
  if (!selectedFiles.length) return

  // Récupérer les infos parsées de chaque fichier (concurrence bornée — un dossier de
  // 150+ fichiers ne doit pas taper le backend avec 150 requêtes simultanées)
  const parsed = await mapWithConcurrency(selectedFiles, 6, async f => {
    try {
      const { data } = await importApi.parseFilename(f.name)
      return data
    } catch { return {} }
  })

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

  // Série (nouvelle avec URL saisie, ou existante déjà identifiée sur Bedetheque) :
  // préremplissage automatique sans clic supplémentaire — nextTick pour laisser le watcher
  // sur `items` initialiser metaRows avant que completeFromBedetheque() ne le lise.
  if (currentBedethequeSource()) {
    await nextTick()
    completeFromBedetheque()
  }

  // Charger les résolutions en arrière-plan (CBZ/CBR uniquement, fichiers sélectionnés seulement).
  // Mutation directe de la clé (imageSizes.value reste le même objet réactif) au lieu de
  // recopier tout l'objet à chaque résolution — évite un coût O(n²) sur un gros import.
  imageSizes.value = {}
  for (const item of items.value) {
    const ext = '.' + item.originalName.split('.').pop().toLowerCase()
    if (ext === '.cbz' || ext === '.cbr' || ext === '.zip') {
      importApi.getImageSize(item.file).then(({ data }) => {
        if (data.width) imageSizes.value[item.originalName] = data
      }).catch(() => {})
    }
  }
}

// ── Étape 2 — Renommage (silencieux, pattern fixé dans Configuration) ────────
const items = ref([])
// imageSizes[originalName] = { width, height } | null
const imageSizes = ref({})

// Applique le modèle configuré dans Configuration → Bibliothèque. Pattern vide = nom
// d'origine conservé tel quel.
function applyPattern(item) {
  // Un fichier coché pour conversion sera réellement enregistré en .cbz (voir
  // converter_service.py, qui remplace le tome en place avec la nouvelle extension) —
  // l'aperçu doit refléter ce résultat final, pas l'extension du fichier source (PDF/CBR).
  const willConvert = !!convertChecked.value[item.originalName]
  const ext = willConvert ? '.cbz' : (item.originalName.includes('.') ? '.' + item.originalName.split('.').pop() : '')
  const stem = item.originalName.includes('.') ? item.originalName.slice(0, item.originalName.lastIndexOf('.')) : item.originalName
  // Priorité : metaRows (édités) > parsed > fallback
  const m = metaRows.value[item.originalName] || {}
  const p = item.parsed || {}
  const isOneshot = !!oneshotRows.value[item.originalName]
  // Miroir de apply_pattern() côté backend (routers/tomes.py) : un one-shot n'a ni série
  // ni numéro, le modèle configuré (avec {Série}/{Numéro}) n'a pas de sens pour lui.
  const pattern = isOneshot ? '{Titre}' : renamePattern.value
  if (!pattern) return item.originalName
  const seriesName = destMode.value === 'new' ? destSeriesName.value.trim()
    : existingSeries.value.find(s => s.id === destSeriesId.value)?.name || ''
  return applyRenamePattern(pattern, {
    stem, ext,
    series: isOneshot ? '' : (m.Series || p.series || seriesName || ''),
    number: isOneshot ? '' : (m.Number || p.number || ''),
    title: m.Title || p.title || '',
    year: m.Year || p.year || '',
    penciller: m.Penciller || p.penciller || '',
    writer: m.Writer || p.writer || '',
    publisher: m.Publisher || p.publisher || '',
  }, [])
}

// Nom réellement écrit sur disque au moment de l'upload initial — toujours l'extension
// d'origine du fichier sélectionné, jamais .cbz par anticipation (contrairement à
// applyPattern/item.finalName, qui prévisualise volontairement le résultat final). Sinon
// des octets encore au format source (CBR/PDF) atterrissent sous un nom .cbz, et toute
// lecture de ce fichier avant l'issue de la conversion (ou si elle échoue) se fie à tort à
// cette extension au lieu du contenu réel — la conversion elle-même se charge de renommer
// le fichier en .cbz une fois le contenu réellement réencodé (voir convertOne/converter_service.py).
function uploadFilename(item) {
  if (!convertChecked.value[item.originalName]) return item.finalName
  const originalExt = item.originalName.includes('.') ? '.' + item.originalName.split('.').pop() : ''
  const stem = item.finalName.includes('.') ? item.finalName.slice(0, item.finalName.lastIndexOf('.')) : item.finalName
  return stem + originalExt
}

async function checkDuplicates() {
  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null
  for (const item of items.value) item.finalName = applyPattern(item)
  await mapWithConcurrency(items.value, 6, async item => {
    try {
      const { data } = await importApi.checkFile(item.finalName, sid, sname)
      item.duplicate = data.duplicate
    } catch { item.duplicate = false }
  })
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
const META_FIELDS = ['Series', 'Number', 'Year', 'Title', 'Penciller', 'Writer', 'Publisher', 'LanguageISO']
const META_LABELS = { Series: 'Série', Number: 'N°', Year: 'Année', Title: 'Titre', Writer: 'Scénariste', Penciller: 'Dessinateur', Publisher: 'Éditeur', LanguageISO: 'Langue' }
const BATCH_FIELDS = ['Series', 'Penciller', 'Writer', 'Publisher', 'LanguageISO']
const batchRow = ref({ Series: '', Penciller: '', Writer: '', Publisher: '', LanguageISO: '' })
const batchOnlyEmpty = ref(true)
// Valeurs originales avant tout remplissage par lot (pour distinguer "vide d'origine" de "rempli par le lot")
const metaOriginal = ref({})

// metaRows[originalName][field] = valeur saisie
const metaRows = ref({})
// oneshotRows[originalName] = bool — indépendant de metaRows (pas un champ ComicInfo.xml,
// un fait sur le tome, voir Tome.is_oneshot). Conserve la valeur déjà cochée d'un fichier
// existant plutôt que de tout réinitialiser à chaque recalcul de la liste (ex. réordonnancement).
const oneshotRows = ref({})

watch(items, (newItems) => {
  const next = {}
  const nextOneshot = {}
  const seriesName = destMode.value === 'new'
    ? destSeriesName.value.trim()
    : existingSeries.value.find(s => s.id === destSeriesId.value)?.name || ''
  for (const item of newItems) {
    const p = item.parsed || {}
    const alreadyOneshot = oneshotRows.value[item.originalName] || false
    next[item.originalName] = {
      // Un one-shot n'a pas de série — sans ce garde, un fichier déjà coché one-shot
      // récupérait quand même le nom du dossier de destination à chaque recalcul de la
      // liste (ex. réordonnancement), pas seulement à la création de la ligne, jusqu'à ce
      // que la case soit explicitement décochée puis recochée (voir onOneshotToggle).
      Series: alreadyOneshot ? '' : (p.series || seriesName),
      Number: p.number || '',
      Title: p.title || '',
      Writer: p.writer || '',
      Penciller: p.penciller || '',
      Publisher: p.publisher || '',
      LanguageISO: p.languageiso || 'fr',
    }
    nextOneshot[item.originalName] = alreadyOneshot
  }
  metaRows.value = next
  oneshotRows.value = nextOneshot
  // Snapshot des valeurs originales pour le filtre "seulement si vide"
  metaOriginal.value = JSON.parse(JSON.stringify(next))
}, { immediate: true })

const allOneshot = computed(() => items.value.length > 0 && items.value.every(item => oneshotRows.value[item.originalName]))

// Un one-shot n'appartient à aucune série — dès que la case est cochée, on vide le champ
// Série de la ligne (il avait pu être pré-rempli par le nom du dossier de destination ou une
// recherche en ligne précédente), plutôt que de compter uniquement sur le blocage du scraper.
function onOneshotToggle(item) {
  if (oneshotRows.value[item.originalName]) {
    const row = metaRows.value[item.originalName]
    if (row) row.Series = ''
  }
}

function toggleAllOneshot() {
  const next = !allOneshot.value
  const nextRows = { ...oneshotRows.value }
  for (const item of items.value) {
    nextRows[item.originalName] = next
    if (next) {
      const row = metaRows.value[item.originalName]
      if (row) row.Series = ''
    }
  }
  oneshotRows.value = nextRows
}

function applyBatch() {
  const next = { ...metaRows.value }
  for (const item of items.value) {
    // Le traitement par lot n'a pas de sens pour un one-shot : ni la série (il n'en a pas),
    // ni les autres champs (dessinateur/scénariste/éditeur/langue), un dossier one-shot
    // regroupant typiquement des albums indépendants sans rapport entre eux.
    if (oneshotRows.value[item.originalName]) continue
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

// Scraper par fichier
const scraperTarget = ref(null) // { originalName, series, number }

function openScraper(item) {
  const row = metaRows.value[item.originalName] || {}
  const isOneshot = !!oneshotRows.value[item.originalName]
  // Repli sur le nom de fichier (sans extension) si aucun titre n'a pu être parsé — mieux
  // qu'un champ de recherche vide, et surtout jamais le nom de la série/du dossier pour un
  // one-shot (voir ScraperModal.vue, qui n'utilise plus jamais Série/Numéro dans ce cas).
  const stem = item.originalName.includes('.') ? item.originalName.slice(0, item.originalName.lastIndexOf('.')) : item.originalName
  scraperTarget.value = {
    originalName: item.originalName,
    series: row.Series || '',
    number: row.Number || '',
    title: row.Title || (isOneshot ? stem : ''),
    isOneshot,
  }
}

function applyScraperResult(result) {
  if (!scraperTarget.value) return
  const row = metaRows.value[scraperTarget.value.originalName]
  if (!row) return
  if (result.title)            row.Title     = result.title
  // Un one-shot n'a pas de série : Bedetheque crée pourtant une page "série" du même nom
  // que l'album pour chaque one-shot — on ignore ce champ pour ne pas la faire fuiter ici.
  if (result.series && !scraperTarget.value.isOneshot) row.Series = result.series
  if (result.number)           row.Number    = formatTomeNumber(result.number)
  if (result.source === 'bedetheque' && result.authors?.length) {
    // Bedetheque distingue scénariste et dessinateur (contrairement à Google Books/ComicVine)
    row.Writer    = result.authors[0] || ''
    row.Penciller = result.authors[1] || result.authors[0] || ''
  } else if (result.authors?.length) {
    row.Writer    = result.authors.join(', ')
  }
  if (result.publisher)        row.Publisher = result.publisher
  if (result.year)             row.Year      = String(result.year)
  // Lien vers la fiche de cet album précisément — capturé dès l'import plutôt que
  // seulement au prochain passage dans la popup d'édition (voir MetadataForm.vue).
  if (result.url)              row.Web       = result.url
  scraperTarget.value = null
}

// Complétion globale — une seule requête pour toute la page série Bedetheque, puis
// association par numéro d'album à chaque ligne du tableau, au lieu de rechercher fichier
// par fichier via openScraper() (qui reste le repli manuel si un album n'est pas trouvé ici).
// Nouvelle série : URL saisie à la création. Série existante : URL déjà confirmée en base,
// pas besoin de la re-saisir à chaque import dans cette série.
const bedeBulkLoading = ref(false)

function currentBedethequeSource() {
  if (destMode.value === 'new') {
    const url = newSeriesBedethequeUrl.value.trim()
    return url ? { url: url, seriesId: null } : null
  }
  if (destMode.value === 'existing') {
    const s = existingSeries.value.find(s => s.id === destSeriesId.value)
    if (s?.bedetheque_url && s.bedetheque_match_status === 'found') {
      return { url: null, seriesId: s.id }
    }
  }
  return null
}

async function completeFromBedetheque() {
  const source = currentBedethequeSource()
  if (!source || bedeBulkLoading.value) return
  bedeBulkLoading.value = true
  try {
    const { data: albums } = await scraperApi.bedethequeBulk(source.url, source.seriesId)
    const byNumber = {}
    for (const a of albums) { if (a.number) byNumber[a.number] = a }

    let matched = 0
    for (const item of items.value) {
      const row = metaRows.value[item.originalName]
      if (!row) continue
      const num = (row.Number || item.parsed?.number || '').trim()
      const album = num ? byNumber[num] : null
      if (!album) continue
      matched++
      if (album.title)     row.Title     = album.title
      if (album.writer)    row.Writer    = album.writer
      if (album.penciller) row.Penciller = album.penciller
      if (album.publisher) row.Publisher = album.publisher
    }
    metaRows.value = { ...metaRows.value }
    notif.success(matched
      ? `${matched}/${items.value.length} album(s) complété(s) depuis Bedetheque.com`
      : 'Aucun album correspondant trouvé sur cette page Bedetheque.com')
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la récupération sur Bedetheque.com')
  } finally {
    bedeBulkLoading.value = false
  }
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

// Comparateur de qualité : HoverCard de shadcn-vue (survol ou focus clavier sur l'icône),
// rendu dans <body> et positionné par Reka UI — au-dessus de la modale, jamais hors écran.

const convertPreset = ref(null) // null = aucune qualité sélectionnée par défaut
// convertChecked[originalName] = true/false
const convertChecked = ref({})

// Fichiers éligibles à la conversion (CBR ou PDF)
const convertibleItems = computed(() =>
  items.value.filter(i => CONVERT_EXTS.has('.' + i.originalName.split('.').pop().toLowerCase()))
)

// Nom affiché dans le bloc conversion — doit refléter le renommage en direct, pas le
// nom d'origine, sinon le fichier affiché ne correspond pas à ce qui sera importé.
function currentFinalName(item) {
  return applyPattern(item)
}

// Nom (sans extension) affiché dans le tableau Métadonnées — l'extension d'origine n'a
// pas de sens ici : elle ne correspond ni au fichier d'origine (le nom a changé) ni au
// futur fichier si une conversion est prévue (ex: .pdf → .cbz).
function currentFinalStem(item) {
  const name = currentFinalName(item)
  return name.includes('.') ? name.slice(0, name.lastIndexOf('.')) : name
}


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

// Quand on sélectionne un preset, cocher automatiquement les fichiers qui nécessitent
// une conversion (CBR/PDF) mais pas les CBZ/ZIP déjà dans le bon format
const AUTO_CONVERT_EXTS = new Set(['.cbr', '.rar', '.pdf'])
watch(convertPreset, (val) => {
  if (!val) return
  const next = {}
  for (const item of convertibleItems.value) {
    const ext = '.' + item.originalName.split('.').pop().toLowerCase()
    next[item.originalName] = AUTO_CONVERT_EXTS.has(ext)
  }
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
const finalizing = ref(false)
const cancelRequested = ref(false)
const activeJobIds = ref([])

// Tableau unifié : une entrée par fichier importé
// { name, uploadStatus: 'pending'|'ok'|'error', uploadError, convertStatus: null|'pending'|'running'|'done'|'error', convertProgress, convertPagesNow, convertPagesTotal }
const fileStatuses = ref([])

const uploadErrors = computed(() => fileStatuses.value.filter(f => f.uploadStatus === 'error'))
const allDone = computed(() => allDoneFlag.value)

// Si l'utilisateur quitte la page pendant un import/conversion en cours, on annule
// proprement (comme le bouton "Annuler") au lieu de laisser startImport() continuer
// en tâche de fond sans plus aucune UI pour le suivre.
onUnmounted(() => {
  if (uploading.value && !allDoneFlag.value) {
    cancelAll()
  }
})

async function startImport() {
  uploading.value = true
  uploadDone.value = 0
  allDoneFlag.value = false
  finalizing.value = false
  cancelRequested.value = false
  activeJobIds.value = []
  step.value = 3

  const sid = destMode.value === 'existing' ? destSeriesId.value : null
  const sname = destMode.value === 'new' ? destSeriesName.value.trim() : null

  for (const item of items.value) item.finalName = applyPattern(item)

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
    let uploadedTomeId = null
    try {
      const meta = metaRows.value[item.originalName] || {}
      const { data } = await importApi.uploadFile(item.file, uploadFilename(item), sid, sname, meta, !!oneshotRows.value[item.originalName])
      fileStatuses.value[i].uploadStatus = 'ok'
      fileStatuses.value[i].destPath = data.path
      destPath = data.path
      uploadedTomeId = data.tome_id || null
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
      await convertOne(i, destPath, uploadedTomeId)
    }
  }

  // Nettoyage si annulation : supprimer les fichiers déjà uploadés, leur entrée DB
  // (tome + série si elle devient vide) et resynchroniser la bibliothèque
  if (cancelRequested.value) {
    const uploadedPaths = fileStatuses.value
      .filter(f => f.destPath)
      .map(f => f.destPath)
    if (uploadedPaths.length) {
      const isNewSeries = destMode.value === 'new'
      try {
        const { data } = await client.post('/api/import/cancel-cleanup', {
          paths: uploadedPaths,
          is_new_series: isNewSeries,
          new_series_name: isNewSeries ? destSeriesName.value.trim() : null,
        })
        if (data?.deleted_count) {
          notif.info(`Import annulé — ${data.deleted_count} fichier(s) supprimé(s)`)
        }
      } catch { /* ignoré */ }
      await libraryStore.fetchSeries()
    }
    allDoneFlag.value = true
    return
  }

  // Scan final — tous les fichiers sont déjà uploadés/convertis à ce stade, il ne reste
  // qu'à réindexer la bibliothèque. "finalizing" distingue cette phase de l'upload/conversion
  // proprement dits : jusqu'ici l'en-tête restait bloqué sur "Import en cours…" et le bouton
  // Annuler restait affiché sans plus rien de significatif à annuler pendant ce temps.
  finalizing.value = true
  try {
    await libraryStore.triggerScan()
    await waitForScan()
  } finally {
    finalizing.value = false
  }

  // Trouver l'ID de la série importée
  const seriesName = sname || existingSeries.value.find(s => s.id === sid)?.name
  if (seriesName) {
    const { data } = await libraryApi.getSeries()
    const found = data.find(s => s.name === seriesName)
    if (found) importedSeriesId.value = found.id
  } else if (sid) {
    importedSeriesId.value = sid
  }

  // Attache l'URL Bedetheque saisie en étape 1 à la série nouvellement créée — même
  // endpoint que "Corriger l'URL" sur la fiche série, ce qui déclenche aussi le suivi des
  // albums manquants si applicable.
  if (destMode.value === 'new' && newSeriesBedethequeUrl.value.trim() && importedSeriesId.value) {
    try {
      await missingAlbumsApi.setBedethequeUrl(importedSeriesId.value, newSeriesBedethequeUrl.value.trim())
    } catch { /* ignoré — l'import reste réussi même si cette étape échoue */ }
  }

  allDoneFlag.value = true
  const okCount = fileStatuses.value.filter(f => f.uploadStatus === 'ok').length
  notif.success(`Import terminé — ${okCount} fichier(s) importé(s)`)
}

async function convertOne(idx, destPath, uploadedTomeId = null) {
  // Utiliser le tome_id retourné par l'upload — évite un scan complet de la bibliothèque
  let tomeId = uploadedTomeId

  if (!tomeId) {
    // Fallback : lookup avec scan à la volée si le tome n'est pas encore en DB
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const { data } = await importApi.lookupTomes([destPath])
        tomeId = data[destPath]
      } catch { break }
      if (tomeId) break
      await new Promise(r => setTimeout(r, 1000))
    }
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
        if (data.status === 'done') {
          // La conversion a renommé/déplacé le fichier (ex : .cbr -> .cbz) : recharger le
          // chemin réel pour qu'une annulation juste après cible le bon fichier.
          try {
            const { data: tomeData } = await tomesApi.getTome(tomeId)
            if (tomeData.filepath) fileStatuses.value[idx].destPath = tomeData.filepath
          } catch { /* ignoré */ }
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
  // Attendre max 150s que le scan se termine
  for (let i = 0; i < 300; i++) {
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
// /api/series a déjà writers/pencillers/publishers agrégés — réutilisés pour préremplir
// les métadonnées par lot quand on choisit une série existante (cf. selectExistingSeries).
libraryApi.getSeries().then(({ data }) => {
  existingSeries.value = [...data].sort((a, b) => sortTitle(a.name).localeCompare(sortTitle(b.name), 'fr', { sensitivity: 'base' }))
})
libraryStore.fetchAuthors()
settingsApi.get().then(({ data }) => { renamePattern.value = data.rename_pattern || '' })

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

function resetImport() {
  step.value = 1
  rawFiles.value = []
  rawFileSelection.value = {}
  rawFileWarnings.value = {}
  items.value = []
  fileStatuses.value = []
  destMode.value = null
  destSeriesName.value = ''
  destSeriesId.value = null
  newSeriesBedethequeUrl.value = ''
  seriesSearch.value = ''
  showSeriesDropdown.value = false
  showCreateSeriesConfirm.value = false
  similarSeriesForNew.value = []
  uploading.value = false
  allDoneFlag.value = false
  cancelRequested.value = false
  activeJobIds.value = []
  importedSeriesId.value = null
  convertPreset.value = null
  convertChecked.value = {}
}

// Reset à l'étape 1 si on navigue vers /import depuis une autre étape
watch(() => route.path, (path) => {
  if (path === '/import' && step.value > 1) resetImport()
})
</script>

<template>
  <AppLayout>
    <main class="import-main">
      <!-- Header -->
      <div class="import-header">
        <h1 class="import-title">Importer des albums</h1>
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
            <!-- Fichiers individuels : input "normal", pas de webkitdirectory (qui force
                 un sélecteur de dossier et ignore le filtre `accept`). -->
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".cbz,.cbr,.pdf,.zip,.rar"
              style="display:none"
              @change="onFilesSelected"
            />
            <!-- Dossier complet : input séparé avec webkitdirectory. -->
            <input
              ref="folderInput"
              type="file"
              multiple
              webkitdirectory
              style="display:none"
              @change="onFilesSelected"
            />
            <SvgIcon :name="dragging ? 'upload' : 'folder-up'" class="drop-icon" />
            <p class="drop-label">{{ dragging ? 'Déposer les fichiers ici' : 'Cliquer ou glisser-déposer des fichiers' }}</p>
            <p class="drop-hint">
              Formats acceptés : CBZ, CBR, PDF — ou
              <button type="button" class="link-btn" @click.stop="folderInput.click()">choisir un dossier</button>
            </p>
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
                  <span
                    v-if="rawFileWarnings[f.name]"
                    class="files-warn-icon"
                    :title="[
                      rawFileWarnings[f.name].conflict ? 'Conflit : un autre fichier sélectionné aurait le même nom une fois renommé' : '',
                      rawFileWarnings[f.name].duplicate ? 'Un fichier de ce nom existe déjà dans la destination' : '',
                    ].filter(Boolean).join(' — ')"
                  >⚠</span>
                </label>
                <span class="files-size">{{ formatSize(f.size) }}</span>
              </li>
            </ul>
          </div>

          <h2 class="section-title" style="margin-top: 24px">2. Choisir la destination</h2>

          <div class="field series-search-field">
            <label class="form-label">Série</label>
            <input
              type="text"
              class="form-control"
              v-model="seriesSearch"
              placeholder="Rechercher ou créer une série…"
              @focus="showSeriesDropdown = true"
              @input="onSeriesSearchInput"
              @blur="onSeriesSearchBlur"
            />
            <p v-if="destMode === 'existing'" class="dest-status">✓ Série existante « {{ seriesSearch }} »</p>
            <template v-else-if="destMode === 'new'">
              <p class="dest-status">✓ Nouvelle série « {{ seriesSearch }} »</p>
              <p v-if="newSeriesBedethequeUrl" class="dest-status-hint">🔗 {{ newSeriesBedethequeUrl }}</p>
            </template>
            <ul v-if="showSeriesDropdown" class="series-dropdown">
              <li
                v-for="s in filteredExistingSeries"
                :key="s.id"
                :class="{ 'series-option-active': s.id === destSeriesId }"
                @mousedown.prevent="selectExistingSeries(s)"
              >{{ s.name }}</li>
              <li v-if="canOfferCreateNew" class="series-option-create" @mousedown.prevent="askCreateSeries">
                + Créer une nouvelle série « {{ seriesSearch.trim() }} »
              </li>
              <li v-if="!filteredExistingSeries.length && !canOfferCreateNew" class="series-option-empty">Aucune série trouvée</li>
            </ul>
          </div>

          <div class="step-actions">
            <button @click="router.push('/series')" class="btn btn-ghost btn-sm">Annuler</button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!selectedRawCount || !destMode"
              @click="goToStep2"
            >Suivant →</button>
          </div>
        </div>
      </div>

      <!-- ── Étape 2 ── -->
      <div v-if="step === 2" class="card step-card">
        <div class="card-body">

          <!-- ① Bloc métadonnées -->
          <div class="import-section">
            <h2 class="section-title">Métadonnées</h2>

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
                <label class="batch-only-empty" title="Sans rapport avec les autres tomes du dossier — voir Tome.is_oneshot">
                  <input type="checkbox" :checked="allOneshot" @change="toggleAllOneshot" />
                  Tout marquer one-shot
                </label>
              </div>

              <!-- Tableau métadonnées par fichier -->
              <div class="inner-table-wrap">
                <table class="inner-table meta-table">
                  <thead>
                    <tr>
                      <th class="col-meta-file">Fichier</th>
                      <th v-for="f in META_FIELDS" :key="f" :class="`col-meta-${f.toLowerCase()}`">{{ META_LABELS[f] }}</th>
                      <th class="col-meta-oneshot" title="Album indépendant, sans rapport avec les autres tomes du dossier">One-shot</th>
                      <th class="col-meta-scrape"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in items" :key="item.originalName">
                      <td class="td-meta-file" :title="currentFinalName(item)">{{ currentFinalStem(item) }}</td>
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
                      <td class="td-meta-oneshot">
                        <input type="checkbox" v-model="oneshotRows[item.originalName]" @change="onOneshotToggle(item)" title="Album one-shot" />
                      </td>
                      <td class="td-meta-scrape">
                        <Hint label="Rechercher en ligne">
                          <button class="scrape-btn" type="button" @click="openScraper(item)"><SvgIcon name="search" /></button>
                        </Hint>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
          </div>

          <div class="section-divider" />

          <!-- ② Bloc conversion -->
          <div class="import-section">
            <h2 class="section-title">Convertir / Recompresser en CBZ <span class="collapsible-hint">(optionnel)</span></h2>
              <!-- Indicateur si aucune qualité / aucun fichier coché -->
              <div v-if="!convertPreset || convertCount === 0" class="convert-no-convert">
                ✓ Les fichiers seront importés sans modification
              </div>
              <!-- Preset qualité -->
              <div class="convert-presets">
                <span class="form-label">Qualité :</span>
                <HoverCard :open-delay="100" :close-delay="100">
                  <HoverCardTrigger as-child>
                    <span class="quality-info-wrap" tabindex="0" aria-label="Comparer les qualités">
                      <SvgIcon name="info" class="quality-info-icon" />
                    </span>
                  </HoverCardTrigger>
                  <HoverCardContent align="start" class="w-auto border-0 bg-transparent p-0 shadow-none">
                    <div class="quality-popover">
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
                  </HoverCardContent>
                </HoverCard>
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
                      <th style="width:95px">Format</th>
                      <th style="width:90px">Résolution</th>
                      <th class="col-size">Taille actuelle</th>
                      <th class="col-size">Taille estimée</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in convertibleItems" :key="item.originalName">
                      <td><input type="checkbox" v-model="convertChecked[item.originalName]" /></td>
                      <td>{{ currentFinalName(item) }}</td>
                      <td>
                        <span :class="['fmt-badge', `fmt-${item.originalName.split('.').pop().toLowerCase()}`]">{{ item.originalName.split('.').pop().toUpperCase() }}</span>
                        <template v-if="convertChecked[item.originalName]">
                          <span class="fmt-arrow">→</span>
                          <span class="fmt-badge fmt-cbz">CBZ</span>
                        </template>
                      </td>
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
        :series-id="scraperTarget.isOneshot ? null : (destMode === 'existing' ? destSeriesId : null)"
        :title="scraperTarget.title"
        :is-oneshot="scraperTarget.isOneshot"
        @select="applyScraperResult"
        @close="scraperTarget = null"
      />

      <!-- ── Étape 3 ── -->
      <div v-if="step === 3" class="card step-card">
        <div class="card-body">
          <h2 class="section-title">{{ allDone ? 'Import terminé' : finalizing ? 'Mise à jour de la bibliothèque…' : 'Import en cours…' }}</h2>

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
          <div class="step-actions step-actions-final">
            <button v-if="uploading && !allDone && !finalizing" class="btn btn-danger btn-sm" @click="cancelAll" :disabled="cancelRequested">
              {{ cancelRequested ? 'Annulation…' : 'Annuler' }}
            </button>
            <template v-if="allDone">
              <p class="progress-count">
                {{ fileStatuses.filter(f => f.uploadStatus === 'ok').length }} fichier(s) importé(s)
                <template v-if="uploadErrors.length"> — {{ uploadErrors.length }} erreur(s)</template>
              </p>
              <div class="step-actions-buttons">
                <button @click="resetImport" class="btn btn-ghost btn-sm">Importer d'autres albums</button>
                <button @click="goToSeries" class="btn btn-primary btn-sm">Voir la série →</button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </main>

    <!-- Modale confirmation création série -->
    <AppDialog v-if="showCreateSeriesConfirm" title="Créer une nouvelle série ?" @close="cancelCreateSeries">
      <div class="modal-box">
        <p class="modal-title">Créer une nouvelle série ?</p>
        <p class="modal-body">
          Êtes-vous sûr de vouloir créer la série « {{ pendingNewSeriesName }} » ?
        </p>
        <div v-if="similarSeriesForNew.length" class="similar-series-warning">
          <p class="similar-series-warning-title">⚠️ Nom proche d'une série déjà existante — vérifiez qu'il ne s'agit pas de la même série avant de continuer :</p>
          <button
            v-for="s in similarSeriesForNew"
            :key="s.id"
            type="button"
            class="similar-series-option"
            @click="pickSimilarSeries(s)"
          >« {{ s.name }} » <span class="similar-series-count">{{ s.tome_count ?? 0 }} album(s)</span></button>
        </div>
        <div class="field modal-bede-field">
          <p v-if="bedeSuggestLoading" class="bede-suggest-loading">Recherche sur Bedetheque.com…</p>
          <div v-else-if="bedeSuggestions.length" class="bede-suggest-list">
            <div
              v-for="c in bedeSuggestions"
              :key="c.url"
              role="button"
              tabindex="0"
              :class="['bede-suggest-card', { 'bede-suggest-selected': pendingNewSeriesBedethequeUrl === c.url }]"
              @click="pendingNewSeriesBedethequeUrl = c.url"
              @keydown.enter="pendingNewSeriesBedethequeUrl = c.url"
            >
              <span class="bede-suggest-check">{{ pendingNewSeriesBedethequeUrl === c.url ? '✓' : '' }}</span>
              <span class="bede-suggest-info">
                <span class="bede-suggest-name">{{ c.name }}</span>
                <span class="bede-suggest-meta">
                  {{ c.album_count }} album(s)<template v-if="c.status"> · {{ c.status }}</template><template v-if="c.year_min"> · {{ c.year_min }}{{ c.year_max && c.year_max !== c.year_min ? '–' + c.year_max : '' }}</template>
                </span>
              </span>
              <Hint label="Voir sur Bedetheque.com">
                <a :href="c.url" target="_blank" rel="noopener" class="bede-suggest-link" @click.stop>↗</a>
              </Hint>
            </div>
          </div>
          <button
            v-if="bedeSuggestions.length && !bedeSuggestLoading"
            type="button"
            class="link-btn bede-manual-toggle"
            @click="showManualBedeUrl = !showManualBedeUrl"
          >{{ showManualBedeUrl ? 'Masquer' : 'Ou saisir une URL manuellement' }}</button>
          <input
            v-if="showManualBedeUrl || (!bedeSuggestLoading && !bedeSuggestions.length)"
            type="text"
            class="form-control"
            v-model="pendingNewSeriesBedethequeUrl"
            placeholder="https://www.bedetheque.com/serie-XXXXX-BD-....html"
            style="margin-top: 6px"
          />
          <p v-if="!bedeSuggestLoading" class="dest-status-hint">Permet de compléter automatiquement les métadonnées de tous les albums à l'étape suivante.</p>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost btn-sm" @click="cancelCreateSeries">Annuler</button>
          <button class="btn btn-primary btn-sm" :disabled="bedeSuggestLoading" @click="confirmCreateSeries">{{ similarSeriesForNew.length ? 'Créer quand même' : 'Créer' }}</button>
        </div>
      </div>
    </AppDialog>

    <!-- Modale alerte métadonnées perdues -->
    <AppDialog v-if="showMetaWarnModal" title="Métadonnées non enregistrées" @close="showMetaWarnModal = false">
      <div class="modal-box">
        <p class="modal-title">⚠️ Métadonnées non enregistrées</p>
        <p class="modal-body">
          Au moins un fichier n'est pas au format CBZ — les métadonnées saisies ne seront pas enregistrées.
          Voulez-vous activer la conversion en CBZ, ou continuer sans métadonnées ?
        </p>
        <div class="modal-actions">
          <button class="btn btn-ghost btn-sm" @click="showMetaWarnModal = false">Annuler</button>
          <button class="btn btn-primary btn-sm" @click="showMetaWarnModal = false; startImport()">Importer sans métadonnées</button>
        </div>
      </div>
    </AppDialog>
  </AppLayout>
</template>

<style scoped>
.import-main {
  flex: 1;
  padding: 24px 20px;
  max-width: 1250px;
}

.import-header {
  margin-bottom: 24px;
}

.import-title {
  font-family: var(--font-display);
  font-weight: 400;
  text-transform: uppercase;
  font-size: 1.4rem;
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
.step.active .step-num { background: var(--vermilion); color: #fff; }
.step.done .step-num { background: var(--success); color: #fff; }
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
.link-btn { background: none; border: none; padding: 0; color: var(--vermilion); font-size: 0.8rem; text-decoration: underline; cursor: pointer; }

/* Files preview */
.files-preview { margin-bottom: 8px; }
.files-count-row { margin-bottom: 6px; }
.files-select-all { display: flex; align-items: center; gap: 6px; font-size: 0.875rem; color: var(--text); cursor: pointer; user-select: none; }
.files-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 3px; max-height: 260px; overflow-y: auto; }
.files-item { display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem; padding: 4px 8px; background: var(--light); border-radius: var(--radius-sm); }
.files-item-label { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; cursor: pointer; }
.files-warn-icon { flex-shrink: 0; color: var(--danger); font-size: 0.85rem; cursor: help; }
.files-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.files-name-unchecked { color: var(--muted); text-decoration: line-through; }
.files-size { color: var(--muted); flex-shrink: 0; margin-left: 8px; }


/* Section title */
.section-title { font-size: 0.9rem; font-weight: 600; color: var(--text); margin-bottom: 14px; }

/* ── Step 2 ── */
.alert-warning { background: var(--warning-bg-light); border: 1px solid var(--warning-border); border-radius: var(--radius-sm); padding: 8px 12px; font-size: 0.8125rem; color: var(--warning-text); margin-bottom: 10px; }

/* Sections étape 2 (toujours visibles, plus d'accordéon) */
.import-section { display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; }
.section-divider { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
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

.similar-series-warning {
  margin-top: 4px;
  padding: 10px 12px;
  background: var(--warning-bg, #fffbeb);
  border: 1px solid var(--warning-bg, #fffbeb);
  border-radius: var(--radius-sm);
  display: flex; flex-direction: column; gap: 6px;
}
.similar-series-warning-title { font-size: 0.8rem; color: var(--orange-bar, #b45309); font-weight: 600; line-height: 1.4; }
.similar-series-option {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  width: 100%; text-align: left;
  padding: 6px 10px;
  font-size: 0.82rem; font-family: var(--font);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer; color: var(--text);
  transition: background 0.12s, border-color 0.12s;
}
.similar-series-option:hover { background: var(--primary-light); border-color: var(--primary-focus-border); color: var(--primary); }
.similar-series-count { flex-shrink: 0; font-size: 0.75rem; color: var(--muted); }
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
.collapsible-hint { font-size: 0.75rem; font-weight: 400; color: var(--muted); margin-left: 4px; }
.form-label { font-size: 0.8125rem; color: var(--muted); white-space: nowrap; font-weight: 500; }

/* Tableaux internes (communs aux deux blocs) */
.inner-table-wrap { overflow-x: auto; overflow-y: auto; max-height: 320px; border: 1px solid var(--border); border-radius: var(--radius-sm); }
.inner-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
.inner-table th { text-align: left; padding: 6px 10px; background: var(--light); color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; position: sticky; top: 0; z-index: 1; }
.inner-table td { padding: 4px 10px; border-bottom: 1px solid var(--light); vertical-align: middle; }
.inner-table tr:last-child td { border-bottom: none; }
.col-size { width: 10%; white-space: nowrap; }
.td-size { color: var(--muted); }

/* Édition par lot */
.batch-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 10px; background: var(--light); border-radius: var(--radius-sm); }
.batch-label { font-size: 0.75rem; font-weight: 600; color: var(--muted); white-space: nowrap; }
.batch-input { flex: 1; min-width: 80px; max-width: 160px; font-size: 0.78rem; }
.batch-only-empty { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--muted); white-space: nowrap; cursor: pointer; margin-left: 4px; }

/* Tableau métadonnées */
.meta-table { min-width: 700px; }
.col-meta-file { width: 21%; }
.col-meta-series { width: 12%; }
.col-meta-number { width: 5%; }
.col-meta-year { width: 6%; }
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
.scrape-btn { background: none; border: none; cursor: pointer; font-size: 1.15rem; padding: 2px 4px; border-radius: var(--radius-sm); opacity: 0.5; transition: opacity 0.15s; }
.scrape-btn:hover { opacity: 1; background: var(--light); }


/* Step actions */
.step-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border); }
/* Étape 3 (fin d'import) : décompte détaché sur sa propre ligne, boutons regroupés en dessous
   — sinon "X fichier(s) importé(s)" se retrouvait collé aux boutons sur la même ligne. */
.step-actions-final { flex-direction: column; align-items: flex-end; gap: 8px; }
.step-actions-final .progress-count { margin-bottom: 0; }
.step-actions-buttons { display: flex; gap: 8px; }

/* Progress */
.progress-count { font-size: 0.875rem; color: var(--muted); margin-bottom: 8px; }
.import-done-icon { font-size: 3rem; margin-bottom: 12px; }
.error-list { list-style: none; padding: 0; margin: 16px 0; text-align: left; display: flex; flex-direction: column; gap: 4px; }
.error-item { font-size: 0.8125rem; color: var(--danger); background: var(--danger-bg-light); padding: 6px 10px; border-radius: var(--radius-sm); }

.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }

/* Combobox recherche de série existante — pas dans une scroll-row, position:absolute ok */
.series-search-field { position: relative; }
.series-dropdown {
  position: absolute; top: calc(100% + 2px); left: 0; right: 0; z-index: 20;
  max-height: 220px; overflow-y: auto; margin: 0; padding: 4px; list-style: none;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0,0,0,0.12);
}
.series-dropdown li { padding: 6px 10px; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
.series-dropdown li:hover, .series-option-active { background: var(--primary-light); }
.series-option-empty { color: var(--muted); cursor: default; }
.series-option-empty:hover { background: none; }
.series-option-create { color: var(--vermilion); font-weight: 600; border-top: 1px solid var(--border); margin-top: 2px; padding-top: 8px; }
.dest-status { font-size: 0.78rem; color: var(--success-text, var(--primary)); margin: 2px 0 0; }
.modal-bede-field { margin: 14px 0 0; }
.bede-suggest-loading { font-size: 0.8rem; color: var(--muted); margin: 0; }
.bede-suggest-list { display: flex; flex-direction: column; gap: 6px; }
.bede-suggest-card {
  display: flex; align-items: center; gap: 8px;
  width: 100%; text-align: left;
  padding: 6px 10px;
  font-family: var(--font);
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
  cursor: pointer; color: var(--text);
  transition: background 0.12s, border-color 0.12s;
}
.bede-suggest-card:hover { background: var(--primary-light); border-color: var(--primary-focus-border); }
.bede-suggest-selected { background: var(--primary-light); border-color: var(--primary); }
.bede-suggest-check { flex-shrink: 0; width: 12px; font-size: 0.8rem; font-weight: 700; color: var(--vermilion); }
.bede-suggest-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.bede-suggest-name { font-size: 0.82rem; font-weight: 600; }
.bede-suggest-meta { font-size: 0.75rem; color: var(--muted); }
.bede-suggest-link { flex-shrink: 0; font-size: 0.9rem; line-height: 1; color: var(--muted); padding: 2px 4px; text-decoration: none; }
.bede-suggest-link:hover { color: var(--vermilion); }
.bede-manual-toggle { display: block; margin-top: 6px; }
.dest-status-hint { font-size: 0.75rem; color: var(--muted); margin: 2px 0 0; }

/* Formats badge (partagé avec ConverterModal) */
.fmt-badge { font-size: 0.65rem; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.fmt-cbz { background: var(--success-bg); color: var(--success-text); }
.fmt-cbr { background: var(--warning-bg); color: var(--orange-bar); }
.fmt-pdf { background: var(--info-bg); color: var(--info-text); }
.fmt-arrow { font-size: 0.7rem; color: var(--muted); margin: 0 2px; }

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
  max-width: calc(100vw - 16px);
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
