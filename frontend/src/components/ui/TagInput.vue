<script setup>
import { ref, computed } from 'vue'
import { tomesApi } from '../../api/tomes'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

const input = ref('')
const allTags = ref([])
const inputRef = ref(null)

tomesApi.getTags().then(({ data }) => { allTags.value = data })

const suggestions = computed(() => {
  if (!input.value.trim()) return []
  const q = input.value.toLowerCase()
  return allTags.value.filter(t =>
    t.toLowerCase().includes(q) && !props.modelValue.includes(t)
  ).slice(0, 6)
})

function addTag(tag) {
  const t = (tag || input.value).trim()
  if (t && !props.modelValue.includes(t)) {
    emit('update:modelValue', [...props.modelValue, t])
  }
  input.value = ''
  inputRef.value?.focus()
}

function removeTag(tag) {
  emit('update:modelValue', props.modelValue.filter(t => t !== tag))
}

function onKeydown(e) {
  if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); e.stopPropagation(); addTag() }
  if (e.key === 'Backspace' && !input.value && props.modelValue.length) {
    removeTag(props.modelValue[props.modelValue.length - 1])
  }
}
</script>

<template>
  <div class="tag-input-wrap">
    <div class="tag-chips">
      <span v-for="tag in modelValue" :key="tag" class="tag-chip">
        {{ tag }}
        <button type="button" class="tag-remove" @click="removeTag(tag)">×</button>
      </span>
      <input
        ref="inputRef"
        v-model="input"
        class="tag-text-input"
        placeholder="Ajouter… (séparer par une virgule)"
        @keydown="onKeydown"
      />
    </div>
    <div v-if="suggestions.length" class="tag-suggestions">
      <button
        v-for="s in suggestions"
        :key="s"
        type="button"
        class="tag-suggestion"
        @click="addTag(s)"
      >{{ s }}</button>
    </div>
  </div>
</template>

<style scoped>
.tag-input-wrap { position: relative; }
.tag-chips {
  display: flex; flex-wrap: wrap; gap: 5px; align-items: center;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 5px 8px; background: var(--surface); min-height: 34px;
  cursor: text;
}
.tag-chip {
  display: flex; align-items: center; gap: 4px;
  background: var(--primary-light); color: var(--primary);
  border-radius: 12px; padding: 2px 8px;
  font-size: 0.78rem; font-weight: 600;
}
.tag-remove {
  background: none; border: none; cursor: pointer;
  color: var(--primary); font-size: 1rem; line-height: 1; padding: 0;
}
.tag-text-input {
  border: none; outline: none; flex: 1; min-width: 100px;
  font-size: 0.8125rem; font-family: var(--font);
  background: transparent; color: var(--text);
}
.tag-suggestions {
  position: absolute; bottom: calc(100% + 4px); left: 0; right: 0;
  background: var(--surface-raised); border: 1px solid var(--border);
  border-radius: var(--radius-sm); box-shadow: var(--shadow-lg);
  z-index: 100; display: flex; flex-direction: column;
}
.tag-suggestion {
  background: none; border: none; text-align: left;
  padding: 7px 10px; font-size: 0.8125rem; cursor: pointer;
  color: var(--text); font-family: var(--font);
}
.tag-suggestion:hover { background: var(--light); }
</style>
