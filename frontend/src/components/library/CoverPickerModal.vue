<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { libraryApi } from '../../api/library'
import { useNotificationStore } from '../../stores/notifications'

const props = defineProps({
  series: { type: Object, required: true }, // doit avoir .tomes[]
})
const emit = defineEmits(['close', 'updated'])

function parseTomeNumber(tome) {
  const raw = String(tome.number || tome.title || tome.filename || '')
  const hsMatch = raw.match(/hs\s*(\d+)/i)
  if (hsMatch) return 10000 + parseInt(hsMatch[1])
  const numMatch = raw.match(/(\d+)/)
  if (numMatch) return parseInt(numMatch[1])
  return 99999
}

const sortedTomes = computed(() =>
  [...props.series.tomes].sort((a, b) => parseTomeNumber(a) - parseTomeNumber(b))
)

const notif = useNotificationStore()

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

async function setCover(tomeId) {
  const { data } = await libraryApi.setSeriesCover(props.series.id, tomeId)
  notif.success('Cover mise à jour')
  emit('updated', { cover_url: data.cover_url, cover_tome_id: data.cover_tome_id })
  emit('close')
}

async function resetCover() {
  const { data } = await libraryApi.setSeriesCover(props.series.id, null)
  notif.success('Cover réinitialisée')
  emit('updated', { cover_url: data.cover_url, cover_tome_id: null })
  emit('close')
}
</script>

<template>
  <div class="cover-picker-backdrop" @click.self="$emit('close')">
    <div class="cover-picker-modal">
      <div class="cover-picker-header">
        <span>Choisir la miniature — {{ series.name }}</span>
        <button class="btn btn-ghost btn-sm" @click="$emit('close')">✕</button>
      </div>
      <div class="cover-picker-grid">
        <!-- Reset to default (first tome) -->
        <div
          class="cover-picker-item"
          :class="{ 'cover-picker-item-active': !series.cover_tome_id }"
          @click="resetCover"
          title="Miniature par défaut (premier tome)"
        >
          <img v-if="series.tomes[0]?.cover_url" :src="series.tomes[0].cover_url" class="cover-picker-img" />
          <div v-else class="cover-picker-placeholder">📚</div>
          <span class="cover-picker-label">Par défaut</span>
          <span v-if="!series.cover_tome_id" class="cover-picker-check">✓</span>
        </div>
        <!-- Each tome -->
        <div
          v-for="tome in sortedTomes"
          :key="tome.id"
          class="cover-picker-item"
          :class="{ 'cover-picker-item-active': series.cover_tome_id === tome.id }"
          @click="setCover(tome.id)"
          :title="tome.title || tome.filename"
        >
          <img v-if="tome.cover_url" :src="tome.cover_url" class="cover-picker-img" />
          <div v-else class="cover-picker-placeholder">📖</div>
          <span class="cover-picker-label">{{ tome.title || tome.filename }}</span>
          <span v-if="series.cover_tome_id === tome.id" class="cover-picker-check">✓</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cover-picker-backdrop {
  position: fixed; inset: 0; z-index: 500;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.cover-picker-modal {
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%; max-width: 780px;
  height: 85vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.cover-picker-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 0.9rem; font-weight: 600; flex-shrink: 0;
}
.cover-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 10px;
  padding: 14px;
  overflow-y: auto;
  align-content: start;
}

.cover-picker-item {
  position: relative; cursor: pointer;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.12s;
}
.cover-picker-item:hover { border-color: var(--primary); transform: scale(1.03); }
.cover-picker-item-active { border-color: var(--primary); }

.cover-picker-img {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
  object-position: center top;
  display: block;
  background: var(--light);
}
.cover-picker-placeholder {
  width: 100%; aspect-ratio: 2/3;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem; background: var(--light);
}
.cover-picker-label {
  display: block; font-size: 0.65rem; color: var(--text);
  padding: 3px 4px; background: var(--surface);
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.cover-picker-check {
  position: absolute; top: 4px; left: 4px;
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--primary); color: #fff;
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
</style>
