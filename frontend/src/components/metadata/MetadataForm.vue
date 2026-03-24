<script setup>
import AutocompleteInput from '../ui/AutocompleteInput.vue'
import { useLibraryStore } from '../../stores/library'
import { computed, onMounted } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const library = useLibraryStore()

onMounted(() => {
  if (!library.authors.writers.length) library.fetchAuthors()
})

function update(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

// Pool commun writers + pencillers (dédupliqué) pour Writer et Penciller
const authorPool = computed(() => {
  const all = new Set([...library.authorNames.writers, ...library.authorNames.pencillers])
  return [...all].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
})

const FIELDS = [
  { key: 'Series',      label: 'Série',         autocomplete: null },
  { key: 'Title',       label: 'Titre',          autocomplete: null },
  { key: 'Number',      label: 'Numéro',         autocomplete: null },
  { key: 'Year',        label: 'Année',          autocomplete: null },
  { key: 'Writer',      label: 'Scénariste',     autocomplete: 'authors' },
  { key: 'Penciller',   label: 'Dessinateur',    autocomplete: 'authors' },
  { key: 'Publisher',   label: 'Éditeur',        autocomplete: 'publishers' },
  { key: 'LanguageISO', label: 'Langue (ISO)',   autocomplete: null },
  { key: 'PageCount',   label: 'Pages',          autocomplete: null },
]

function getSuggestions(type) {
  if (type === 'authors')    return authorPool.value
  if (type === 'publishers') return library.authorNames.publishers
  return []
}
</script>

<template>
  <div class="meta-form">
    <div v-for="field in FIELDS" :key="field.key" class="meta-field">
      <label class="form-label">{{ field.label }}</label>
      <AutocompleteInput
        v-if="field.autocomplete"
        :model-value="modelValue[field.key] || ''"
        :suggestions="getSuggestions(field.autocomplete)"
        :readonly="readonly"
        @update:model-value="update(field.key, $event)"
      />
      <input
        v-else
        :value="modelValue[field.key] || ''"
        :readonly="readonly"
        type="text"
        @input="update(field.key, $event.target.value)"
        class="form-control"
        :class="{ 'readonly': readonly }"
      />
    </div>
  </div>
</template>

<style scoped>
.meta-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.meta-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-control.readonly {
  background-color: var(--light);
  cursor: default;
}
</style>
