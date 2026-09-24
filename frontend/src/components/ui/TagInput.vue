<script setup>
import { ref, computed } from 'vue'
import { tomesApi } from '../../api/tomes'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // Étiquettes personnelles (usage d'origine) : va chercher elle-même la liste via
  // tomesApi.getTags(). Passer une liste ici (auteurs, éditeurs, genres…) court-circuite ce
  // fetch — permet de réutiliser le même composant "badges + autocomplétion" pour d'autres
  // champs multi-valeurs que les étiquettes (voir MetadataForm.vue/SeriesMetadataModal.vue).
  suggestions: { type: Array, default: null },
  placeholder: { type: String, default: 'Ajouter… (séparer par une virgule)' },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// Une fois au moins une entrée saisie, le placeholder (qui répète le nom du champ, ex.
// "Ajouter un scénariste…") devient redondant à côté du badge déjà là — masqué dans ce cas,
// le champ reste actif pour en ajouter d'autres.
const effectivePlaceholder = computed(() => props.modelValue.length ? '' : props.placeholder)

const input = ref('')
const allTags = ref([])
const inputRef = ref(null)

if (props.suggestions === null) {
  tomesApi.getTags().then(({ data }) => { allTags.value = data })
}

const suggestions = computed(() => {
  if (!input.value.trim()) return []
  const pool = props.suggestions !== null ? props.suggestions : allTags.value
  const q = input.value.toLowerCase()
  return pool.filter(t =>
    t.toLowerCase().includes(q) && !props.modelValue.includes(t)
  ).slice(0, 6)
})

function addTag(tag) {
  if (props.readonly) return
  const t = (tag || input.value).trim()
  if (t && !props.modelValue.includes(t)) {
    emit('update:modelValue', [...props.modelValue, t])
  }
  input.value = ''
  inputRef.value?.focus()
}

function removeTag(tag) {
  if (props.readonly) return
  emit('update:modelValue', props.modelValue.filter(t => t !== tag))
}

function onKeydown(e) {
  if (props.readonly) return
  if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); e.stopPropagation(); addTag() }
  if (e.key === 'Backspace' && !input.value && props.modelValue.length) {
    removeTag(props.modelValue[props.modelValue.length - 1])
  }
}
</script>

<template>
  <div class="tag-input-wrap">
    <div class="tag-chips" :class="{ readonly }">
      <span v-for="tag in modelValue" :key="tag" class="tag-chip">
        {{ tag }}
        <button v-if="!readonly" type="button" class="tag-remove" @click="removeTag(tag)">×</button>
      </span>
      <input
        v-if="!readonly"
        ref="inputRef"
        v-model="input"
        class="tag-text-input"
        :placeholder="effectivePlaceholder"
        @keydown="onKeydown"
      />
    </div>
    <div v-if="!readonly && suggestions.length" class="tag-suggestions">
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
.tag-chips.readonly { background: var(--light); cursor: default; }
.tag-chip {
  display: flex; align-items: center; gap: 4px;
  background: var(--vermilion-light); color: var(--vermilion);
  border-radius: 12px; padding: 2px 8px;
  font-size: 0.78rem; font-weight: 600;
}
/* Plus petite que le texte du badge et recentrée verticalement (flex, pas juste line-height)
   — trop proche visuellement du texte auparavant (même taille, même couleur pleine),
   difficile à distinguer d'une lettre du badge. Opacité + fond au survol pour la détacher
   davantage encore. */
.tag-remove {
  display: flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; flex-shrink: 0;
  background: none; border: none; border-radius: 50%; cursor: pointer;
  color: var(--vermilion); font-size: 0.7rem; line-height: 1; padding: 0;
  opacity: 0.6; transition: opacity 0.12s, background 0.12s;
}
.tag-remove:hover { opacity: 1; background: rgba(217,65,30,.18); }
.tag-text-input {
  /* min-width volontairement faible : un badge déjà présent masque le placeholder
     (effectivePlaceholder), donc ce champ n'a besoin que de place pour taper, pas d'afficher
     un texte d'exemple — une valeur haute ici forçait un retour à la ligne (et donc une boîte
     plus haute) dès qu'un badge un peu long ne laissait plus assez de place. */
  border: none; outline: none; flex: 1; min-width: 40px;
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
