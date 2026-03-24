<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import AppLayout from '../components/layout/AppLayout.vue'
import client from '../api/client'
import { CountUp } from 'countup.js'

const stats = ref(null)
const loading = ref(true)

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

watch(stats, async (val) => {
  if (!val) return
  await nextTick()
  initCounters()
  setTimeout(() => { chartsReady.value = true }, 50)
  animateBars()
})

onMounted(async () => {
  try {
    const { data } = await client.get('/api/stats')
    stats.value = data
  } finally {
    loading.value = false
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

// ── Camemberts ───────────────────────────────────────────────────────────
const PIE_R = 70
const PIE_CX = 90
const PIE_CY = 90
const PIE_CIRC = 2 * Math.PI * PIE_R

const COLORS = [
  '#1565c0','#e65100','#2e7d32','#6a1b9a','#00838f',
  '#f57f17','#ad1457','#37474f','#558b2f','#4527a0',
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
const fmtSlices = computed(() => calcSlices(stats.value?.formats, PIE_R))

// ── Barres horizontales (top séries / scénaristes) ───────────────────────
function hbarPct(items) {
  if (!items?.length) return []
  const max = Math.max(...items.map(d => d.count))
  return items.map(d => ({ ...d, pct: Math.round((d.count / max) * 100) }))
}
const top10 = computed(() => hbarPct(stats.value?.top10_series))
const topWriters = computed(() => hbarPct(stats.value?.writers))
const topPencillers = computed(() => hbarPct(stats.value?.pencillers))
</script>

<template>
  <AppLayout>
    <main class="stats-main">
      <h1 class="stats-title">Statistiques</h1>

      <div v-if="loading" class="state-box">
        <span class="state-pulse">Chargement…</span>
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
            <p class="kpi-value">{{ formatSize(stats.total_size) }}</p>
            <p class="kpi-label">Taille totale</p>
          </div>
          <div class="kpi-card card">
            <div class="kpi-accent"></div>
            <p class="kpi-value">{{ formatSize(stats.avg_size) }}</p>
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
                fill="#1565c0" rx="1"
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

        <!-- ── Éditeurs + Formats ── -->
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

          <div class="card chart-card chart-card-wide" v-if="fmtSlices.length">
            <div class="chart-header">
              <h2 class="chart-title">Formats</h2>
            </div>
            <div class="chart-body pie-body">
              <svg :viewBox="`0 0 ${PIE_CX * 2} ${PIE_CY * 2}`" class="pie-svg">
                <path
                  v-for="(s, i) in fmtSlices" :key="i"
                  :d="s.d" :fill="s.color" stroke="var(--surface)" stroke-width="1.5"
                >
                  <title>{{ s.name }} : {{ s.count }} ({{ s.pct }}%)</title>
                </path>
              </svg>
              <div class="pie-legend">
                <div v-for="(s, i) in fmtSlices" :key="i" class="legend-item">
                  <span class="legend-dot" :style="{ background: s.color }"></span>
                  <span class="legend-name">{{ s.name }}</span>
                  <span class="legend-val">{{ s.count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Ligne : top séries + scénaristes + dessinateurs ── -->
        <div class="charts-row">
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
        </div>

      </template>
    </main>
  </AppLayout>
</template>

<style scoped>
.stats-main {
  flex: 1;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1200px;
}

.stats-title {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text);
}

/* KPI */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 14px;
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
.kpi-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--primary);
  line-height: 1.1;
  transition: color 0.2s;
}
.kpi-value-sm { font-size: 1rem; }
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
.hbar-val {
  width: 28px;
  text-align: right;
  font-weight: 600;
  color: var(--muted);
  font-size: 0.78rem;
}

/* States */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.state-box {
  display: flex; align-items: center; justify-content: center;
  min-height: 200px;
}
.state-pulse { font-size: 0.9rem; color: var(--muted); animation: pulse 1.4s ease-in-out infinite; }

</style>
