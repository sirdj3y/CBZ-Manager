<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useReaderStore } from '../stores/reader'
import { tomesApi } from '../api/tomes'
import { libraryApi } from '../api/library'
import client from '../api/client'
import { sortTomesByNumber } from '../utils/tomeSort'
import SvgIcon from '../components/SvgIcon.vue'

const route = useRoute()
const router = useRouter()
const reader = useReaderStore()

const loading = ref(true)
// Bandeau de reprise — non bloquant : l'album s'ouvre directement à la page sauvegardée (voir
// openTome), ce bandeau n'est qu'une information transitoire ("Repris à la page X") avec une
// option "Recommencer", plutôt que l'ancienne popup qui obligeait à choisir avant de pouvoir
// lire quoi que ce soit (retour utilisateur : "revient sans cesse", trop intrusif à chaque
// ouverture d'un album déjà entamé).
const showResumeBanner = ref(false)
let resumeBannerTimer = null
const RESUME_BANNER_MS = 5000
const imgA = ref(null)  // Left/single page
const imgB = ref(null)  // Right page (double mode)
const pagesRef = ref(null)
const progressTrackRef = ref(null)
const isFullscreen = ref(false)
// iOS Safari (iPhone) ne supporte pas du tout la Fullscreen API (restriction volontaire
// d'Apple, pas propre à cette app) — document.fullscreenEnabled y vaut toujours false.
// Mieux vaut masquer le bouton que d'en laisser un qui ne fait rien au clic.
const fullscreenSupported = !!document.fullscreenEnabled
// Sur smartphone : le plein écran ne marche pas de toute façon sur iOS (voir ci-dessus, et
// Android l'ignore largement en pratique dans les navigateurs mobiles), et le mode double
// page n'a pas de sens sur un écran aussi étroit — masqués plutôt que laissés inertes/inutiles.
// Même seuil que TomeDetailView.vue (isDesktop).
const isSmartphone = ref(window.innerWidth <= 640)
function updateIsSmartphone() { isSmartphone.value = window.innerWidth <= 640 }

// Sélecteur de mode — menu déroulant (icône + libellé + chevron) plutôt que 3 boutons
// toujours visibles, repris du style demandé par l'utilisateur (capture d'écran fournie).
const showModeMenu = ref(false)
const MODE_OPTIONS = [
  { value: 'single', label: 'Page', icon: 'reader-mode-page' },
  { value: 'double', label: 'Double', icon: 'reader-mode-double' },
  { value: 'vertical', label: 'Défilement', icon: 'reader-mode-scroll' },
]
// Double page retirée du menu sur smartphone (voir plus haut : pas de sens sur écran étroit)
// plutôt que grisée sans explication.
const modeOptions = computed(() => isSmartphone.value ? MODE_OPTIONS.filter(m => m.value !== 'double') : MODE_OPTIONS)
const currentModeOption = computed(() => MODE_OPTIONS.find(m => m.value === reader.mode) || MODE_OPTIONS[0])
function selectMode(m) { reader.setMode(m); showModeMenu.value = false }

// Panneau de réglages d'image ("baguette magique") — luminosité/contraste/saturation/netteté,
// appliqués en filtre directement sur les pages (voir imageFilterStyle plus bas) : aucun
// retraitement d'image côté serveur, juste une composition de filtres natifs du navigateur,
// temps réel au glissement des curseurs.
const showAdjustPanel = ref(false)

// Netteté — CSS n'a pas de fonction "sharpen", contrairement à brightness/contrast/saturate :
// un vrai renforcement de contours est une convolution (chaque pixel recalculé à partir de
// ses voisins), qu'on délègue à un filtre SVG natif (feConvolveMatrix, voir le <svg> caché
// dans le template) plutôt qu'à une boucle JS par pixel sur un canvas — le navigateur fait le
// calcul, pas nous. Noyau classique de renforcement (Laplacien) : le centre grandit et les 4
// voisins directs sont soustraits, la somme du noyau valant toujours 1 (image inchangée en
// luminosité globale) ; k=0 → noyau identité (aucun effet).
const SHARPEN_K_MAX = 1.5
const sharpenKernelMatrix = computed(() => {
  const k = (reader.sharpness / 100) * SHARPEN_K_MAX
  const center = 1 + 4 * k
  return `0 ${-k} 0 ${-k} ${center} ${-k} 0 ${-k} 0`
})

const imageFilterStyle = computed(() => {
  const r = reader
  const parts = []
  if (r.brightness !== 100) parts.push(`brightness(${r.brightness}%)`)
  if (r.contrast !== 100) parts.push(`contrast(${r.contrast}%)`)
  if (r.saturation !== 100) parts.push(`saturate(${r.saturation}%)`)
  if (r.sharpness > 0) parts.push('url(#reader-sharpen)')
  return parts.length ? { filter: parts.join(' ') } : {}
})

// Tome suivant de la série (voir showNextTomeDialog / goToNextTome plus bas) — même
// technique que TomeDetailView.vue::nextTome (getTome pour le series_id, puis
// getSeriesDetail pour la liste triée), chargé en tâche de fond pendant la lecture plutôt
// qu'au moment où l'utilisateur termine, pour ne pas le faire attendre à ce moment-là.
const nextTomeInfo = ref(null)
const showNextTomeDialog = ref(false)

async function loadNextTomeInfo(id) {
  nextTomeInfo.value = null
  try {
    const { data: tome } = await tomesApi.getTome(id)
    if (!tome.series_id) return
    const { data: series } = await libraryApi.getSeriesDetail(tome.series_id)
    const sorted = sortTomesByNumber(series.tomes || [])
    const idx = sorted.findIndex(t => t.id === Number(id))
    if (idx >= 0 && idx < sorted.length - 1) nextTomeInfo.value = sorted[idx + 1]
  } catch { /* pas bloquant : au pire, pas de proposition de tome suivant */ }
}

function goToNextTome() {
  if (!nextTomeInfo.value) return
  showNextTomeDialog.value = false
  // replace (pas push) : sinon Échap/retour depuis le tome suivant rouvrait le lecteur sur le
  // tome qu'on vient de terminer au lieu de sortir du lecteur (l'historique gardait les deux
  // pages /read successives). En remplaçant l'entrée courante, le retour saute directement à
  // ce qui précédait ce tome-là (sa fiche album, ou d'où on avait lancé la lecture).
  router.replace(`/read/${nextTomeInfo.value.id}`)
}

// ── Temps de lecture actif (statistiques "Ma lecture") ──
// Compte le temps réellement passé à lire, pas le temps où l'onglet reste simplement ouvert :
// suspendu quand l'onglet est en arrière-plan (visibilitychange) ou après un long moment sans
// la moindre interaction (IDLE_THRESHOLD_MS) — sans quoi un onglet oublié ouvert sur une BD
// gonflerait artificiellement les statistiques. markActivity() est appelé depuis les
// interactions déjà suivies ailleurs dans ce fichier (clic, touche, molette, tactile, défilement)
// plutôt que via de nouveaux écouteurs dédiés.
const ACTIVITY_TICK_MS = 15000
const IDLE_THRESHOLD_MS = 90000
const HEARTBEAT_FLUSH_MS = 60000
let lastActivityAt = Date.now()
let pendingSeconds = 0
let lastFlushAt = Date.now()
let activityTimer = null

function markActivity() { lastActivityAt = Date.now() }

// beacon=true pour les cas où la page peut disparaître avant qu'une requête normale n'ait le
// temps d'aboutir (fermeture d'onglet, changement de tome) — navigator.sendBeacon est conçu
// spécifiquement pour ça, contrairement à un simple appel axios qui peut être annulé en cours.
function flushReadingTime(beacon = false) {
  if (pendingSeconds <= 0 || !reader.tomeId) return
  const seconds = pendingSeconds
  pendingSeconds = 0
  lastFlushAt = Date.now()
  const url = `/api/reader/${reader.tomeId}/heartbeat`
  if (beacon && navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([JSON.stringify({ seconds })], { type: 'application/json' }))
    return
  }
  client.post(url, { seconds }).catch(() => { /* un battement perdu n'est pas grave */ })
}

