<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/layout/AppLayout.vue'
import client from '../api/client'
import { tomesApi } from '../api/tomes'
import { CountUp } from 'countup.js'

const router = useRouter()

const stats = ref(null)
const loading = ref(true)
const error = ref(false)

// ── Onglet "Bibliothèque" (partagée) / "Ma lecture" (personnelle) ──────────
const activeTab = ref('library')
const myStats = ref(null)
const myLoading = ref(true)
const myError = ref(false)
const inProgress = ref([])

const refSeriesCount = ref(null)
const refTomeCount   = ref(null)
const refTotalPages  = ref(null)
const refAvgPages    = ref(null)

function initCounters() {
  const items = [
    { el: refSeriesCount.value, val: stats.value.series_count },
    { el: refTomeCount.value,   val: stats.value.tome_count },
    { el: refTotalPages.value,  val: stats.value.total_pages ?? 0 },
    { el: refAvgPages.value,    val: stats.value.avg_pages ?? 0 },
  ]
  items.forEach(({ el, val }, i) => {
    if (!el || !val) return
    new CountUp(el, val, { duration: 1.2 + i * 0.1, useEasing: true, separator: '\u00a0' }).start()
  })
}

const chartsReady = ref(false)
const animatedHeights = ref([])

function animateBars() {
  const targets = yearBars.value.map(b => b.h)
  animatedHeights.value = targets.map(() => 0)
  const duration = 700
  const stagger = 12  // ms entre chaque barre
  targets.forEach((target, i) => {
    const start = performance.now() + i * stagger
    function step(now) {
      if (now < start) { requestAnimationFrame(step); return }
      const t = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      animatedHeights.value[i] = target * ease
      if (t < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  })
}

const animatedRatingHeights = ref([])

function animateRatingBars() {
  const targets = ratingBars.value.map(b => b.h)
  animatedRatingHeights.value = targets.map(() => 0)
  const duration = 700
  const stagger = 40
  targets.forEach((target, i) => {
    const start = performance.now() + i * stagger
    function step(now) {
      if (now < start) { requestAnimationFrame(step); return }
      const t = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      animatedRatingHeights.value[i] = target * ease
      if (t < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  })
}

watch(stats, async (val) => {
  if (!val) return
  await nextTick()
  initCounters()
  setTimeout(() => { chartsReady.value = true }, 50)
  animateBars()
})

const myChartsReady = ref(false)
watch(myStats, async (val) => {
  if (!val) return
  await nextTick()
  setTimeout(() => { myChartsReady.value = true }, 50)
  animateRatingBars()
})

onMounted(async () => {
  try {
    const { data } = await client.get('/api/stats')
    stats.value = data
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
  try {
    const [{ data: mine }, { data: ip }] = await Promise.all([
      client.get('/api/stats/me'),
      tomesApi.getInProgress(),
    ])
    myStats.value = mine
    inProgress.value = ip
  } catch {
    myError.value = true
  } finally {
    myLoading.value = false
  }
})

// ── Helpers ──────────────────────────────────────────────────────────────

function formatSize(bytes) {
  if (!bytes) return '0 o'
  if (bytes < 1024) return bytes + ' o'
  if (bytes < 1024 ** 2) return (bytes / 1024).toFixed(0) + ' Ko'
  if (bytes < 1024 ** 3) return (bytes / 1024 ** 2).toFixed(1) + ' Mo'
  return (bytes / 1024 ** 3).toFixed(2) + ' Go'
}

// Valeur et unité séparées pour les KPI de taille — l'unité (Go/Mo) affichée en plus petit
// pour mettre en valeur le chiffre, plutôt que le même poids visuel que "12,3 Go" en bloc.
function sizeParts(bytes) {
  const full = formatSize(bytes)
  const i = full.lastIndexOf(' ')
  return { value: full.slice(0, i), unit: full.slice(i + 1) }
}

// Temps de lecture (ReadingActivity.seconds) → "3 h 24 min" / "24 min" / "0 min" — jamais les
// secondes elles-mêmes, sans intérêt à l'affichage à cette échelle.
function formatDuration(seconds) {
  const totalMin = Math.round((seconds || 0) / 60)
  const h = Math.floor(totalMin / 60)
  const min = totalMin % 60
  if (h === 0) return `${min} min`
  return `${h} h ${String(min).padStart(2, '0')} min`
}
function durationParts(seconds) {
  const full = formatDuration(seconds)
  const i = full.lastIndexOf(' ')
  return { value: full.slice(0, i), unit: full.slice(i + 1) }
}

// ── Graphique barres (albums par année) ──────────────────────────────────
const BAR_W = 600
const BAR_H = 180
const BAR_PAD = { top: 10, right: 10, bottom: 30, left: 36 }

const yearBars = computed(() => {
  if (!stats.value?.by_year?.length) return []
  const data = stats.value.by_year
  const maxVal = Math.max(...data.map(d => d.count))
  const innerW = BAR_W - BAR_PAD.left - BAR_PAD.right
  const innerH = BAR_H - BAR_PAD.top - BAR_PAD.bottom
  const bw = Math.max(2, Math.floor(innerW / data.length) - 1)
  return data.map((d, i) => {
    const h = Math.round((d.count / maxVal) * innerH)
    const x = BAR_PAD.left + i * (innerW / data.length)
    const y = BAR_PAD.top + innerH - h
    return { x, y, w: bw, h, label: d.year, count: d.count }
  })
})

const yearAxisY = computed(() => {
  if (!stats.value?.by_year?.length) return []
  const maxVal = Math.max(...stats.value.by_year.map(d => d.count))
  const innerH = BAR_H - BAR_PAD.top - BAR_PAD.bottom
  const ticks = 4
  return Array.from({ length: ticks + 1 }, (_, i) => {
    const val = Math.round((maxVal * i) / ticks)
    const y = BAR_PAD.top + innerH - Math.round((val / maxVal) * innerH)
    return { val, y }
  })
})

// Labels d'années : n'afficher que tous les ~5 ans pour éviter le chevauchement
const yearLabels = computed(() => {
  if (!yearBars.value.length) return []
  const step = Math.ceil(yearBars.value.length / 12)
  return yearBars.value.filter((_, i) => i % step === 0)
})

// ── Activité de lecture, 30 derniers jours (myStats.activity_by_day) ──────
// Rangée de petites barres colorées par intensité plutôt qu'un histogramme à hauteur
// variable — repris d'une capture d'esprit "moniteur de disponibilité" (UptimeRobot/
// Statuspage : une barre par jour, hauteur uniforme, la couleur seule porte l'information).
// 5 paliers (0 = aucune activité, 1 à 4 = quarts de l'intensité max sur la fenêtre) plutôt
// qu'un dégradé continu — plus lisible en un coup d'œil, comme la grille de contributions
// GitHub.
const activityBlocks = computed(() => {
  const data = myStats.value?.activity_by_day
  if (!data?.length) return []
  const maxSeconds = Math.max(1, ...data.map(d => d.seconds))
  return data.map(d => {
    const ratio = d.seconds / maxSeconds
    let level = 0
    if (d.seconds > 0) level = ratio > 0.75 ? 4 : ratio > 0.5 ? 3 : ratio > 0.25 ? 2 : 1
    const minutes = Math.round(d.seconds / 60)
    // "12/09" plutôt que la date ISO complète — assez pour situer le jour dans l'infobulle,
    // sans avoir à caser l'année qui ne varie jamais sur une fenêtre de 30 jours.
    const label = d.day.slice(8, 10) + '/' + d.day.slice(5, 7)
    return { day: d.day, label, minutes, level }
  })
})
const hasActivity = computed(() => (myStats.value?.activity_by_day || []).some(d => d.seconds > 0))

// ── Camemberts ───────────────────────────────────────────────────────────
const PIE_R = 70
const PIE_CX = 90
const PIE_CY = 90
const PIE_CIRC = 2 * Math.PI * PIE_R

// Palette qualitative "Affiche" — tons chauds/terreux cohérents avec navy/vermillon/ochre
// plutôt que des couleurs web saturées par défaut.
const COLORS = [
  '#D9411E','#4A6C93','#E9C46A','#6B8F71','#8A5A44',
  '#5B7C99','#B5651D','#7A6C8F','#4A7268','#A67B5B',
]

function calcSlices(items, r) {
  if (!items?.length) return []
  const total = items.reduce((s, d) => s + d.count, 0)
  // Cas 1 seul item : arc 360° dégénéré en SVG → deux demi-arcs
  if (items.length === 1) {
    const d = items[0]
    return [{
      d: `M ${PIE_CX} ${PIE_CY - r} A ${r} ${r} 0 1 1 ${PIE_CX - 0.01} ${PIE_CY - r} Z`,
      color: COLORS[0],
      name: d.name || d.lang || d.format,
      count: d.count,
      pct: 100,
    }]
  }
  let angle = -Math.PI / 2
  return items.map((d, i) => {
    const sweep = (d.count / total) * 2 * Math.PI
    const x1 = PIE_CX + r * Math.cos(angle)
    const y1 = PIE_CY + r * Math.sin(angle)
    angle += sweep
    const x2 = PIE_CX + r * Math.cos(angle)
    const y2 = PIE_CY + r * Math.sin(angle)
    const large = sweep > Math.PI ? 1 : 0
    return {
      d: `M ${PIE_CX} ${PIE_CY} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`,
      color: COLORS[i % COLORS.length],
      name: d.name || d.lang || d.format,
      count: d.count,
      pct: Math.round((d.count / total) * 100),
    }
  })
}

const pubSlices = computed(() => calcSlices(stats.value?.publishers, PIE_R))
const STATUS_COLORS = { 'En cours': '#2e7d32', 'Terminées': '#4A6C93', 'Statut inconnu': '#bdbdbd' }
const statusSlices = computed(() => {
  const items = (stats.value?.series_status || []).filter(s => s.count > 0)
  return calcSlices(items, PIE_R).map(s => ({ ...s, color: STATUS_COLORS[s.name] || s.color }))
})

// ── Genres (treemap) ───────────────────────────────────────────────────
// Algorithme "squarified treemap" (Bruls/Huizing/van Wijk) : découpe la surface en bandes
// horizontales ou verticales en ajoutant les éléments un à un tant que ça ne dégrade pas le
// ratio largeur/hauteur (le "worst" ci-dessous) du pire rectangle de la bande — ce qui donne
// des blocs proches du carré plutôt que des lamelles très étirées.
function treemapWorst(rowAreas, length) {
  let max = -Infinity, min = Infinity, sum = 0
  for (const a of rowAreas) { if (a > max) max = a; if (a < min) min = a; sum += a }
  const lenSq = length * length
  const sumSq = sum * sum
  return Math.max((lenSq * max) / sumSq, sumSq / (lenSq * min))
}
function treemapLayoutRow(row, x, y, w, h) {
  const rowSum = row.reduce((s, r) => s + r.area, 0)
  const rects = []
  if (w >= h) {
    const colW = h > 0 ? rowSum / h : 0
    let cy = y
    for (const r of row) {
      const itH = rowSum > 0 ? (r.area / rowSum) * h : 0
      rects.push({ item: r.item, x, y: cy, w: colW, h: itH })
      cy += itH
    }
    return [rects, { x: x + colW, y, w: w - colW, h }]
  }
  const rowH = w > 0 ? rowSum / w : 0
  let cx = x
  for (const r of row) {
    const itW = rowSum > 0 ? (r.area / rowSum) * w : 0
    rects.push({ item: r.item, x: cx, y, w: itW, h: rowH })
    cx += itW
  }
  return [rects, { x, y: y + rowH, w, h: h - rowH }]
}
function squarify(items, x, y, w, h) {
  let remaining = items.slice()
  let container = { x, y, w, h }
  const allRects = []
  let row = []
  while (remaining.length) {
    const length = Math.min(container.w, container.h)
    const next = remaining[0]
    const rowAreas = row.map(r => r.area)
    const withNext = [...rowAreas, next.area]
    if (row.length === 0 || treemapWorst(rowAreas, length) >= treemapWorst(withNext, length)) {
      row.push(next)
      remaining = remaining.slice(1)
    } else {
      const [rects, rest] = treemapLayoutRow(row, container.x, container.y, container.w, container.h)
      allRects.push(...rects)
      container = rest
      row = []
    }
  }
  if (row.length) {
    const [rects] = treemapLayoutRow(row, container.x, container.y, container.w, container.h)
    allRects.push(...rects)
  }
  return allRects
}
// Tronque le libellé selon la largeur réellement disponible dans le bloc plutôt qu'un nombre
// de caractères fixe — un genre court dans un grand bloc s'affiche en entier, un genre long
// dans un petit bloc est coupé avec une ellipse, comme sur la maquette fournie.
function treemapLabel(name, w, fontSize) {
  const avgChar = fontSize * 0.56
  const maxChars = Math.floor((w - 10) / avgChar)
  if (maxChars < 1) return ''
  if (name.length <= maxChars) return name
  if (maxChars <= 1) return name.slice(0, 1)
  return name.slice(0, maxChars - 1) + '…'
}

const TREEMAP_W = 1000
const TREEMAP_H = 360
const genreTreemap = computed(() => {
  const genres = stats.value?.genres || []
  const total = genres.reduce((s, g) => s + g.count, 0)
  if (!total) return []
  const items = genres.map(g => ({ item: g, area: (g.count / total) * (TREEMAP_W * TREEMAP_H) }))
  const rects = squarify(items, 0, 0, TREEMAP_W, TREEMAP_H)
  return rects.map((r, i) => {
    const pct = Math.round((r.item.count / total) * 1000) / 10
    const showTwoLines = r.w >= 50 && r.h >= 34
    const showOneLine = !showTwoLines && r.w >= 34 && r.h >= 18
    return {
      ...r,
      color: COLORS[i % COLORS.length],
      pct,
      nameLabel: (showTwoLines || showOneLine) ? treemapLabel(r.item.name, r.w, 14) : '',
      statLabel: showTwoLines ? treemapLabel(`${r.item.count} (${pct}%)`, r.w, 11) : '',
    }
  })
})

// ── Répartition des notes personnelles (1 à 5 étoiles) ────────────────────
const RATING_BAR_W = 300
const RATING_BAR_H = 160
const RATING_BAR_PAD = { top: 10, right: 10, bottom: 24, left: 30 }

const hasRatings = computed(() => (myStats.value?.ratings_distribution || []).some(r => r.count > 0))

const ratingBars = computed(() => {
  const data = myStats.value?.ratings_distribution
  if (!data?.length) return []
  const maxVal = Math.max(1, ...data.map(d => d.count))
  const innerW = RATING_BAR_W - RATING_BAR_PAD.left - RATING_BAR_PAD.right
  const innerH = RATING_BAR_H - RATING_BAR_PAD.top - RATING_BAR_PAD.bottom
  const bw = Math.floor(innerW / data.length) - 10
  return data.map((d, i) => {
    const h = Math.round((d.count / maxVal) * innerH)
    const x = RATING_BAR_PAD.left + i * (innerW / data.length) + 5
    const y = RATING_BAR_PAD.top + innerH - h
    return { x, y, w: bw, h, label: `${d.stars} ★`, count: d.count }
  })
})

const ratingAxisY = computed(() => {
  const data = myStats.value?.ratings_distribution
  if (!data?.length) return []
  const maxVal = Math.max(1, ...data.map(d => d.count))
  const innerH = RATING_BAR_H - RATING_BAR_PAD.top - RATING_BAR_PAD.bottom
  const ticks = Math.min(4, maxVal)
  return Array.from({ length: ticks + 1 }, (_, i) => {
    const val = Math.round((maxVal * i) / ticks)
    const y = RATING_BAR_PAD.top + innerH - Math.round((val / maxVal) * innerH)
    return { val, y }
  })
})

// ── Barres horizontales (top séries / scénaristes) ───────────────────────
function hbarPct(items) {
  if (!items?.length) return []
  const max = Math.max(...items.map(d => d.count))
  return items.map(d => ({ ...d, pct: Math.round((d.count / max) * 100) }))
}
const top10 = computed(() => hbarPct(stats.value?.top10_series))
const topWriters = computed(() => hbarPct(stats.value?.writers))
const topPencillers = computed(() => hbarPct(stats.value?.pencillers))
// Même donnée que le camembert Éditeurs (stats.value.publishers), en liste classée pour
// compléter les 3 tops existants à 4 — permet une grille 2 colonnes propre sur mobile.
const topPublishers = computed(() => hbarPct((stats.value?.publishers || []).slice(0, 10)))

// Genres des albums LUS par l'utilisateur (myStats.by_genre) — même barre horizontale que
// les tops ci-dessus, avec en plus le temps de lecture cumulé pour ce genre à côté du
// nombre d'albums (0 si aucune session n'a encore été enregistrée pour ces albums-là).
const myGenreBars = computed(() => hbarPct(
  (myStats.value?.by_genre || []).slice(0, 10).map(g => ({ name: g.name, count: g.read_count, seconds: g.seconds }))
))
</script>

<template>
  <AppLayout>
    <main class="stats-main">
      <h1 class="stats-title">Statistiques</h1>

      <div class="tabs-row">
        <button @click="activeTab = 'library'" :class="['tab-btn', { 'tab-btn-active': activeTab === 'library' }]">Bibliothèque</button>
        <button @click="activeTab = 'mine'" :class="['tab-btn', { 'tab-btn-active': activeTab === 'mine' }]">Ma lecture</button>
      </div>

      <template v-if="activeTab === 'library'">
      <div v-if="loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
      </div>

      <div v-else-if="error" class="state-box">
        <span>Impossible de charger les statistiques.</span>
      </div>

      <template v-else-if="stats">

        <!-- ── KPIs ── -->
        <div class="kpi-grid">
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p ref="refSeriesCount" class="kpi-value">0</p>
            <p class="kpi-label">Séries</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p ref="refTomeCount" class="kpi-value">0</p>
            <p class="kpi-label">Albums</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p class="kpi-value">{{ sizeParts(stats.total_size).value }}<span class="kpi-unit">{{ sizeParts(stats.total_size).unit }}</span></p>
            <p class="kpi-label">Taille totale</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p class="kpi-value">{{ sizeParts(stats.avg_size).value }}<span class="kpi-unit">{{ sizeParts(stats.avg_size).unit }}</span></p>
            <p class="kpi-label">Taille moyenne / album</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p ref="refTotalPages" class="kpi-value">0</p>
            <p class="kpi-label">Pages totales</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p ref="refAvgPages" class="kpi-value">0</p>
            <p class="kpi-label">Pages moyennes / album</p>
          </div>
          <div v-if="stats.complete_series_pct !== null" class="kpi-card card">
            <div class="kpi-accent"></div>
            <p class="kpi-value">{{ stats.complete_series_pct }}<span class="kpi-unit">%</span></p>
            <p class="kpi-label">Séries complètes</p>
          </div>
        </div>

        <!-- ── Albums par année ── -->
        <div class="card chart-card" v-if="stats.by_year?.length">
          <div class="chart-header">
            <h2 class="chart-title">Albums par année d'édition</h2>
            <span class="chart-sub">{{ stats.by_year.length }} années</span>
          </div>
          <div class="chart-body chart-overflow">
            <svg :viewBox="`0 0 ${BAR_W} ${BAR_H}`" class="bar-svg">
              <!-- Grid lines -->
              <line v-for="tick in yearAxisY" :key="tick.val"
                :x1="BAR_PAD.left" :y1="tick.y" :x2="BAR_W - BAR_PAD.right" :y2="tick.y"
                stroke="#e0e0e0" stroke-width="1" />
              <!-- Y axis labels -->
              <text v-for="tick in yearAxisY" :key="'y'+tick.val"
                :x="BAR_PAD.left - 4" :y="tick.y + 4"
                text-anchor="end" font-size="9" fill="#9e9e9e">{{ tick.val }}</text>
              <!-- Bars animées via animatedHeights JS -->
              <rect
                v-for="(b, i) in yearBars" :key="b.label"
                :x="b.x"
                :y="b.y + b.h - (animatedHeights[i] ?? 0)"
                :width="b.w"
                :height="animatedHeights[i] ?? 0"
                fill="#4A6C93" rx="1"
              >
                <title>{{ b.label }} : {{ b.count }} album{{ b.count > 1 ? 's' : '' }}</title>
              </rect>
              <!-- X axis labels -->
              <text v-for="b in yearLabels" :key="'x'+b.label"
                :x="b.x + b.w / 2" :y="BAR_H - 4"
                text-anchor="middle" font-size="9" fill="#9e9e9e">{{ b.label }}</text>
            </svg>
          </div>
        </div>

        <!-- ── Éditeurs + Statut des séries ── -->
        <div class="charts-row">
          <div class="card chart-card chart-card-wide" v-if="stats.publishers?.length">
            <div class="chart-header">
              <h2 class="chart-title">Éditeurs</h2>
            </div>
            <div class="chart-body pie-body">
              <svg :viewBox="`0 0 ${PIE_CX * 2} ${PIE_CY * 2}`" class="pie-svg">
                <path
                  v-for="(s, i) in pubSlices" :key="i"
                  :d="s.d" :fill="s.color" stroke="var(--surface)" stroke-width="1.5"
                >
                  <title>{{ s.name }} : {{ s.count }} ({{ s.pct }}%)</title>
                </path>
              </svg>
              <div class="pie-legend">
                <div v-for="(s, i) in pubSlices" :key="i" class="legend-item">
                  <span class="legend-dot" :style="{ background: s.color }"></span>
                  <span class="legend-name">{{ s.name }}</span>
                  <span class="legend-val">{{ s.count }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="card chart-card chart-card-wide" v-if="statusSlices.length">
            <div class="chart-header">
              <h2 class="chart-title">Séries en cours / terminées</h2>
            </div>
            <div class="chart-body pie-body">
              <svg :viewBox="`0 0 ${PIE_CX * 2} ${PIE_CY * 2}`" class="pie-svg">
                <path
                  v-for="(s, i) in statusSlices" :key="i"
                  :d="s.d" :fill="s.color" stroke="var(--surface)" stroke-width="1.5"
                >
                  <title>{{ s.name }} : {{ s.count }} ({{ s.pct }}%)</title>
                </path>
              </svg>
              <div class="pie-legend">
                <div v-for="(s, i) in statusSlices" :key="i" class="legend-item">
                  <span class="legend-dot" :style="{ background: s.color }"></span>
                  <span class="legend-name">{{ s.name }}</span>
                  <span class="legend-val">{{ s.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Ligne : top séries + éditeurs + dessinateurs + scénaristes ── -->
        <div class="charts-row top-lists-row">
          <!-- Top 10 séries -->
          <div class="card chart-card chart-card-wide" v-if="top10.length">
            <div class="chart-header">
              <h2 class="chart-title">Top 10 séries</h2>
            </div>
            <div class="chart-body">
              <div class="hbar-list">
                <div v-for="(s, i) in top10" :key="s.name" class="hbar-row">
                  <span class="hbar-label">{{ s.name }}</span>
                  <div class="hbar-track">
                    <div class="hbar-fill"
                      :style="{ width: chartsReady ? s.pct + '%' : '0%', transitionDelay: `${i * 60}ms` }"></div>
                  </div>
                  <span class="hbar-val">{{ s.count }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Top éditeurs -->
          <div class="card chart-card chart-card-wide" v-if="topPublishers.length">
            <div class="chart-header">
              <h2 class="chart-title">Top éditeurs</h2>
            </div>
            <div class="chart-body">
              <div class="hbar-list">
                <div v-for="(p, i) in topPublishers" :key="p.name" class="hbar-row">
                  <span class="hbar-label">{{ p.name }}</span>
                  <div class="hbar-track">
                    <div class="hbar-fill hbar-fill-ochre"
                      :style="{ width: chartsReady ? p.pct + '%' : '0%', transitionDelay: `${i * 60}ms` }"></div>
                  </div>
                  <span class="hbar-val">{{ p.count }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Top dessinateurs -->
          <div class="card chart-card chart-card-wide" v-if="topPencillers.length">
            <div class="chart-header">
              <h2 class="chart-title">Top dessinateurs</h2>
            </div>
            <div class="chart-body">
              <div class="hbar-list">
                <div v-for="(p, i) in topPencillers" :key="p.name" class="hbar-row">
                  <span class="hbar-label">{{ p.name }}</span>
                  <div class="hbar-track">
                    <div class="hbar-fill hbar-fill-green"
                      :style="{ width: chartsReady ? p.pct + '%' : '0%', transitionDelay: `${i * 60}ms` }"></div>
                  </div>
                  <span class="hbar-val">{{ p.count }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Top scénaristes -->
          <div class="card chart-card chart-card-wide" v-if="topWriters.length">
            <div class="chart-header">
              <h2 class="chart-title">Top scénaristes</h2>
            </div>
            <div class="chart-body">
              <div class="hbar-list">
                <div v-for="(w, i) in topWriters" :key="w.name" class="hbar-row">
                  <span class="hbar-label">{{ w.name }}</span>
                  <div class="hbar-track">
                    <div class="hbar-fill hbar-fill-orange"
                      :style="{ width: chartsReady ? w.pct + '%' : '0%', transitionDelay: `${i * 60}ms` }"></div>
                  </div>
                  <span class="hbar-val">{{ w.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Genres (treemap) ── -->
        <div class="card chart-card" v-if="genreTreemap.length">
          <div class="chart-header">
            <h2 class="chart-title">Répartition des genres</h2>
            <span class="chart-sub">{{ stats.genres?.length }} genre{{ stats.genres?.length > 1 ? 's' : '' }}</span>
          </div>
          <div class="chart-body">
            <svg :viewBox="`0 0 ${TREEMAP_W} ${TREEMAP_H}`" class="treemap-svg">
              <g v-for="(r, i) in genreTreemap" :key="r.item.name">
                <rect :x="r.x" :y="r.y" :width="r.w" :height="r.h" :fill="r.color" stroke="var(--surface)" stroke-width="2">
                  <title>{{ r.item.name }} : {{ r.item.count }} ({{ r.pct }}%)</title>
                </rect>
                <text v-if="r.nameLabel" :x="r.x + r.w / 2" :y="r.statLabel ? r.y + r.h / 2 - 7 : r.y + r.h / 2 + 5"
                  text-anchor="middle" font-size="14" font-weight="600" fill="#fff">{{ r.nameLabel }}</text>
                <text v-if="r.statLabel" :x="r.x + r.w / 2" :y="r.y + r.h / 2 + 11"
                  text-anchor="middle" font-size="11" fill="#fff">{{ r.statLabel }}</text>
              </g>
            </svg>
          </div>
        </div>

      </template>
      </template>

      <template v-else>
        <div v-if="myLoading" class="state-box">
          <span class="state-pulse">Chargement…</span>
        </div>

        <div v-else-if="myError" class="state-box">
          <span>Impossible de charger vos statistiques de lecture.</span>
        </div>

        <template v-else-if="myStats">

          <!-- ── KPIs personnels ── -->
          <div class="kpi-grid">
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.read_count }}</p>
              <p class="kpi-label">Albums lus</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.in_progress_count }}</p>
              <p class="kpi-label">Albums en cours</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.series_in_progress_count }}</p>
              <p class="kpi-label">Séries en cours</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.pages_read.toLocaleString('fr-FR') }}</p>
              <p class="kpi-label">Pages lues</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ durationParts(myStats.total_seconds).value }}<span class="kpi-unit">{{ durationParts(myStats.total_seconds).unit }}</span></p>
              <p class="kpi-label">Temps de lecture total</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ durationParts(myStats.avg_seconds_per_read).value }}<span class="kpi-unit">{{ durationParts(myStats.avg_seconds_per_read).unit }}</span></p>
              <p class="kpi-label">Temps moyen / album lu</p>
            </div>
            <div class="kpi-card card">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.current_streak }}<span class="kpi-unit">{{ myStats.current_streak > 1 ? 'jours' : 'jour' }}</span></p>
              <p class="kpi-label">Série de lecture en cours</p>
            </div>
            <div class="kpi-card card" v-if="myStats.longest_streak > myStats.current_streak">
              <div class="kpi-accent"></div>
              <p class="kpi-value">{{ myStats.longest_streak }}<span class="kpi-unit">{{ myStats.longest_streak > 1 ? 'jours' : 'jour' }}</span></p>
              <p class="kpi-label">Meilleure série</p>
            </div>
          </div>

          <!-- ── Activité de lecture, 30 derniers jours ── -->
          <div class="card chart-card" v-if="hasActivity">
            <div class="chart-header">
              <h2 class="chart-title">Activité de lecture</h2>
              <span class="chart-sub">30 derniers jours</span>
            </div>
            <div class="chart-body chart-overflow">
              <div class="activity-monitor">
                <div
                  v-for="b in activityBlocks" :key="b.day"
                  class="activity-block"
                  :class="'activity-block-lvl' + b.level"
                  :title="b.label + ' : ' + (b.minutes ? b.minutes + ' min' : 'aucune activité')"
                ></div>
              </div>
              <div class="activity-monitor-labels">
                <span>Il y a 30 jours</span>
                <span>Aujourd'hui</span>
              </div>
            </div>
          </div>
          <div class="card chart-card chart-card-empty" v-else>
            <div class="chart-body">
              <p class="empty-hint">Pas encore de temps de lecture enregistré — lisez un album pour voir apparaître votre activité ici.</p>
            </div>
          </div>

          <div class="charts-row">
            <!-- ── En cours ── -->
            <div class="card chart-card chart-card-wide" v-if="inProgress.length">
              <div class="chart-header">
                <h2 class="chart-title">Lectures en cours</h2>
              </div>
              <div class="chart-body">
                <div class="inprogress-list">
                  <div v-for="t in inProgress" :key="t.id" class="inprogress-row" @click="router.push(`/read/${t.id}`)">
                    <img v-if="t.cover_url" :src="t.cover_url" :alt="t.title" class="inprogress-cover" />
                    <div v-else class="inprogress-cover inprogress-cover-placeholder">📖</div>
                    <div class="inprogress-info">
                      <p class="inprogress-title">{{ t.title || t.filename }}</p>
                      <p class="inprogress-series">{{ t.series_name }}</p>
                      <div class="inprogress-track">
                        <div class="inprogress-fill" :style="{ width: t.progress_pct + '%' }"></div>
                      </div>
                    </div>
                    <span class="inprogress-pct">{{ t.progress_pct }}%</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── Genres lus ── -->
            <div class="card chart-card chart-card-wide" v-if="myGenreBars.length">
              <div class="chart-header">
                <h2 class="chart-title">Mes genres les plus lus</h2>
              </div>
              <div class="chart-body">
                <div class="hbar-list hbar-list-genres">
                  <div v-for="(g, i) in myGenreBars" :key="g.name" class="hbar-row">
                    <span class="hbar-label">{{ g.name }}</span>
                    <div class="hbar-track">
                      <div class="hbar-fill"
                        :style="{ width: myChartsReady ? g.pct + '%' : '0%', transitionDelay: `${i * 60}ms` }"></div>
                    </div>
                    <span class="hbar-val">{{ g.count }}<span v-if="g.seconds" class="hbar-val-sub"> · {{ formatDuration(g.seconds) }}</span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ── Répartition des notes personnelles ── -->
          <div class="card chart-card" v-if="hasRatings">
            <div class="chart-header">
              <h2 class="chart-title">Répartition de mes notes</h2>
            </div>
            <div class="chart-body">
              <svg :viewBox="`0 0 ${RATING_BAR_W} ${RATING_BAR_H}`" class="rating-bar-svg">
                <line v-for="tick in ratingAxisY" :key="tick.val"
                  :x1="RATING_BAR_PAD.left" :y1="tick.y" :x2="RATING_BAR_W - RATING_BAR_PAD.right" :y2="tick.y"
                  stroke="#e0e0e0" stroke-width="1" />
                <text v-for="tick in ratingAxisY" :key="'y'+tick.val"
                  :x="RATING_BAR_PAD.left - 4" :y="tick.y + 4"
                  text-anchor="end" font-size="9" fill="#9e9e9e">{{ tick.val }}</text>
                <rect
                  v-for="(b, i) in ratingBars" :key="b.label"
                  :x="b.x"
                  :y="b.y + b.h - (animatedRatingHeights[i] ?? 0)"
                  :width="b.w"
                  :height="animatedRatingHeights[i] ?? 0"
                  fill="#4A6C93" rx="1"
                >
                  <title>{{ b.label }} : {{ b.count }} album{{ b.count > 1 ? 's' : '' }}</title>
                </rect>
                <text v-for="b in ratingBars" :key="'x'+b.label"
                  :x="b.x + b.w / 2" :y="RATING_BAR_H - 6"
                  text-anchor="middle" font-size="10" fill="#9e9e9e">{{ b.label }}</text>
              </svg>
            </div>
          </div>

        </template>
      </template>
    </main>
  </AppLayout>
