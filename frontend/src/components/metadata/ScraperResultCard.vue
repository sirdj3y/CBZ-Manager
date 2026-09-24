<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})
defineEmits(['select'])

const tome = computed(() => {
  const n = props.result.number
  if (!n) return null
  return /^\d+$/.test(n) ? 'T' + n.padStart(2, '0') : n
})
</script>

<template>
  <div
    @click="$emit('select', result)"
    :class="['result-card', { 'result-card-selected': selected }]"
  >
    <!-- Cover -->
    <div class="result-cover">
      <img v-if="result.cover_url" :src="result.cover_url" class="result-cover-img" loading="lazy" />
      <div v-else class="result-cover-placeholder">📖</div>
    </div>
    <!-- Info -->
    <div class="result-info">
      <p class="result-title-row">
        <span class="result-title">{{ result.title }}</span>
        <span v-if="tome" class="result-tome">{{ tome }}</span>
      </p>
      <p v-if="result.authors?.length" class="result-authors">{{ result.authors.join(', ') }}</p>
      <p class="result-meta">
        <span v-if="result.publisher">{{ result.publisher }}</span>
        <span v-if="result.publisher && result.year"> · </span>
        <span v-if="result.year">{{ result.year }}</span>
        <span v-if="result.pages"> · {{ result.pages }}p</span>
      </p>
      <span class="result-source-badge">{{ result.source }}</span>
    </div>
  </div>
</template>

<style scoped>
.result-card {
  display: flex;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, background-color 0.15s;
  background: var(--surface);
}
.result-card:hover {
  border-color: var(--border);
  box-shadow: var(--shadow-sm);
}
.result-card-selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-focus);
  background-color: var(--primary-light);
}

.result-cover {
  width: 44px;
  height: 62px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
  background-color: var(--light);
  border: 1px solid var(--border);
}
.result-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.result-cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
}

.result-info {
  flex: 1;
  min-width: 0;
}

.result-title-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 3px;
  min-width: 0;
}

.result-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.result-tome {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--muted);
  flex-shrink: 0;
}

.result-authors {
  font-size: 0.8rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
}

.result-meta {
  font-size: 0.775rem;
  color: var(--muted);
  margin-bottom: 5px;
}

.result-source-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 1px 7px;
  background-color: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
