<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  suggestions: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const inputRef = ref(null)

// Terme en cours de saisie = dernier segment après la dernière virgule
function currentTerm() {
  const val = props.modelValue || ''
  const parts = val.split(',')
  return parts[parts.length - 1].trim().toLowerCase()
}

const filtered = computed(() => {
  const term = currentTerm()
  if (!term) return []
  return props.suggestions.filter(s =>
    s.toLowerCase().includes(term) && s.toLowerCase() !== term
  ).slice(0, 8)
})

function onInput(e) {
  emit('update:modelValue', e.target.value)
  open.value = true
}

function select(suggestion) {
  const val = props.modelValue || ''
  const parts = val.split(',')
  parts[parts.length - 1] = ' ' + suggestion
  // Trim le premier élément si vide
  const joined = parts.map((p, i) => i === 0 ? p.trim() : p.trimStart()).join(',')
  emit('update:modelValue', joined)
  open.value = false
  inputRef.value?.focus()
}

function onBlur() {
  // Délai pour laisser le clic sur suggestion se déclencher
  setTimeout(() => { open.value = false }, 150)
}
</script>

<template>
  <div class="autocomplete-wrap">
    <input
      ref="inputRef"
      :value="modelValue"
      :readonly="readonly"
      :placeholder="placeholder"
      type="text"
      class="form-control"
      :class="{ readonly }"
      @input="onInput"
      @focus="open = true"
      @blur="onBlur"
    />
    <ul v-if="open && filtered.length" class="autocomplete-list">
      <li
        v-for="s in filtered"
        :key="s"
        class="autocomplete-item"
        @mousedown.prevent="select(s)"
      >{{ s }}</li>
    </ul>
  </div>
</template>

<style scoped>
.autocomplete-wrap {
  position: relative;
}

.autocomplete-list {
  position: absolute;
  top: calc(100% + 2px);
  left: 0; right: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  list-style: none;
  margin: 0; padding: 4px 0;
  z-index: 200;
  max-height: 220px;
  overflow-y: auto;
}

.autocomplete-item {
  padding: 6px 12px;
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--text);
}
.autocomplete-item:hover {
  background: var(--primary-light);
  color: var(--primary);
}

.form-control.readonly {
  background-color: var(--light);
  cursor: default;
}
</style>