function activityTick() {
  const visible = document.visibilityState === 'visible'
  const active = (Date.now() - lastActivityAt) < IDLE_THRESHOLD_MS
  if (visible && active) pendingSeconds += ACTIVITY_TICK_MS / 1000
  if (Date.now() - lastFlushAt >= HEARTBEAT_FLUSH_MS) flushReadingTime()
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') flushReadingTime(true)
}
function onPageHide() { flushReadingTime(true) }

async function openTome(id) {
  loading.value = true
  showNextTomeDialog.value = false
  clearTimeout(resumeBannerTimer)
  showResumeBanner.value = false
  // Avant de changer reader.tomeId (voir reader.loadTome ci-dessous) : le temps accumulé
  // jusqu'ici appartient au tome qu'on quitte, pas au suivant.
  flushReadingTime(true)
  await reader.loadTome(Number(id))
  loading.value = false
  if (reader.hasSavedProgress) {
    // La lecture démarre du début par défaut (currentPage déjà à 0 via reader.loadTome) — le
    // bandeau propose la reprise comme une action explicite ("Reprendre à la page X"),
    // pendant quelques secondes, plutôt que de reprendre automatiquement et de proposer de
    // revenir en arrière.
    showResumeBanner.value = true
    resumeBannerTimer = setTimeout(() => { showResumeBanner.value = false }, RESUME_BANNER_MS)
  }
  loadNextTomeInfo(id)
}

// ── Zoom sur les cases (option désactivée par défaut, voir stores/reader.js) ──
// panelIndex : -1 = page entière (toujours l'état d'arrivée sur une page, avant le zoom
// sur la 1ère case — voulu explicitement : on voit d'abord la page, puis on zoome),
// 0..n-1 = case zoomée.
const panels = ref([])
const panelIndex = ref(-1)
const panelsLoading = ref(false)
// Comment se positionner en arrivant sur une nouvelle page : 'full' (par défaut, page
// entière) ou 'last' (en reculant depuis la page entière de la page suivante, on doit
// entrer sur la DERNIÈRE case de celle-ci — pas sa page entière à nouveau — pour que la
// marche arrière soit le miroir exact de la marche avant). Posé juste avant de changer de
// page, lu puis remis à 'full' une fois les cases de la nouvelle page chargées.
let entryMode = 'full'

async function loadPanelsForCurrentPage() {
  // Capturés avant l'appel réseau : si l'utilisateur tourne les pages vite, plusieurs appels
  // se chevauchent et rien ne garantit que celui-ci revienne le dernier — sans ce garde, la
  // réponse (plus lente) d'une page déjà quittée pouvait écraser les cases de la page
  // réellement affichée entre-temps.
  const targetTomeId = reader.tomeId
  const targetPage = reader.currentPage
  panels.value = []
  if (!reader.panelMode || !reader.tomeId) { entryMode = 'full'; panelIndex.value = -1; return }
  updateContainerSize()
  panelsLoading.value = true
  let result = []
  try {
    result = await reader.fetchPanels(targetTomeId, targetPage) || []
  } catch {
    result = []
  }
  if (reader.tomeId !== targetTomeId || reader.currentPage !== targetPage) return
  panels.value = result
  panelsLoading.value = false
  panelIndex.value = entryMode === 'last' && panels.value.length ? panels.value.length - 1 : -1
  entryMode = 'full'
}
watch(() => [reader.currentPage, reader.panelMode, reader.tomeId], loadPanelsForCurrentPage)

function goNextPanelOrPage() {
  if (reader.mode === 'vertical') {
    // Dernière page déjà atteinte : proposer le tome suivant (façon Netflix) plutôt que de ne
    // rien faire.
    if (reader.currentPage >= reader.pageCount - 1) {
      if (nextTomeInfo.value) showNextTomeDialog.value = true
      return
    }
    scrollToPage(reader.currentPage + 1)
    return
  }
  if (reader.panelMode) {
    if (panelIndex.value < panels.value.length - 1) { panelIndex.value++; return }
    entryMode = 'full'
  }
  if (reader.currentPage >= reader.pageCount - 1) {
    if (nextTomeInfo.value) showNextTomeDialog.value = true
    return
  }
  reader.nextPage()
}
function goPrevPanelOrPage() {
  if (reader.mode === 'vertical') { scrollToPage(reader.currentPage - 1); return }
  if (!reader.panelMode) { reader.prevPage(); return }
  if (panelIndex.value > -1) {
    panelIndex.value--
  } else if (reader.currentPage > 0) {
    entryMode = 'last'
    reader.prevPage()
  }
}

// Transform CSS pur (pas de recadrage serveur) : zoome l'image déjà chargée sur la case
// courante. Calculé à partir de mesures réelles (taille naturelle de l'image + taille du
// cadre) plutôt que d'une supposition sur le rendu — un premier essai basé sur "l'image
// affichée remplit le cadre" était faux dès que le ratio largeur/hauteur de la page diffère
// de celui de l'écran (cas général avec object-fit:contain, qui laisse des bandes vides
// plutôt que de déformer l'image), d'où un zoom mal centré/insuffisant.
const imgRef = ref(null)
const imgNaturalSize = ref({ w: 0, h: 0 })
function onImgLoad(e) {
  imgNaturalSize.value = { w: e.target.naturalWidth, h: e.target.naturalHeight }
}

const containerSize = ref({ w: 0, h: 0 })
function updateContainerSize() {
  if (pagesRef.value) {
    const r = pagesRef.value.getBoundingClientRect()
    containerSize.value = { w: r.width, h: r.height }
  }
}

// Marge laissée autour de la case une fois zoomée (0.85 = la case occupe 85% du cadre sur
// son axe le plus contraint, ~15% de marge visible tout autour).
const PANEL_MARGIN = 0.85

const panelGeometry = computed(() => {
  if (!reader.panelMode) return null
  const { w: natW, h: natH } = imgNaturalSize.value
  const { w: contW, h: contH } = containerSize.value
  if (!natW || !natH || !contW || !contH) return null

  // Reproduit le calcul d'object-fit:contain nous-mêmes : taille et position réelles de
  // l'image affichée à l'intérieur du cadre (souvent plus petite que le cadre sur un axe —
  // les bandes vides de part et d'autre).
  const fitScale = Math.min(contW / natW, contH / natH)
  const dispW = natW * fitScale
  const dispH = natH * fitScale
  const offX = (contW - dispW) / 2
  const offY = (contH - dispH) / 2

  const imgBase = {
    position: 'absolute', left: `${offX}px`, top: `${offY}px`,
    width: `${dispW}px`, height: `${dispH}px`, maxWidth: 'none', maxHeight: 'none',
    transformOrigin: '0 0',
  }

  const box = !panelsLoading.value && panelIndex.value >= 0 ? panels.value[panelIndex.value] : null
  if (!box) return { imgStyle: { ...imgBase, transform: 'none' }, spotlight: null }

  const [x1, y1, x2, y2] = box
  const bw = Math.max(x2 - x1, 0.02)
  const bh = Math.max(y2 - y1, 0.02)
  const cx = (x1 + x2) / 2
  const cy = (y1 + y2) / 2
  // Le plus PETIT des deux ratios : la case tient entière dans le cadre, avec de la marge
  // sur l'axe où elle est relativement plus petite — jamais coupée (contrairement à un
  // remplissage plein cadre, qui débordait et rognait la case).
  const scale = Math.min(contW / (bw * dispW), contH / (bh * dispH)) * PANEL_MARGIN
  const dx = contW / 2 - offX - cx * dispW * scale
  const dy = contH / 2 - offY - cy * dispH * scale

  // Rectangle à l'écran occupé par la case une fois zoomée — toujours centré par
  // construction (dx/dy ci-dessus visent exactement le centre du cadre) — sert à découper
  // la zone claire du fond assombri (voir spotlight ci-dessous).
  const screenW = bw * dispW * scale
  const screenH = bh * dispH * scale
  const spotlight = {
    left: `${(contW - screenW) / 2}px`,
    top: `${(contH - screenH) / 2}px`,
    width: `${screenW}px`,
    height: `${screenH}px`,
  }

  return { imgStyle: { ...imgBase, transform: `translate(${dx}px, ${dy}px) scale(${scale})` }, spotlight }
})