</template>

<style scoped>
.stats-main {
  flex: 1;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1100px;
}

.stats-title {
  font-family: var(--font-display);
  font-weight: 400;
  text-transform: uppercase;
  font-size: 1.4rem;
  color: var(--text);
}

/* KPI */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media (min-width: 480px) {
  /* 135px (au lieu de 160px) : les 7 cartes actuelles tiennent sur une seule ligne dès que
     la fenêtre offre assez de place (7×135px + espacements ≈ 1030px, sous les ~1060px de
     contenu disponible à l'intérieur du max-width de 1100px de la page) au lieu de retomber
     à 6+1 juste avant ce seuil. */
  .kpi-grid { grid-template-columns: repeat(auto-fill, minmax(135px, 1fr)); }
}
.kpi-card {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  position: relative;
  overflow: hidden;
  cursor: default;
  transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
}
.kpi-card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-3px);
  border-color: var(--primary);
}
.kpi-accent {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--primary);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.25s ease;
  border-radius: var(--radius) var(--radius) 0 0;
}
.kpi-card:hover .kpi-accent {
  transform: scaleX(1);
}
/* Texte simple plutôt qu'une couleur d'accent — répété sur plusieurs cartes, une couleur
   vive ici donnait le même effet de surcharge que les anciennes barres tout en vermillon. */
