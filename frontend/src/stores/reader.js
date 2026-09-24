import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import client from '../api/client'
import { tomesApi } from '../api/tomes'

export const useReaderStore = defineStore('reader', () => {
  const tomeId = ref(null)
  const tomeInfo = ref(null)
  const currentPage = ref(0)
  const savedPage = ref(0)
  const mode = ref('single') // 'single' | 'double' | 'vertical'
  // Quel axe est cadré à 100% du cadre par défaut : 'width' (défilement vertical naturel,
  // horizontal seulement si zoomé) ou 'height' (page entière visible sans défiler, tant
  // qu'on n'a pas zoomé). Défaut 'height' : voir la page entière dès l'ouverture. Le zoom
  // (voir setZoom) s'applique toujours sur cet axe, quel qu'il soit — voir
  // ReaderView.vue::singlePageStyle.
  const fit = ref('height')
  const zoom = ref(1.0)
  const showToolbar = ref(true)

  // Réglages d'image (panneau "baguette magique", voir ReaderView.vue) — appliqués en CSS
  // filter sur les pages, jamais persistés : repartent à 0 à chaque nouvel album (voir
  // loadTome), comme le zoom. Un réglage propre à un scan particulier (trop sombre, jauni...)
  // n'a pas de raison de s'appliquer silencieusement à l'album suivant.
  const brightness = ref(100)   // 50-150 %
  const contrast = ref(100)     // 50-150 %
  const saturation = ref(100)   // 0-200 %
  // Netteté — 0 = aucun effet (pas de filtre appliqué, voir ReaderView.vue::imageFilterStyle),
  // jusqu'à 100 = renforcement de contours maximal. Piloté par un feConvolveMatrix SVG (vrai
  // noyau de convolution, pas juste un CSS filter — CSS n'a pas de fonction "sharpen" native).
  const sharpness = ref(0)
  function setBrightness(v) { brightness.value = Math.max(50, Math.min(150, v)) }
  function setContrast(v) { contrast.value = Math.max(50, Math.min(150, v)) }
  function setSaturation(v) { saturation.value = Math.max(0, Math.min(200, v)) }
  function setSharpness(v) { sharpness.value = Math.max(0, Math.min(100, v)) }
  function resetImageAdjustments() {
    brightness.value = 100
    contrast.value = 100
    saturation.value = 100
    sharpness.value = 0
  }

  // Option "Zoom sur les cases" (désactivée par défaut) — préférence gardée d'une session à
  // l'autre une fois activée, comme le thème sombre/clair.
  const panelMode = ref(localStorage.getItem('cmw-panel-mode') === '1')
  function setPanelMode(v) {
    panelMode.value = v
    localStorage.setItem('cmw-panel-mode', v ? '1' : '0')
    if (v) mode.value = 'single' // incompatible avec la double page
  }

  const pageCount = computed(() => tomeInfo.value?.page_count ?? 0)
  const title = computed(() => tomeInfo.value?.title ?? '')
  const hasSavedProgress = computed(() => savedPage.value > 0)
  const loadError = ref(false)

  function pageUrl(id, index) {
    return `/api/reader/${id}/page/${index}`
  }

  async function fetchPanels(id, index) {
    const { data } = await client.get(`/api/reader/${id}/panels/${index}`)
    return data.panels
  }

  let _saveTimer = null

  async function loadTome(id) {
    // Cancel any pending save from the previous tome — otherwise it fires after the
    // switch and overwrites the new tome's progress with the old page number.
    clearTimeout(_saveTimer)
    tomeId.value = id
    currentPage.value = 0
    savedPage.value = 0
    tomeInfo.value = null
    loadError.value = false
    zoom.value = 1.0 // repart net à chaque nouvel album (voir ReaderView.vue::onWheel)
    resetImageAdjustments()
    try {
      const [infoRes, progressRes] = await Promise.all([
        client.get(`/api/reader/${id}/info`),
        tomesApi.getProgress(id),
      ])
      // Une navigation plus récente (loadTome appelé à nouveau avec un autre id avant que
      // CES réponses n'arrivent — ex. avance rapide vers le tome suivant) a pu changer
      // tomeId entre-temps : ignorer une réponse devenue obsolète plutôt que d'écraser les
      // données du tome ACTUELLEMENT affiché avec celles d'un tome qu'on a déjà quitté.
      if (tomeId.value !== id) return
      tomeInfo.value = infoRes.data
      // Un album marqué Lu repart toujours de 0 plutôt que de proposer de reprendre près de
      // la fin (voir TomeDetailView.vue::toggleRead) — savedPage à 0 fait que
      // hasSavedProgress est faux, donc ReaderView.vue n'affiche même pas la boîte de
      // dialogue "reprendre ?", on démarre directement page 1.
      savedPage.value = progressRes.data.is_read ? 0 : (progressRes.data.last_page ?? 0)
    } catch {
      if (tomeId.value === id) loadError.value = true
    }
  }

  function resumeFromSaved() {
    currentPage.value = savedPage.value
  }

  function _scheduleSave() {
    if (!tomeId.value) return
    clearTimeout(_saveTimer)
    _saveTimer = setTimeout(() => {
      tomesApi.saveProgress(tomeId.value, currentPage.value)
    }, 500)
  }

  // Mode double : la couverture (page 0) s'affiche seule (voir ReaderView.vue::doubleLeftPage
  // pour le calcul d'affichage correspondant), les paires suivantes sont (1,2), (3,4), etc.
  // Le pas n'est donc de 2 qu'à partir de la page 1 — avancer depuis la couverture ne saute
  // qu'une seule page, pour atterrir sur la première paire plutôt que de la sauter.
  function nextPage() {
    const step = (mode.value === 'double' && currentPage.value > 0) ? 2 : 1
    const max = pageCount.value - 1
    currentPage.value = Math.min(currentPage.value + step, max)
    _scheduleSave()
  }

  function prevPage() {
    const step = (mode.value === 'double' && currentPage.value > 1) ? 2 : 1
    currentPage.value = Math.max(currentPage.value - step, 0)
    _scheduleSave()
  }

  function goToPage(index) {
    const max = pageCount.value - 1
    currentPage.value = Math.max(0, Math.min(index, max))
    _scheduleSave()
  }

  function setMode(m) {
    mode.value = m
    // Le zoom sur les cases suppose une page unique cadrée à l'écran — incompatible avec le
    // défilement continu (pas de "case courante" au sens où l'entend son calcul de cadrage).
    // Runtime seul (pas touché en localStorage) : si l'utilisateur repasse en mode Page, sa
    // préférence panel-zoom d'avant peut se réappliquer plutôt que d'être perdue pour de bon.
    if (m === 'vertical') panelMode.value = false
  }
  function cycleMode() {
    setMode(mode.value === 'single' ? 'double' : mode.value === 'double' ? 'vertical' : 'single')
  }
  function setFit(f) { fit.value = f }
  // Plage 1×-2.5× : au-delà, l'image devient plus grande que ce qu'un écran/trackpad permet de
  // parcourir confortablement. Actif sur l'axe cadré par `fit`, quel qu'il soit (largeur ou
  // hauteur) — voir ReaderView.vue::singlePageStyle.
  function setZoom(z) { zoom.value = Math.max(1, Math.min(2.5, z)) }
  function toggleToolbar() { showToolbar.value = !showToolbar.value }

  return {
    tomeId, tomeInfo, currentPage, savedPage, mode, fit, zoom, showToolbar, panelMode,
    brightness, contrast, saturation, sharpness,
    pageCount, title, hasSavedProgress, loadError, pageUrl, fetchPanels,
    loadTome, resumeFromSaved, nextPage, prevPage, goToPage, setMode, cycleMode, setFit, setZoom, toggleToolbar, setPanelMode,
    setBrightness, setContrast, setSaturation, setSharpness, resetImageAdjustments,
  }
})