const panelStyle = computed(() => panelGeometry.value?.imgStyle ?? {})

// Deux réglages distincts : reader.fit choisit quel axe est cadré par défaut à 100% du
// cadre ('width' = la largeur, 'height' = la hauteur) — reader.zoom (1×-2.5×, pincement
// trackpad/Ctrl+molette ou curseur dans la barre du haut) agrandit TOUJOURS ce même axe,
// quel qu'il soit : zoomer en ajustement "hauteur" rend la page plus haute que l'écran
// (défilement vertical, .reader-pages gère déjà ce cas — voir plus bas), zoomer en
// ajustement "largeur" la rend plus large (défilement horizontal). Le lecteur de référence
// fourni par l'utilisateur laisse le zoom sans effet en ajustement "hauteur" — délibérément
// pas repris ici : en pratique, pincer pour zoomer alors qu'on est dans le réglage par défaut
// ("hauteur") ne faisait RIEN, ce qui semblait être un zoom cassé plutôt qu'un choix de
// design (retour utilisateur direct).
const singlePageStyle = computed(() => {
  if (reader.panelMode) return panelStyle.value
  if (reader.fit === 'height') {
    return { height: (100 * reader.zoom) + '%', width: 'auto', maxWidth: 'none', maxHeight: 'none' }
  }
  return { width: (100 * reader.zoom) + '%', maxWidth: 'none', height: 'auto', maxHeight: 'none' }
})
const doublePageStyle = computed(() => {
  if (reader.fit === 'height') return { height: (100 * reader.zoom) + '%', width: 'auto', maxWidth: 'none' }
  return { width: (50 * reader.zoom) + '%', maxWidth: 'none', height: 'auto' }
})
const spotlightStyle = computed(() => {
  const s = panelGeometry.value?.spotlight
  return s ? { ...s, opacity: 1 } : { opacity: 0 }
})

// ── Mode Défilement (scroll continu) ──
// Toutes les pages sont rendues directement (loading="eager"/"lazy" natif du navigateur se
// charge de ne pas lancer 100+ requêtes d'un coup, voir le template) — plus simple et plus
// robuste que l'ancien chargement progressif piloté par IntersectionObserver, qui dérivait à
// chaque changement de zoom (les pages changent de hauteur, donc de position). Suivi de la
// page "courante" repris du référentiel fourni : au lieu d'observer les intersections, on
// calcule à chaque scroll (limité à une fois par frame) quelle page couvre le point situé à
// 40% de la hauteur visible — un seuil fixe, insensible aux changements de taille des pages.
const allPageUrls = computed(() => {
  if (!reader.tomeId || !reader.pageCount) return []
  return Array.from({ length: reader.pageCount }, (_, i) => reader.pageUrl(reader.tomeId, i))
})

let pageEls = []
function setPageEl(el, idx) {
  if (el) pageEls[idx] = el
}

// Suspend la détection le temps d'un scroll DÉCLENCHÉ PAR NOUS (scrollToPage) — sans ce
// garde, le scroll programmatique lui-même serait interprété comme une navigation manuelle
// et pourrait faire dériver reader.currentPage pendant le trajet.
let syncPending = false
let syncPendingTimer = null
let scrollRaf = null

function scrollToPage(idx, behavior = 'smooth') {
  const target = Math.max(0, Math.min(idx, reader.pageCount - 1))
  const el = pageEls[target]
  const cont = pagesRef.value
  if (!cont) return
  if (el) {
    syncPending = true
    cont.scrollTo({ top: Math.max(0, el.offsetTop - 12), behavior })
    // Filet de sécurité : sur une page déjà chargée (revisitée, ou simplement réancrée après
    // un zoom — voir onWheel), l'image ne recharge pas, donc son événement "load" ne se
    // déclenchera jamais pour lever ce blocage (voir onScrollImgLoad) — sans cette minuterie,
    // syncPending restait bloqué à true pour de bon, empêchant tout suivi de scroll par la
    // suite. "auto" (instantané, cas du réancrage zoom) se résout vite ; "smooth" (navigation
    // normale) laisse le temps à l'animation du navigateur de finir.
    clearTimeout(syncPendingTimer)
    syncPendingTimer = setTimeout(() => { syncPending = false }, behavior === 'smooth' ? 500 : 60)
  }
  if (target !== reader.currentPage) reader.goToPage(target)
}

// Une image dont la hauteur réelle diffère de l'estimation (rare, mais possible avant
// chargement) peut décaler légèrement le point d'arrivée d'un scrollToPage — une fois cette
// image chargée, on réajuste silencieusement la position exacte (sans transition, "auto").
function onScrollImgLoad(idx) {
  if (reader.mode === 'vertical' && syncPending && idx === reader.currentPage) {
    clearTimeout(syncPendingTimer)
    syncPending = false
    scrollToPage(idx, 'auto')
  }
}

function onPagesScroll() {
  markActivity()
  if (reader.mode !== 'vertical' || syncPending || scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = null
    const cont = pagesRef.value
    if (!cont) return
    const mid = cont.scrollTop + cont.clientHeight * 0.4
    let current = 0
    for (let i = 0; i < pageEls.length; i++) {
      const el = pageEls[i]
      if (el && el.offsetTop <= mid) current = i
    }
    if (current !== reader.currentPage) reader.goToPage(current)
  })
}

// Repositionne au bon endroit à chaque entrée/sortie du mode Défilement et à chaque
// changement de tome — sur [mode, tomeId, pageCount] plutôt que sur mode seul, sinon changer
// de tome en restant en mode Défilement laisserait pageEls pointer sur les anciens éléments
// DOM (démontés) du tome précédent.
watch(() => [reader.mode, reader.tomeId, reader.pageCount], async () => {
  pageEls = []
  if (reader.mode !== 'vertical' || !reader.pageCount) return
  await nextTick()
  // Reprise en cours de lecture (savedPage) : sans ce saut, le défilement recommencerait
  // toujours en haut de la première page quel que soit currentPage au moment de l'entrée
  // dans ce mode.
  scrollToPage(reader.currentPage, 'auto')
}, { immediate: true })

onUnmounted(() => {
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  clearTimeout(syncPendingTimer)
})

function onFullscreenChange() { isFullscreen.value = !!document.fullscreenElement; updateContainerSize() }
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen?.()
  else document.documentElement.requestFullscreen?.()
}

onMounted(async () => {
  await openTome(route.params.id)
  window.addEventListener('keydown', onKey)
  document.addEventListener('mousemove', markActivity)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  // Sur mobile (surtout iOS Safari), un tap près du haut/bas de l'écran peut déclencher le
  // rebond élastique natif de la page EN DESSOUS du lecteur (pourtant en position:fixed —
  // ça n'empêche pas ce comportement), donnant l'impression qu'un clic fait défiler la page
  // au lieu de zoomer. Verrouillage du scroll du body le temps du lecteur, même pattern déjà
  // utilisé pour le tiroir de menu mobile (voir AppLayout.vue).
  document.body.style.overflow = 'hidden'
  window.addEventListener('resize', updateIsSmartphone)
  window.addEventListener('resize', updateContainerSize)
  activityTimer = setInterval(activityTick, ACTIVITY_TICK_MS)
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('pagehide', onPageHide)
  await nextTick()
  updateContainerSize()
})

// Vue Router réutilise l'instance du composant pour la même route nommée : sans ce
// watcher, naviguer d'un tome à l'autre sans démontage (ex. via l'historique du
// navigateur) laisserait le lecteur bloqué sur l'ancien tome.
watch(() => route.params.id, (id) => { if (id) openTome(id) })