.kpi-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
}
.kpi-value-sm { font-size: 1rem; }
.kpi-unit { font-size: 0.55em; font-weight: 600; color: var(--muted); margin-left: 3px; }
.kpi-label {
  font-size: 0.78rem;
  color: var(--muted);
  transition: color 0.2s;
}
.kpi-card:hover .kpi-label { color: var(--text); }

/* Chart cards */
.chart-card {
  overflow: hidden;
}
.chart-card-wide { flex: 1; min-width: 280px; max-width: calc(50% - 8px); }

/* Les 4 tops (séries/éditeurs/dessinateurs/scénaristes) : toujours 2 colonnes fixes — séries
   + éditeurs sur une ligne, dessinateurs + scénaristes sur la suivante — quelle que soit la
   largeur d'écran, plutôt que de dépendre du flex-wrap hérité de .charts-row : avec
   flex-basis:0 (implicite via flex:1) et un min-width, l'ordre de retour à la ligne du flex
   n'est pas fiable ; la grille impose ce découpage précis en toutes circonstances.
   Sélecteur composé (.charts-row.top-lists-row) plutôt que .top-lists-row seul : même
   spécificité qu'un sélecteur à une seule classe, la règle "display:flex" de .charts-row
   (définie plus bas dans le fichier) gagnerait sinon sur l'ordre de cascade et écraserait
   silencieusement ce display:grid. */
