<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import SvgIcon from '../SvgIcon.vue'

const props = defineProps({
  tome: { type: Object, required: true },
})
const emit = defineEmits(['edit-metadata', 'convert'])
const router = useRouter()

const formatBadgeClass = {
  cbz: 'badge-format-cbz',
  cbr: 'badge-format-cbr',
  pdf: 'badge-format-pdf',
}
</script>

<template>
  <div class="tome-row">
    <!-- Cover thumb -->
    <div
      class="tome-thumb"
      @click="router.push(`/read/${tome.id}`)"
      title="Lire"
    >
      <img
        :src="tome.cover_url"
        :alt="tome.title"
        class="tome-thumb-img"
        loading="lazy"
        @error="$event.target.style.display='none'"
      />
    </div>

    <!-- Info -->
    <div class="tome-info" @click="router.push(`/read/${tome.id}`)">
      <div class="tome-title-row">
        <span v-if="tome.number" class="tome-number">T{{ tome.number.padStart(2,'0') }}</span>
        <span class="tome-title">{{ tome.title || tome.filename }}</span>
      </div>
      <div class="tome-meta-row">
        <span :class="['badge-format', formatBadgeClass[tome.file_format] || 'badge-format-default']">
          {{ tome.file_format.toUpperCase() }}
        </span>
        <span v-if="tome.page_count" class="tome-pages">{{ tome.page_count }} p.</span>
        <span v-if="!tome.has_metadata" class="tome-no-meta">Sans métadonnées</span>
      </div>
    </div>

    <!-- Actions -->
    <div class="tome-actions">
      <button
        @click="router.push(`/read/${tome.id}`)"
        class="btn btn-ghost btn-icon btn-sm"
        title="Lire"
      ><SvgIcon name="read" style="font-size:15px" /></button>
      <button
        @click="$emit('edit-metadata', tome)"
        class="btn btn-ghost btn-icon btn-sm"
        title="Modifier les métadonnées"
      ><SvgIcon name="edit" style="font-size:15px" /></button>
      <button
        v-if="tome.file_format !== 'cbz'"
        @click="$emit('convert', tome)"
        class="btn btn-ghost btn-icon btn-sm"
        title="Convertir en CBZ"
      ><SvgIcon name="convert" style="font-size:15px" /></button>
    </div>
  </div>
</template>

<style scoped>
.tome-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: default;
  transition: box-shadow 0.15s ease;
}
.tome-row:hover {
  box-shadow: var(--shadow);
}
.tome-row:hover .tome-actions {
  opacity: 1;
}

/* Thumb */
.tome-thumb {
  width: 40px;
  height: 56px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background-color: var(--light);
  flex-shrink: 0;
  cursor: pointer;
  border: 1px solid var(--border);
}
.tome-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.2s ease;
}
.tome-thumb:hover .tome-thumb-img {
  transform: scale(1.08);
}

/* Info */
.tome-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.tome-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}
.tome-number {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--vermilion);
  flex-shrink: 0;
  font-family: ui-monospace, monospace;
}
.tome-title {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tome-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.badge-format {
  font-size: 0.7rem;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.03em;
}
.badge-format-cbz {
  background-color: var(--success-bg);
  color: var(--success-text);
}
.badge-format-cbr {
  background-color: var(--warning-bg);
  color: var(--warning-text);
}
.badge-format-pdf {
  background-color: var(--info-bg);
  color: var(--info-text);
}
.badge-format-default {
  background-color: var(--light);
  color: var(--muted);
  border: 1px solid var(--border);
}

.tome-pages {
  font-size: 0.8rem;
  color: var(--muted);
}
.tome-no-meta {
  font-size: 0.75rem;
  color: var(--orange-bar);
  background-color: var(--warning-bg);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Actions */
.tome-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
</style>