watch(() => reader.currentPage, () => {
  // Sans cette garde, changer de page en mode Défilement (piloté par le défilement lui-même,
  // voir setupScrollObserver) déclencherait ce reset et annulerait le scroll en cours.
  if (reader.mode !== 'vertical' && pagesRef.value) pagesRef.value.scrollTop = 0
})

function dismissResumeBanner() {
  showResumeBanner.value = false
  clearTimeout(resumeBannerTimer)
}

// Action explicite du bandeau — la lecture est déjà partie du début (voir openTome), cliquer
// saute à la page sauvegardée. Ne rien faire (ou fermer via ×) revient à démarrer du début,
// sans action supplémentaire à prévoir pour ce cas-là.
function resumeReading() {
  reader.resumeFromSaved()
  dismissResumeBanner()
}

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('mousemove', markActivity)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.body.style.overflow = ''
  window.removeEventListener('mousemove', onSeekMove)
  window.removeEventListener('mouseup', endSeek)
  window.removeEventListener('resize', updateIsSmartphone)
  window.removeEventListener('resize', updateContainerSize)
  clearInterval(activityTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('pagehide', onPageHide)
  // On quitte le lecteur (retour à la fiche album, etc.) : le temps accumulé depuis le
  // dernier envoi ne doit pas attendre le prochain HEARTBEAT_FLUSH_MS pour être compté.
  flushReadingTime(true)
})

function onKey(e) {
  markActivity()
  if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); goNextPanelOrPage() }
  if (e.key === 'ArrowLeft') { e.preventDefault(); goPrevPanelOrPage() }
  // Haut/Bas : page précédente/suivante en mode Défilement (comme Gauche/Droite) — bascule
  // l'ajustement largeur/hauteur dans les autres modes (voir reader.fit).
  if (e.key === 'ArrowUp') {
    if (reader.mode === 'vertical') { e.preventDefault(); goPrevPanelOrPage() }
    else if (!reader.panelMode) { e.preventDefault(); reader.setFit('width') }
  }
  if (e.key === 'ArrowDown') {
    if (reader.mode === 'vertical') { e.preventDefault(); goNextPanelOrPage() }
    else if (!reader.panelMode) { e.preventDefault(); reader.setFit('height') }
  }
  if (e.key === 'Escape') {
    // Menu déroulant du sélecteur de mode / panneau de réglages ouvert : Échap le referme
    // sans rien faire de plus.
    if (showModeMenu.value) { showModeMenu.value = false; return }
    if (showAdjustPanel.value) { showAdjustPanel.value = false; return }
    // Bandeau de reprise affiché : Échap l'écarte simplement (non bloquant, ne doit pas
    // empêcher la sortie du lecteur ci-dessous si l'utilisateur veut vraiment partir).
    if (showResumeBanner.value) dismissResumeBanner()
    // Popup "Tome suivant" ouverte : Échap la ferme et reste sur la dernière page, sans
    // quitter le lecteur.
    if (showNextTomeDialog.value) { showNextTomeDialog.value = false; return }
    // Un premier Échap ne fait que sortir du plein écran (comportement standard d'un
    // lecteur vidéo/image) — il en faut un second pour vraiment quitter la page.
    if (document.fullscreenElement) { document.exitFullscreen?.(); return }
    router.back()
  }
  // Raccourci "d" : fait tourner les 3 modes (Page → Double → Défilement → Page), en plus
  // du sélecteur de mode cliquable dans la barre du haut.
  if (e.key === 'd' && !reader.panelMode) reader.cycleMode()
  if (e.key === 'f') toggleFullscreen()
}

// Page "gauche" affichée en mode double — la couverture (page 0) est toujours seule, les
// paires suivantes sont (1,2), (3,4), etc. Recalculé à partir de reader.currentPage plutôt
// que de dépendre uniquement du pas de navigation (voir stores/reader.js::nextPage/prevPage) :
// reste correct même si currentPage a été positionné autrement (reprise de lecture, recherche
// dans la barre de progression, passage du mode simple au mode double en cours d'album).
const doubleLeftPage = computed(() => {
  const p = reader.currentPage
  if (p === 0) return 0
  return p % 2 === 0 ? p - 1 : p
})
// En mode double, la progression affichée (compteur + barre) suit la page gauche plutôt que
// reader.currentPage brut, qui peut ponctuellement pointer sur la page droite d'une paire
// (voir doubleLeftPage) — évite un compteur qui semble sauter un numéro.
const progressPage = computed(() => reader.mode === 'double' ? doubleLeftPage.value : reader.currentPage)

const currentPageUrl = computed(() => {
  if (!reader.tomeId) return null
  const p = reader.mode === 'double' ? doubleLeftPage.value : reader.currentPage
  return reader.pageUrl(reader.tomeId, p)
})
const nextPageUrl = computed(() =>
  reader.mode === 'double' && reader.tomeId && doubleLeftPage.value !== 0 && doubleLeftPage.value + 1 < reader.pageCount
    ? reader.pageUrl(reader.tomeId, doubleLeftPage.value + 1)
    : null
)

// Barre de progression cliquable + glissable — saut direct à une page. mousedown seul
// (sans mouvement) se comporte comme un simple clic grâce à ce même calcul de position.
let seeking = false

function pageFromClientX(clientX) {
  const rect = progressTrackRef.value.getBoundingClientRect()
  const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
  return Math.round(ratio * (reader.pageCount - 1))
}

// En mode Défilement, "aller à une page" veut dire faire défiler jusqu'à elle (currentPage
// suit alors le défilement lui-même, voir setupScrollObserver) — pas seulement changer un
// numéro affiché comme en mode page.
function seekTo(page) {
  if (reader.mode === 'vertical') scrollToPage(page)
  else reader.goToPage(page)
}

function startSeek(e) {
  seeking = true
  seekTo(pageFromClientX(e.clientX))
  window.addEventListener('mousemove', onSeekMove)
  window.addEventListener('mouseup', endSeek)
}
function onSeekMove(e) {
  if (!seeking) return
  seekTo(pageFromClientX(e.clientX))
}
function endSeek() {
  seeking = false
  window.removeEventListener('mousemove', onSeekMove)
  window.removeEventListener('mouseup', endSeek)
}

function onSeekTouchStart(e) {
  seeking = true
  seekTo(pageFromClientX(e.touches[0].clientX))
}
function onSeekTouchMove(e) {
  if (!seeking) return
  seekTo(pageFromClientX(e.touches[0].clientX))
}
function onSeekTouchEnd() { seeking = false }

// Zoomé via le pincer-zoomer natif (touch-action: pinch-zoom sur .reader-pages) : un
// glisser-déposer du doigt sert alors à se déplacer DANS l'image agrandie, pas à tourner
// la page — sans ce garde, le geste de déplacement est aussi interprété comme un swipe
// (onTouchEnd) ou un tap de zone (clickZone), changeant la page au lieu de laisser le
// panoramique natif faire son travail. window.visualViewport.scale reflète le niveau de
// zoom visuel réel (contrairement à window.devicePixelRatio, fixe) ; >1 tant que l'utilisateur
// n'a pas dézoomé, y compris juste après avoir levé le doigt.
function isPageZoomed() {
  return !!window.visualViewport && window.visualViewport.scale > 1.01
}

// Zoomer agrandit tout le contenu affiché d'un même facteur, dans tous les modes (chaque
// image grandit proportionnellement, largeur et hauteur suivant reader.zoom à l'identique —
// voir singlePageStyle/doublePageStyle) : mathématiquement, c'est un agrandissement uniforme
// autour d'un point, quel que soit le mode. Pour que ce point reste sous le curseur (ou sous
// le centre de l'écran pour le curseur de zoom, faute de position pointeur) au lieu de sauter
// à un coin, on recalcule scrollLeft/scrollTop après coup pour que le même point de CONTENU
// reste sous le même point d'ÉCRAN : contenu = scroll + écran avant zoom ; scroll =
// contenu*facteur - écran après. Ce calcul se base sur la position de scroll RÉELLE au moment
// du geste (peu importe comment le centrage CSS l'a établie au départ, y compris son défaut
// connu en mode Double — voir historique), donc reste valable partout, y compris là où le
// centrage CSS seul ne suffisait pas (mode Double).
function setZoomAnchored(newZoom, screenX, screenY) {
  const oldZoom = reader.zoom
  const cont = pagesRef.value
  if (!cont || newZoom === oldZoom) {
    reader.setZoom(newZoom)
    return
  }
  const factor = newZoom / oldZoom
  const contentX = cont.scrollLeft + screenX
  const contentY = cont.scrollTop + screenY
  reader.setZoom(newZoom)
  nextTick(() => {
    cont.scrollLeft = factor * contentX - screenX
    cont.scrollTop = factor * contentY - screenY
  })
}