.charts-row.top-lists-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
}
.top-lists-row .chart-card-wide { min-width: 0; max-width: 100%; }

@media (max-width: 640px) {
  /* En dessous de 640px, 50% du conteneur passe sous le min-width (280px) — conflit qui
     forçait chaque card à une largeur fixe de 280px au lieu de remplir la ligne, d'où des
     cards visiblement plus étroites que le reste de la page. Empilées en pleine largeur
     (n'affecte pas .top-lists-row, déjà en grille 2 colonnes par la règle ci-dessus). */
  .chart-card-wide { min-width: 0; max-width: 100%; }
  /* Libellé/valeur réduits pour laisser de la place à la barre malgré la colonne étroite. */
  .top-lists-row .hbar-label { width: 64px; font-size: 0.72rem; }
  .top-lists-row .hbar-val { width: 22px; font-size: 0.7rem; }
  .top-lists-row .hbar-row { gap: 6px; }
  .top-lists-row .chart-body { padding: 12px 10px; }
}
.chart-card-sm   { max-width: 420px; }

.chart-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 12px 16px 8px;
  border-bottom: 1px solid var(--border);
}
.chart-title { font-size: 0.9rem; font-weight: 600; }
.chart-sub   { font-size: 0.78rem; color: var(--muted); }

.chart-body {
  padding: 14px 16px;
}
.chart-overflow { overflow-x: auto; }

