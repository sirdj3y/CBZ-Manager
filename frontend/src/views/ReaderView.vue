<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useReaderStore } from '../stores/reader'

const route = useRoute()
const router = useRouter()
const reader = useReaderStore()

const loading = ref(true)
const showResumeDialog = ref(false)
const imgA = ref(null)  // Left/single page
const imgB = ref(null)  // Right page (double mode)
const showUI = ref(true)
const zoomWidth = ref(false)  // false = page entière, true = zoom largeur
const pagesRef = ref(null)
let uiTimer = null

onMounted(async () => {
  await reader.loadTome(Number(route.params.id))
  loading.value = false
  if (reader.hasSavedProgress) {
    showResumeDialog.value = true
  }
  window.addEventListener('keydown', onKey)
  document.addEventListener('mousemove', resetUITimer)
})

watch(() => reader.currentPage, () => {
  if (pagesRef.value) pagesRef.value.scrollTop = 0
})

function resumeReading() {
  reader.resumeFromSaved()
  showResumeDialog.value = false
}

function restartReading() {
  showResumeDialog.value = false
}

onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('mousemove', resetUITimer)
  clearTimeout(uiTimer)
})

function onKey(e) {
  if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); reader.nextPage() }
  if (e.key === 'ArrowLeft') { e.preventDefault(); reader.prevPage() }
  if (e.key === 'ArrowUp') { e.preventDefault(); zoomWidth.value = true }
  if (e.key === 'ArrowDown') { e.preventDefault(); zoomWidth.value = false }
  if (e.key === 'Escape') router.back()
  if (e.key === 'd') reader.setMode(reader.mode === 'double' ? 'single' : 'double')
  if (e.key === 'f') document.documentElement.requestFullscreen?.()
}

function resetUITimer() {
  showUI.value = true
  clearTimeout(uiTimer)
  uiTimer = setTimeout(() => { showUI.value = false }, 3000)
}

const currentPageUrl = computed(() =>
  reader.tomeId ? reader.pageUrl(reader.tomeId, reader.currentPage) : null
)
const nextPageUrl = computed(() =>
  reader.mode === 'double' && reader.tomeId && reader.currentPage + 1 < reader.pageCount
    ? reader.pageUrl(reader.tomeId, reader.currentPage + 1)
    : null
)

function clickZone(e) {
  const w = e.currentTarget.offsetWidth
  const x = e.clientX
  if (x < w * 0.25) reader.prevPage()
  else if (x > w * 0.75) reader.nextPage()
  else zoomWidth.value = !zoomWidth.value
}
</script>

<template>
  <div class="reader" @click="clickZone">

    <!-- Resume dialog -->
    <Teleport to="body">
      <div v-if="showResumeDialog" class="resume-backdrop" @click.self="restartReading">
        <div class="resume-dialog">
          <p class="resume-title">Reprendre la lecture ?</p>
          <p class="resume-sub">Vous étiez à la page {{ reader.savedPage + 1 }}</p>
          <div class="resume-actions">
            <button class="btn btn-primary btn-sm" @click="resumeReading">Reprendre</button>
            <button class="btn btn-ghost btn-sm" @click="restartReading">Recommencer</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Top toolbar -->
    <Transition name="fade">
      <div v-show="showUI" class="reader-toolbar reader-toolbar-top" @click.stop>
        <button @click="router.back()" class="reader-btn" title="Retour">←</button>
        <span class="reader-title">{{ reader.title }}</span>

        <button
          @click="reader.setMode(reader.mode === 'double' ? 'single' : 'double')"
          class="reader-mode-btn"
          :class="{ 'reader-mode-active': reader.mode === 'double' }"
        >Double</button>

        <span class="reader-page-info">{{ reader.currentPage + 1 }} / {{ reader.pageCount }}</span>
      </div>
    </Transition>

    <!-- Pages area -->
    <div v-if="loading" class="reader-loading">Chargement…</div>
    <div v-else ref="pagesRef" :class="['reader-pages', { 'zoom-width': zoomWidth }]">
      <!-- Double page -->
      <div v-if="reader.mode === 'double' && nextPageUrl" class="reader-double">
        <img :src="currentPageUrl" class="reader-page-img" @error="$event.target.style.opacity='0.3'" />
        <img :src="nextPageUrl" class="reader-page-img" @error="$event.target.style.opacity='0.3'" />
      </div>
      <!-- Single page -->
      <img
        v-else
        :src="currentPageUrl"
        class="reader-page-single"
        @error="$event.target.style.opacity='0.3'"
      />
    </div>

    <!-- Bottom nav -->
    <Transition name="fade">
      <div v-show="showUI" class="reader-toolbar reader-toolbar-bottom" @click.stop>
        <button
          @click="reader.prevPage()"
          :disabled="reader.currentPage === 0"
          class="reader-nav-btn"
        >‹</button>

        <div class="reader-progress-track">
          <div
            class="reader-progress-fill"
            :style="{ width: reader.pageCount ? `${((reader.currentPage + 1) / reader.pageCount) * 100}%` : '0%' }"
          />
        </div>

        <button
          @click="reader.nextPage()"
          :disabled="reader.currentPage >= reader.pageCount - 1"
          class="reader-nav-btn"
        >›</button>
      </div>
    </Transition>
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
}

/* Toolbar shared */
.reader-toolbar {
  position: absolute;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}

.reader-toolbar-top {
  top: 0;
  background: linear-gradient(to bottom, rgba(0,0,0,0.75), transparent);
}

.reader-toolbar-bottom {
  bottom: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.75), transparent);
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

/* Title */
.reader-title {
  flex: 1;
  font-size: 0.875rem;
  color: rgba(255,255,255,0.8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Mode toggle */
.reader-mode-btn {
  background: none;
  border: 1px solid rgba(255,255,255,0.3);
  color: rgba(255,255,255,0.7);
  border-radius: 4px;
  font-size: 0.8125rem;
  padding: 3px 10px;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}
.reader-mode-btn:hover { color: #fff; border-color: rgba(255,255,255,0.6); }
.reader-mode-active {
  background-color: rgba(255,255,255,0.2);
  color: #fff;
}

/* Page info */
.reader-page-info {
  font-size: 0.8125rem;
  color: rgba(255,255,255,0.6);
  white-space: nowrap;
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
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.reader-pages.zoom-width {
  align-items: flex-start;
  overflow-y: auto;
  overflow-x: hidden;
}

.reader-double {
  display: flex;
  height: 100%;
  gap: 2px;
}

.reader-page-img {
  height: 100%;
  object-fit: contain;
}

.reader-page-single {
  max-height: 100%;
  max-width: 100%;
  object-fit: contain;
}
.zoom-width .reader-page-single {
  max-height: none;
  max-width: none;
  width: 100%;
  height: auto;
}

/* Bottom nav */
.reader-nav-btn {
  background: none;
  border: none;
  color: rgba(255,255,255,0.7);
  font-size: 1.8rem;
  cursor: pointer;
  padding: 0 6px;
  line-height: 1;
  transition: color 0.15s;
}
.reader-nav-btn:hover:not(:disabled) { color: #fff; }
.reader-nav-btn:disabled { opacity: 0.25; cursor: default; }

.reader-progress-track {
  flex: 1;
  max-width: 320px;
  height: 4px;
  background: rgba(255,255,255,0.2);
  border-radius: 4px;
  overflow: hidden;
}
.reader-progress-fill {
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* Resume dialog */
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
</style>