function onZoomSliderInput(value) {
  const cont = pagesRef.value
  setZoomAnchored(value, cont ? cont.clientWidth / 2 : 0, cont ? cont.clientHeight / 2 : 0)
}

// Pincer sur un trackpad (ou Ctrl/⌘+molette) ne produit PAS d'événement tactile — le
// navigateur/l'OS le traduit en un événement wheel avec ctrlKey=true (deltaY négatif en
// écartant les doigts = zoomer). Sans interception, ce geste zoome toute la page web
// (comportement natif du navigateur), pas la BD. On l'intercepte pour zoomer l'image
// affichée à la place, avec reader.zoom — actif quel que soit l'ajustement en cours (voir
// singlePageStyle/doublePageStyle), donc jamais besoin de changer reader.fit ici.
function onWheel(e) {
  if (!e.ctrlKey) return
  markActivity()
  e.preventDefault()
  if (reader.panelMode) return
  // deltaY peut faire un bond ponctuel important lors d'un geste rapide/répété sur trackpad
  // (accélération native de l'OS) — sans ce plafond par événement, un seul pic pouvait faire
  // sauter le zoom d'un coup jusqu'à sa borne, donnant l'impression que le zoom "se relâchait"
  // brutalement en pleine série de gestes plutôt que de suivre chaque geste en douceur.
  const delta = Math.max(-30, Math.min(30, e.deltaY))
  const newZoom = Math.max(1, Math.min(2.5, reader.zoom - delta * 0.015))
  if (pagesRef.value) {
    const rect = pagesRef.value.getBoundingClientRect()
    setZoomAnchored(newZoom, e.clientX - rect.left, e.clientY - rect.top)
  } else {
    setZoomAnchored(newZoom, 0, 0)
  }
}

function clickZone(e) {
  markActivity()
  // Un tap en dehors du menu de mode/du panneau de réglages le referme sans déclencher en
  // plus un changement de page.
  if (showModeMenu.value) { showModeMenu.value = false; return }
  if (showAdjustPanel.value) { showAdjustPanel.value = false; return }
  // Pas de zones gauche/droite en Défilement (le scroll natif gère déjà la navigation).
  if (reader.mode === 'vertical') return
  if (isPageZoomed()) return
  const w = e.currentTarget.offsetWidth
  const x = e.clientX
  if (x < w * 0.3) goPrevPanelOrPage()
  else if (x > w * 0.7) goNextPanelOrPage()
}

// Swipe tactile : geste horizontal dominant uniquement (un scroll vertical en mode
// zoom-largeur ne doit pas déclencher un changement de page). Après un vrai swipe, les
// navigateurs mobiles ne synthétisent pas de "click" ensuite — pas de conflit avec clickZone
// pour un simple tap.
let touchStartX = 0
let touchStartY = 0
let touchActive = false
const SWIPE_THRESHOLD = 50

function onTouchStart(e) {
  markActivity()
  if (e.touches.length !== 1 || isPageZoomed()) return
  touchStartX = e.touches[0].clientX
  touchStartY = e.touches[0].clientY
  touchActive = true
}

function onTouchEnd(e) {
  if (!touchActive) return
  touchActive = false
  if (isPageZoomed()) return
  const touch = e.changedTouches[0]
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY
  if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy) * 1.5) {
    if (dx < 0) goNextPanelOrPage()
    else goPrevPanelOrPage()
  }
}
</script>