/* Bar chart */
.bar-svg {
  width: 100%;
  min-width: 400px;
  height: auto;
  display: block;
}
@media (max-width: 480px) {
  /* En dessous de 480px, le min-width forçait un débordement horizontal au lieu de
     laisser le SVG (dimensionné via viewBox) se réduire proportionnellement. */
  .bar-svg { min-width: 0; }
}

/* Activité de lecture — rangée de barres façon "moniteur de disponibilité" (une par jour,
   hauteur uniforme, seule la couleur porte l'intensité) plutôt qu'un histogramme classique. */
.activity-monitor {
  display: flex;
  gap: 3px;
  overflow-x: auto;
}
.activity-block {
  flex: 1 1 0;
  min-width: 6px;
  height: 28px;
  border-radius: 3px;
  background: var(--light);
  border: 1px solid var(--border);
  cursor: default;
}
/* Intensité croissante par paliers (0 à 4) plutôt qu'un dégradé continu — plus lisible d'un
   coup d'œil, même principe que la grille de contributions GitHub. */
.activity-block-lvl1 { background: color-mix(in srgb, var(--vermilion) 25%, var(--light)); border-color: transparent; }
.activity-block-lvl2 { background: color-mix(in srgb, var(--vermilion) 50%, var(--light)); border-color: transparent; }
.activity-block-lvl3 { background: color-mix(in srgb, var(--vermilion) 75%, var(--light)); border-color: transparent; }
.activity-block-lvl4 { background: var(--vermilion); border-color: transparent; }
.activity-monitor-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 0.7rem;
  color: var(--muted);
}

