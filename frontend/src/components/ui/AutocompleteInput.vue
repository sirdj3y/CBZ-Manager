<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  suggestions: { type: Array, default: () => [] },
  placeholder: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
  // Champ valeur unique (pas de liste comma-séparée type auteurs) : un clic sur le champ vide
  // affiche la liste complète triée A-Z, comme le combobox série de la page Import.
  showAllOnFocus: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const inputRef = ref(null)
const dropdownRef = ref(null)
const highlighted = ref(-1)
const dropdownStyle = ref({})

// Position calculée + Teleport plutôt que position:absolute classique — nécessaire dès que
// le champ se trouve dans un conteneur avec overflow contraint (tableau scrollable, modale
// avec corps scrollable...) sinon la liste de suggestions se retrouve coupée. Même technique
// que les autres menus de l'app dans ce cas de figure (cf. ImportView/ContentToolbar).
function updateDropdownPosition() {
  if (!inputRef.value) return
  const rect = inputRef.value.getBoundingClientRect()
  dropdownStyle.value = {
    top: (rect.bottom + 2) + 'px',
    left: rect.left + 'px',
    width: rect.width + 'px',
  }
}
// Ferme la liste au scroll d'un ancêtre (le champ se déplace, la position figée n'est plus
// valide) — mais pas quand c'est la liste elle-même qu'on scrolle, sinon impossible de la
// dérouler : l'écouteur en phase de capture se déclenche avant même d'atteindre sa cible.
function onScroll(e) {
  if (dropdownRef.value && (e.target === dropdownRef.value || dropdownRef.value.contains(e.target))) return
  open.value = false
}
onMounted(() => window.addEventListener('scroll', onScroll, true))
onUnmounted(() => window.removeEventListener('scroll', onScroll, true))

// Terme en cours de saisie = dernier segment après la dernière virgule — sauf en mode
// showAllOnFocus (champ valeur unique, cf. doc du prop) où la valeur entière est le terme,
// pour ne pas casser une valeur contenant une virgule littérale (ex: un titre de série).
function currentTerm() {
  const val = props.modelValue || ''
  if (props.showAllOnFocus) return val.trim().toLowerCase()
  const parts = val.split(',')
  return parts[parts.length - 1].trim().toLowerCase()
}

const filtered = computed(() => {
  const term = currentTerm()
  if (!term) {
    if (!props.showAllOnFocus) return []
    return [...props.suggestions].sort((a, b) => a.localeCompare(b, 'fr', { sensitivity: 'base' }))
  }
  const matches = props.suggestions.filter(s =>
    s.toLowerCase().includes(term) && s.toLowerCase() !== term
  )
  return props.showAllOnFocus ? matches : matches.slice(0, 8)
})

function onInput(e) {
  emit('update:modelValue', e.target.value)
  open.value = true
  highlighted.value = -1
  updateDropdownPosition()
}

function onFocus() {
  open.value = true
  updateDropdownPosition()
}

function select(suggestion) {
  if (props.showAllOnFocus) {
    emit('update:modelValue', suggestion)
    open.value = false
    highlighted.value = -1
    inputRef.value?.focus()
    return
  }
  const val = props.modelValue || ''
  const parts = val.split(',')
  parts[parts.length - 1] = ' ' + suggestion
  // Trim le premier élément si vide
  const joined = parts.map((p, i) => i === 0 ? p.trim() : p.trimStart()).join(',')
  emit('update:modelValue', joined)
  open.value = false
  highlighted.value = -1
  inputRef.value?.focus()
}

function onBlur() {
  // Délai pour laisser le clic sur suggestion se déclencher
  setTimeout(() => { open.value = false; highlighted.value = -1 }, 150)
}

// Navigation clavier dans la liste de suggestions — jusqu'ici sélection à la souris
// uniquement, incohérent avec le reste de l'app qui valide au clavier (Entrée/Échap).
function onKeydown(e) {
  if (!open.value || !filtered.value.length) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (e.key === 'Enter' && highlighted.value >= 0) {
    // Empêche la propagation vers le gestionnaire Entrée-pour-sauvegarder de la modale
    // parente : Entrée doit d'abord confirmer la suggestion surlignée, pas sauvegarder.
    e.preventDefault()
    e.stopPropagation()
    select(filtered.value[highlighted.value])
  } else if (e.key === 'Escape') {
    // Un premier Échap referme juste la liste de suggestions, pas toute la modale.
    e.stopPropagation()
    open.value = false
    highlighted.value = -1
  }
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
      @focus="onFocus"
      @blur="onBlur"
      @keydown="onKeydown"
    />
    <Teleport to="body">
      <ul v-if="open && filtered.length" ref="dropdownRef" class="autocomplete-list" :style="dropdownStyle">
        <li
          v-for="(s, i) in filtered"
          :key="s"
          :class="['autocomplete-item', { active: i === highlighted }]"
          @mousedown.prevent="select(s)"
          @mouseenter="highlighted = i"
        >{{ s }}</li>
      </ul>
    </Teleport>
  </div>
</template>

<style scoped>
.autocomplete-wrap {
  position: relative;
}

.autocomplete-list {
  position: fixed;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  list-style: none;
  margin: 0; padding: 4px 0;
  /* Au-dessus des popovers/menus shadcn (z 1000) : ce champ est utilisé dans le panneau de
     filtres (Popover) et dans des modales. */
  z-index: 1100;
  /* Une Dialog shadcn ouverte coupe les clics sur tout <body> (pointer-events: none) sauf
     sur elle-même : cette liste, rendue dans <body>, doit rester cliquable (voir AppDialog). */
  pointer-events: auto;
  max-height: 220px;
  overflow-y: auto;
}

.autocomplete-item {
  padding: 6px 12px;
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--text);
}
.autocomplete-item:hover,
.autocomplete-item.active {
  background: var(--primary-light);
  color: var(--primary);
}

.form-control.readonly {
  background-color: var(--light);
  cursor: default;
}
</style>