<template>
  <div class="reader" @click="clickZone" @wheel="onWheel">

    <!-- Définition de filtre uniquement (rien à afficher, voir imageFilterStyle) — le noyau
         de convolution se recalcule en direct avec le curseur de netteté. -->
    <svg width="0" height="0" style="position:absolute" aria-hidden="true">
      <filter id="reader-sharpen">
        <feConvolveMatrix order="3" :kernelMatrix="sharpenKernelMatrix" edgeMode="duplicate" preserveAlpha="true" />
      </filter>
    </svg>

    <!-- Bandeau de reprise — non bloquant : la lecture démarre du début par défaut, ce
         bandeau propose la reprise comme une action explicite plutôt que l'inverse. -->
    <Transition name="resume-banner-fade">
      <div v-if="showResumeBanner" class="resume-banner" @click.stop>
        <button class="resume-banner-action" @click="resumeReading">Reprendre à la page {{ reader.savedPage + 1 }}</button>
        <button class="resume-banner-close" @click="dismissResumeBanner" aria-label="Fermer">×</button>
      </div>
    </Transition>

    <!-- Tome suivant (fin de l'album atteinte, façon Netflix) -->
    <Teleport to="body">
      <div v-if="showNextTomeDialog && nextTomeInfo" class="resume-backdrop" @click.self="showNextTomeDialog = false">
        <div class="resume-dialog next-tome-dialog">
          <img v-if="nextTomeInfo.cover_url" :src="nextTomeInfo.cover_url" :alt="nextTomeInfo.title" class="next-tome-cover" />
          <p class="resume-title">Tome suivant</p>
          <p class="resume-sub">{{ nextTomeInfo.title || ('Tome ' + nextTomeInfo.number) }}</p>
          <div class="resume-actions">
            <button class="btn btn-primary btn-sm" @click="goToNextTome">Lire la suite →</button>
            <button class="btn btn-ghost btn-sm" @click="showNextTomeDialog = false">Rester ici</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Top toolbar — barre opaque toujours visible (plus d'auto-masquage), style repris
         d'une capture d'écran fournie par l'utilisateur : sélecteur de mode en menu
         déroulant, ajustement+zoom fusionnés en un seul bloc, boutons icônes bordés. -->
    <div class="reader-toolbar reader-toolbar-top" @click.stop="showModeMenu = false; showAdjustPanel = false">
      <!-- Flèche + titre forment une seule zone cliquable — avant, seule la flèche
           (beaucoup plus petite) ramenait en arrière. -->
      <button @click="router.back()" class="reader-back" title="Retour à la fiche album">
        <span class="reader-back-arrow">←</span>
        <span class="reader-title">{{ reader.title }}</span>
      </button>

      <!-- Sélecteur de mode — menu déroulant plutôt que 3 boutons toujours dépliés. -->
      <div class="reader-mode-dropdown" @click.stop>
        <button
          class="reader-dropdown-btn"
          :class="{ 'reader-dropdown-btn-open': showModeMenu }"
          @click="showModeMenu = !showModeMenu"
        >
          <SvgIcon :name="currentModeOption.icon" style="font-size:15px" />
          <span>{{ currentModeOption.label }}</span>
          <SvgIcon name="chevron-down" class="reader-dropdown-chevron" :class="{ 'reader-dropdown-chevron-open': showModeMenu }" style="font-size:13px" />
        </button>
        <div v-if="showModeMenu" class="reader-dropdown-menu">
          <button
            v-for="m in modeOptions" :key="m.value"
            class="reader-dropdown-item"
            :class="{ 'reader-dropdown-item-active': reader.mode === m.value }"
            @click="selectMode(m.value)"
          >
            <SvgIcon :name="m.icon" style="font-size:15px" />
            <span>{{ m.label }}</span>
          </button>
        </div>
      </div>

      <!-- Ajustement + zoom fusionnés : le libellé (Largeur/Hauteur) bascule l'ajustement
           au clic, le curseur pilote le zoom — sans objet en mode Défilement pour le
           libellé (pas de notion de cadrage là-bas), mais le curseur y reste actif (le zoom
           s'y applique toujours, voir singlePageStyle/doublePageStyle). Masqué sur
           smartphone (le pincement tactile natif suffit) et en zoom sur les cases (qui gère
           son propre cadrage). -->
      <div v-if="!isSmartphone && !reader.panelMode" class="reader-zoom-group">
        <button
          v-if="reader.mode !== 'vertical'"
          class="reader-fit-label"
          @click="reader.setFit(reader.fit === 'width' ? 'height' : 'width')"
          :title="reader.fit === 'width' ? 'Ajusté à la largeur — cliquer pour ajuster à la hauteur' : 'Ajusté à la hauteur — cliquer pour ajuster à la largeur'"
        >{{ reader.fit === 'width' ? 'Largeur' : 'Hauteur' }}</button>
        <input
          type="range"
          min="1"
          max="2.5"
          step="0.1"
          :value="reader.zoom"
          @input="onZoomSliderInput(Number($event.target.value))"
          class="reader-zoom-slider"
          title="Zoom"
        />
        <span class="reader-zoom-value">{{ Math.round(reader.zoom * 100) }}%</span>
      </div>

      <!-- Zoom sur les cases — sans objet en mode Défilement (pas de "case courante" au
           sens où l'entend son calcul de cadrage). -->
      <button
        v-if="reader.mode !== 'vertical'"
        @click="reader.setPanelMode(!reader.panelMode)"
        class="reader-icon-btn"
        :class="{ 'reader-mode-active': reader.panelMode }"
        title="Zoomer sur les cases"
      >
        <SvgIcon name="panel-zoom" style="font-size:18px" />
      </button>

      <!-- Réglages d'image — luminosité/contraste/saturation/netteté, en filtre sur les pages
           (voir imageFilterStyle) : aucun retraitement d'image, temps réel. -->
      <div class="reader-adjust-wrap" @click.stop>
        <button
          @click="showAdjustPanel = !showAdjustPanel"
          class="reader-icon-btn"
          :class="{ 'reader-mode-active': showAdjustPanel || reader.brightness !== 100 || reader.contrast !== 100 || reader.saturation !== 100 || reader.sharpness > 0 }"
          title="Réglages d'image"
        >
          <SvgIcon name="wand-sparkles" style="font-size:18px" />
        </button>
        <div v-if="showAdjustPanel" class="reader-adjust-panel">
          <div class="reader-adjust-row">
            <label class="reader-adjust-label">Luminosité</label>
            <input type="range" min="50" max="150" step="1" :value="reader.brightness" @input="reader.setBrightness(Number($event.target.value))" class="reader-adjust-slider" />
            <span class="reader-adjust-value">{{ reader.brightness }}%</span>
          </div>
          <div class="reader-adjust-row">
            <label class="reader-adjust-label">Contraste</label>
            <input type="range" min="50" max="150" step="1" :value="reader.contrast" @input="reader.setContrast(Number($event.target.value))" class="reader-adjust-slider" />
            <span class="reader-adjust-value">{{ reader.contrast }}%</span>
          </div>
          <div class="reader-adjust-row">
            <label class="reader-adjust-label">Saturation</label>
            <input type="range" min="0" max="200" step="1" :value="reader.saturation" @input="reader.setSaturation(Number($event.target.value))" class="reader-adjust-slider" />
            <span class="reader-adjust-value">{{ reader.saturation }}%</span>
          </div>
          <div class="reader-adjust-row">
            <label class="reader-adjust-label">Netteté</label>
            <input type="range" min="0" max="100" step="1" :value="reader.sharpness" @input="reader.setSharpness(Number($event.target.value))" class="reader-adjust-slider" />
            <span class="reader-adjust-value">{{ reader.sharpness }}%</span>
          </div>
          <div class="reader-adjust-sep"></div>
          <button class="reader-adjust-reset" @click="reader.resetImageAdjustments()">Réinitialiser</button>
        </div>
      </div>

      <button
        v-if="fullscreenSupported && !isSmartphone"
        @click="toggleFullscreen"
        class="reader-icon-btn"
        :title="isFullscreen ? 'Quitter le plein écran' : 'Plein écran'"
      >
        <SvgIcon :name="isFullscreen ? 'fullscreen-exit' : 'fullscreen'" style="font-size:20px" />
      </button>
    </div>

    <!-- Pages area -->
    <div v-if="loading" class="reader-loading">Chargement…</div>
    <div v-else-if="reader.loadError" class="reader-loading">
      Impossible de charger cet album.
      <button @click="router.back()" class="reader-btn" title="Retour">← Retour</button>
    </div>

    <!-- Mode Défilement — toutes les pages rendues directement ; loading="eager"/"lazy" natif
         laisse le navigateur décider quand lancer réellement le téléchargement (voir
         allPageUrls plus haut), pas besoin de gérer nous-mêmes une fenêtre de chargement. -->
    <div v-else-if="reader.mode === 'vertical'" ref="pagesRef" class="reader-scroll" @scroll="onPagesScroll">
      <img
        v-for="(url, idx) in allPageUrls"
        :key="idx"
        :ref="el => setPageEl(el, idx)"
        :src="url"
        class="reader-scroll-img"
        :loading="Math.abs(idx - reader.currentPage) <= 2 ? 'eager' : 'lazy'"
        :style="[{ width: (100 * reader.zoom) + '%', maxWidth: 'none' }, imageFilterStyle]"
        @load="onScrollImgLoad(idx)"
        @error="$event.target.style.opacity = '0.3'"
      />
    </div>

    <div
      v-else
      ref="pagesRef"
      class="reader-pages"
      @touchstart="onTouchStart"
      @touchend="onTouchEnd"
    >
      <!-- Double page -->
      <div v-if="reader.mode === 'double' && nextPageUrl" class="reader-double">
        <img
          :key="'left-' + currentPageUrl"
          :src="currentPageUrl"
          class="reader-page-img"
          :style="[doublePageStyle, imageFilterStyle]"
          @error="$event.target.style.opacity='0.3'"
        />
        <img
          :key="'right-' + nextPageUrl"
          :src="nextPageUrl"
          class="reader-page-img"
          :style="[doublePageStyle, imageFilterStyle]"
          @error="$event.target.style.opacity='0.3'"
        />
      </div>
      <!-- Single page -->
      <img
        v-else
        ref="imgRef"
        :src="currentPageUrl"
        class="reader-page-single"
        :class="{ 'reader-page-panel-zoom': reader.panelMode }"
        :style="[singlePageStyle, imageFilterStyle]"
        @load="onImgLoad"
        @error="$event.target.style.opacity='0.3'"
      />

      <!-- Zoom sur les cases : assombrit tout sauf la case courante, pour que l'œil n'ait
           pas à se déplacer — le "trou" clair est positionné exactement sur son rectangle
           à l'écran (voir spotlightStyle), via un box-shadow surdimensionné plutôt qu'un
           calque à 4 pans, plus simple à garder synchronisé avec le rectangle qui bouge. -->
      <div v-if="reader.panelMode" class="reader-panel-spotlight" :style="spotlightStyle"></div>
    </div>

    <!-- Bottom nav — barre opaque toujours visible, comme la barre du haut. -->
    <div class="reader-toolbar reader-toolbar-bottom" @click.stop>
      <button
        @click="goPrevPanelOrPage()"
        :disabled="reader.currentPage === 0"
        class="reader-nav-btn"
        aria-label="Page précédente"
      >‹</button>

      <div class="reader-progress-group">
        <div
          ref="progressTrackRef"
          class="reader-progress-track"
          @mousedown="startSeek"
          @touchstart="onSeekTouchStart"
          @touchmove="onSeekTouchMove"
          @touchend="onSeekTouchEnd"
        >
          <div
            class="reader-progress-fill"
            :style="{ width: reader.pageCount ? `${((progressPage + 1) / reader.pageCount) * 100}%` : '0%' }"
          />
        </div>
        <span class="reader-page-info">{{ progressPage + 1 }} / {{ reader.pageCount }}</span>
      </div>

      <button
        @click="goNextPanelOrPage()"
        :disabled="reader.currentPage >= reader.pageCount - 1 && !nextTomeInfo"
        class="reader-nav-btn"
        aria-label="Page suivante"
      >›</button>
    </div>
  </div>
</template>

<style scoped>
.reader {
  position: fixed;
  inset: 0;
  background-color: var(--reader-bg);
  display: flex;
  flex-direction: column;
  user-select: none;
  /* Empêche le rebond élastique natif iOS Safari, complémentaire au verrouillage du scroll
     du body (voir onMounted) — sans ça, un tap avec un léger mouvement vertical peut encore
     déclencher un overscroll perceptible avant que touch-action ci-dessous ne s'applique. */
  overscroll-behavior: none;
}

/* Toolbar shared — barres opaques toujours visibles (style repris d'une capture d'écran
   fournie par l'utilisateur), en flux normal plutôt qu'en overlay position:absolute : plus
   besoin de disparaître pour ne pas gêner la lecture puisqu'elles ne recouvrent plus rien,
   la zone de pages (flex:1) se cale naturellement entre les deux. */
.reader-toolbar {
  flex: 0 0 auto;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  height: 56px;
  background: #12151c;
}

.reader-toolbar-top {
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

.reader-toolbar-bottom {
  height: 48px;
  border-top: 1px solid rgba(255,255,255,0.08);
  justify-content: center;
}

/* Back button */
.reader-btn {
  background: none;
  border: none;
  color: rgba(255,255,255,0.85);
  font-size: 1.4rem;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
  transition: color 0.15s;
}
.reader-btn:hover { color: #fff; }

/* Zone retour — flèche + titre réunis dans un seul bouton cliquable (avant : seule la
   flèche, beaucoup plus petite, ramenait en arrière). flex:1 pousse naturellement le reste
   de la barre (sélecteur de mode, zoom cases, plein écran) vers la droite, sans avoir besoin
   d'un séparateur dédié. */
.reader-back {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 6px 8px;
  margin: -6px -8px;
  border-radius: 8px;
  transition: background-color 0.15s;
}
.reader-back:hover { background-color: rgba(255,255,255,0.1); }
.reader-back-arrow {
  color: rgba(255,255,255,0.85);
  font-size: 1.5rem;
  line-height: 1;
  flex-shrink: 0;
}
.reader-title {
  min-width: 0;
  font-size: 0.875rem;
  color: rgba(255,255,255,0.8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

/* Sélecteur de mode — bouton bordé ouvrant un menu déroulant (icône + libellé + chevron),
   plutôt que 3 boutons toujours dépliés — style repris de la capture d'écran fournie
   (bordure visible au repos, pas seulement au survol). */
.reader-mode-dropdown { position: relative; flex-shrink: 0; }
.reader-dropdown-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.18);
  color: rgba(255,255,255,0.9);
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-family: var(--font);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
  transition: border-color 0.15s, background-color 0.15s;
}
.reader-dropdown-btn:hover, .reader-dropdown-btn-open {
  border-color: rgba(255,255,255,0.4);
  background: rgba(255,255,255,0.08);
}
.reader-dropdown-chevron { transition: transform 0.15s; flex-shrink: 0; }
.reader-dropdown-chevron-open { transform: rotate(180deg); }
.reader-dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 168px;
  background: #12151c;
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.5);
  padding: 6px;
  z-index: 20;
}
.reader-dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: none;
  border: none;
  color: rgba(255,255,255,0.75);
  font-family: var(--font);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 10px 10px;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s, color 0.15s;
}
.reader-dropdown-item:hover { background-color: rgba(255,255,255,0.08); }
.reader-dropdown-item-active {
  background-color: color-mix(in srgb, var(--vermilion) 22%, transparent);
  color: var(--vermilion);
}

/* Sur petit écran, la barre du haut n'a pas la place pour flèche + titre + le libellé du
   menu déroulant + icônes — icône seule pour le bouton du menu, toujours identifiable via
   son contenu au clic (les libellés restent dans le menu ouvert). */
@media (max-width: 640px) {
  .reader-dropdown-btn span { display: none; }
  .reader-title { font-size: 0.8125rem; }
}

/* Zoom cases / plein écran — boutons bordés (carrés), cible tactile confortable. */
.reader-icon-btn {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.18);
  color: rgba(255,255,255,0.8);
  cursor: pointer;
  width: 36px;
  height: 36px;
  padding: 0;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  flex-shrink: 0;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}
.reader-icon-btn:hover { color: #fff; border-color: rgba(255,255,255,0.4); background-color: rgba(255,255,255,0.08); }
.reader-mode-active {
  background-color: color-mix(in srgb, var(--vermilion) 22%, transparent);
  border-color: var(--vermilion);
  color: var(--vermilion);
}

/* Panneau de réglages d'image — même écrin que le menu déroulant du sélecteur de mode
   (.reader-dropdown-menu), aligné à droite plutôt qu'à gauche (bouton proche du bord droit
   de la barre). */
.reader-adjust-wrap { position: relative; flex-shrink: 0; }
.reader-adjust-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  width: 220px;
  background: #12151c;
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,0.5);
  padding: 14px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.reader-adjust-row { display: flex; flex-direction: column; gap: 6px; }
.reader-adjust-label { font-size: 0.75rem; font-weight: 600; color: rgba(255,255,255,0.85); }
.reader-adjust-slider { width: 100%; accent-color: var(--vermilion); cursor: pointer; }
.reader-adjust-value {
  align-self: flex-end;
  font-size: 0.7rem;
  font-family: var(--font-mono, inherit);
  color: rgba(255,255,255,0.55);
  margin-top: -4px;
}
.reader-adjust-sep { height: 1px; background: rgba(255,255,255,0.1); }
.reader-adjust-reset {
  background: none;
  border: 1px solid rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.8);
  font-size: 0.78rem;
  font-weight: 600;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.reader-adjust-reset:hover { border-color: var(--vermilion); color: var(--vermilion); }

/* Ajustement + zoom fusionnés — le libellé cliquable (Largeur/Hauteur) et le curseur
   partagent un même bloc visuel plutôt qu'un bouton séparé + un groupe à part, comme sur la
   capture d'écran fournie. Largeur du curseur volontairement contenue : réglage secondaire,
   ne doit pas rivaliser avec le sélecteur de mode pour la place disponible. */
.reader-zoom-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.reader-fit-label {
  background: none;
  border: none;
  color: #fff;
  font-family: var(--font);
  font-size: 0.8125rem;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
  transition: color 0.15s;
}
.reader-fit-label:hover { color: var(--vermilion); }
.reader-zoom-slider {
  width: 100px;
  accent-color: var(--vermilion);
  cursor: pointer;
}
.reader-zoom-value {
  font-size: 0.8125rem;
  font-weight: 700;
  font-family: var(--font-mono, inherit);
  color: var(--vermilion);
  width: 38px;
  flex-shrink: 0;
  text-align: left;
}
@media (max-width: 640px) {
  .reader-zoom-slider { width: 70px; }
}

/* Compteur de pages — désormais dans la barre du bas, à côté de la progression, plutôt
   qu'isolé entre deux boutons d'action dans la barre du haut. */
.reader-page-info {
  font-size: 0.8125rem;
  font-family: var(--font-mono, inherit);
  color: rgba(255,255,255,0.6);
  white-space: nowrap;
  flex-shrink: 0;
}

/* Loading */
.reader-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255,255,255,0.4);
  font-size: 0.9rem;
}