.rating-bar-svg {
  width: 100%;
  max-width: 320px;
  height: auto;
  display: block;
  margin: 0 auto;
}

.treemap-svg {
  width: 100%;
  height: auto;
  display: block;
}
.treemap-svg text { pointer-events: none; }

/* Pie charts */
.charts-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: stretch;
}

.pie-body {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.pie-svg {
  width: 140px;
  height: 140px;
  flex-shrink: 0;
}
.pie-legend {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
  min-width: 120px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.78rem;
}
.legend-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}
.legend-val {
  font-weight: 600;
  color: var(--muted);
  flex-shrink: 0;
}

/* Horizontal bars */
.hbar-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hbar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
}
.hbar-label {
  width: 140px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}
.hbar-track {
  flex: 1;
  height: 10px;
  background: var(--light);
  border-radius: 5px;
  overflow: hidden;
}
.hbar-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 5px;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
.hbar-fill-orange { background: var(--orange-bar); }
.hbar-fill-green  { background: var(--green-bar); }
.hbar-fill-ochre  { background: var(--ochre); }
.hbar-val {
  width: 28px;
  text-align: right;
  font-weight: 600;
  color: var(--muted);
  font-size: 0.78rem;
}
/* Genres personnels (myGenreBars) : la valeur porte aussi le temps de lecture cumulé
   ("12 · 3 h 20 min"), trop long pour la largeur fixe des autres listes hbar. */