/* Pages area */
.reader-pages {
  flex: 1;
  position: relative;
  display: flex;
  /* "safe" (mot-clé CSS Box Alignment) : centre normalement, mais bascule sur un alignement
     "start" dès que le contenu déborde plutôt que de continuer à centrer — sans lui, un
     centrage classique laisse la moitié du débordement à un scroll NÉGATIF (haut/gauche),
     donc inatteignable : zoomée, l'image restait tronquée en haut sans façon d'y remonter. */
  align-items: safe center;
  justify-content: safe center;
  /* auto (pas hidden) : reader.zoom (piloté par le pincement trackpad/Ctrl+molette ou le
     curseur de la barre du haut) agrandit RÉELLEMENT l'image sur l'axe cadré par reader.fit
     (width % en ajustement largeur, height % en ajustement hauteur — voir singlePageStyle/
     doublePageStyle), pas un transform — sans rien à faire défiler tant qu'elle tient dans le
     cadre (zoom=1), auto se comporte exactement comme hidden ; une fois zoomée au-delà, le
     défilement natif (glisser à deux doigts sur le trackpad, sans Ctrl) permet de se déplacer
     dans l'image, dans les deux sens grâce à "safe" ci-dessus. */
  overflow: auto;
  /* Empêche le scroll de cette zone de "chaîner" vers le body une fois arrivé en haut/bas/
     gauche/droite (comportement natif iOS Safari) — sans ça, continuer à tirer une fois en
     butée fait bouger toute la page derrière le lecteur malgré position:fixed. */
  overscroll-behavior: contain;
  /* Bloque le déplacement au doigt sur écran tactile (qui pouvait déclencher un léger rebond/
     déplacement perceptible sur un simple tap, voir overscroll-behavior sur .reader) tout en
     gardant le pincer-zoomer natif utilisable pour examiner le détail d'une planche — le
     vrai déplacement dans une image zoomée (reader.zoom) se fait par la molette/le trackpad
     (déjà couvert), pas par ce chemin tactile. */
  touch-action: pinch-zoom;
}