.hbar-val-sub { font-weight: 400; }
.hbar-list-genres .hbar-val { width: auto; white-space: nowrap; }

/* States */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-box {
  display: flex; align-items: center; justify-content: center;
  min-height: 200px;
}
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }

/* ── Onglets Bibliothèque / Ma lecture — même style que SettingsUsersView.vue ── */
.tabs-row {
  display: flex; gap: 22px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.tab-btn {
  padding: 0 0 10px;
  background: none; border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-family: var(--font);
  font-size: 0.85rem; font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn-active { color: var(--vermilion); border-bottom-color: var(--vermilion); }

/* ── "Ma lecture" — état vide (pas encore de temps de lecture enregistré) ── */
.chart-card-empty .chart-body { padding: 24px 16px; }
.empty-hint { font-size: 0.85rem; color: var(--muted); text-align: center; }

/* ── "Ma lecture" — lectures en cours (même esprit que .continue-card de HomeView.vue,
   en liste compacte plutôt qu'en rangée de cartes défilante) ── */
.inprogress-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.inprogress-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 4px;
  margin: -4px;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s;
}
.inprogress-row:hover { background-color: var(--light); }
.inprogress-cover {
  width: 36px;
  aspect-ratio: 0.71;
  object-fit: cover;
  border-radius: 3px;
  flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}
.inprogress-cover-placeholder {
  display: flex; align-items: center; justify-content: center;
  background: var(--light);
  font-size: 1rem;
}
.inprogress-info { flex: 1; min-width: 0; }
.inprogress-title {
  font-size: 0.8rem; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.inprogress-series {
  font-size: 0.72rem; color: var(--muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-bottom: 4px;
}
.inprogress-track {
  height: 4px;
  background: var(--light);
  border-radius: 2px;
  overflow: hidden;
}
.inprogress-fill { height: 100%; background: var(--vermilion); border-radius: 2px; }
.inprogress-pct {
  font-size: 0.75rem; font-weight: 600; color: var(--muted);
  flex-shrink: 0; width: 34px; text-align: right;
}

</style>