.reader-double {
  display: flex;
  height: 100%;
  gap: 2px;
}

.reader-page-img {
  height: 100%;
  /* Sans min-width:0, un item flex ne réduit jamais en dessous de la largeur intrinsèque de
     son contenu — deux pages pleine hauteur côte à côte débordent alors largement d'un écran
     étroit sans pouvoir rétrécir en dessous. */
  min-width: 0;
  max-width: 50%;
  object-fit: contain;
}

.reader-page-single {
  max-height: 100%;
  max-width: 100%;
  object-fit: contain;
}
/* Zoom sur les cases : la case courante est cadrée par un simple transform CSS sur
   l'image déjà chargée (transform-origin/scale calculés dans panelStyle, voir script) —
   pas de recadrage serveur ni de rechargement d'image entre deux cases. Volontairement
   sans transition : le passage d'une case à l'autre doit être un saut instantané, pas un
   glissement visible (choix explicite de l'utilisateur). */
.reader-page-panel-zoom {
}

/* Rectangle transparent dont le box-shadow (surdimensionné, coupé par overflow:hidden sur
   .reader-pages) assombrit tout l'espace autour — la case elle-même, à l'intérieur du
   rectangle, reste intacte. Pas de transition non plus, même raison que ci-dessus. */
.reader-panel-spotlight {
  position: absolute;
  z-index: 2;
  pointer-events: none;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.82);
}

/* Bottom nav — boutons bordés (même langage visuel que .reader-icon-btn), cohérents entre
   eux : les deux passent par goPrevPanelOrPage/goNextPanelOrPage (avant, seul le bouton
   suivant tenait compte du zoom sur les cases). */
.reader-nav-btn {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.18);
  color: rgba(255,255,255,0.8);
  font-size: 1.4rem;
  cursor: pointer;
  width: 36px;
  height: 36px;
  padding: 0;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  flex-shrink: 0;
  transition: color 0.15s, border-color 0.15s, background-color 0.15s;
}
.reader-nav-btn:hover:not(:disabled) { color: #fff; border-color: rgba(255,255,255,0.4); background-color: rgba(255,255,255,0.08); }
.reader-nav-btn:disabled { opacity: 0.25; cursor: default; }

/* Compteur de pages regroupé avec la barre de progression — un seul repère "où j'en suis"
   au lieu de deux informations dispersées entre les deux barres. */
.reader-progress-group {
  flex: 1;
  max-width: 320px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.reader-progress-track {
  flex: 1;
  height: 4px;
  /* Padding transparent (background-clip: content-box) : élargit la zone cliquable/glissable
     sans épaissir visuellement la barre — plus confortable au doigt comme à la souris.
     box-sizing: content-box nécessaire ici : le reset global (border-box) ferait sinon
     rentrer ce padding DANS les 4px de height, écrasant la zone de contenu (donc la barre
     visible) à 0. */
  box-sizing: content-box;
  padding: 10px 0;
  background: rgba(255,255,255,0.2);
  background-clip: content-box;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  touch-action: none;
}
.reader-progress-fill {
  height: 100%;
  background: var(--vermilion);
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* Mode Défilement — les images sont empilées en flux normal (display:block), pas besoin de
   flex/centrage sur le conteneur lui-même. overflow-x: auto (pas hidden) : reader.zoom
   élargit réellement chaque image (width en inline, piloté par onWheel/le curseur du menu
   "Plus d'options") — la largeur/hauteur réelles de défilement (scrollHeight, offsetTop
   utilisé par scrollToPage) restent donc exactes même zoomé, pas de recalage à prévoir. */
.reader-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  touch-action: pan-x pan-y pinch-zoom;
  overscroll-behavior: contain;
}
/* margin: 0 auto (pas un centrage flex du parent) : une marge automatique ne peut jamais
   devenir négative — tant que l'image tient dans le cadre (zoom=1, largeur=100%), elle est
   centrée normalement ; dès qu'elle devient plus large que le cadre (zoomée), la marge
   retombe à 0 des deux côtés et l'image démarre au bord gauche, débordant uniquement vers la
   droite — un centrage flex aurait laissé la moitié du débordement à gauche, à un scrollLeft
   négatif donc inatteignable en LTR. */
.reader-scroll-img {
  height: auto;
  display: block;
  margin: 0 auto;
}

/* Bandeau de reprise — non bloquant, flotte au-dessus de la zone de lecture (jamais de
   backdrop ni de Teleport : la lecture démarre déjà à la bonne page, ce bandeau n'est
   qu'informatif). Centré sous la barre du haut (56px + marge). */
.resume-banner {
  position: absolute;
  top: 68px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 15;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(18,21,28,0.95);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 10px;
  padding: 9px 10px 9px 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
/* Action principale du bandeau (pas juste secondaire : c'est la seule action utile, fermer
   sans cliquer revient à démarrer du début). Fond plein plutôt qu'un simple contour. */
.resume-banner-action {
  background: var(--vermilion);
  border: none;
  color: #fff;
  font-size: 0.8125rem;
  font-weight: 700;
  padding: 7px 14px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: filter 0.15s;
}
.resume-banner-action:hover { filter: brightness(1.1); }
.resume-banner-close {
  background: none;
  border: none;
  color: rgba(255,255,255,0.5);
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
  padding: 2px 4px;
  transition: color 0.15s;
}
.resume-banner-close:hover { color: #fff; }
.resume-banner-fade-enter-active, .resume-banner-fade-leave-active { transition: opacity 0.25s, transform 0.25s; }
.resume-banner-fade-enter-from, .resume-banner-fade-leave-to { opacity: 0; transform: translate(-50%, -8px); }

/* Resume dialog (classes encore utilisées par la popup "Tome suivant" ci-dessous). */
.resume-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center;
}
.resume-dialog {
  background: var(--surface-raised); border-radius: var(--radius);
  padding: 28px 32px; text-align: center;
  box-shadow: 0 8px 32px rgba(0,0,0,0.25);
  min-width: 260px;
}
.resume-title { font-size: 1rem; font-weight: 700; margin-bottom: 6px; }
.resume-sub { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.resume-actions { display: flex; gap: 10px; justify-content: center; }

/* Tome suivant — même boîte que .resume-dialog, avec la cover du tome suivant au-dessus. */
.next-tome-dialog { min-width: 220px; max-width: 260px; }
.next-tome-cover {
  width: 140px; aspect-ratio: 0.71; object-fit: cover;
  border-radius: var(--radius-sm); box-shadow: 0 6px 18px rgba(0,0,0,0.3);
  margin: 0 auto 16px; display: block;
}
</style>
