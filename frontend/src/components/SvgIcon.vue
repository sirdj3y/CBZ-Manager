<script setup>
import { computed } from 'vue'

// Dynamically import SVG as raw string and render inline
// Usage: <SvgIcon name="home" class="nav-icon" />
const props = defineProps({
  name: { type: String, required: true },
})

const modules = import.meta.glob('../assets/icons/*.svg', { query: '?raw', import: 'default', eager: true })

// computed pour réagir aux changements de props.name (ex: toggle dark/light)
const svg = computed(() => {
  const raw = modules[`../assets/icons/${props.name}.svg`] ?? ''
  return raw
    .replace(/(<svg[^>]*)\s+width="[^"]*"/, '$1')
    .replace(/(<svg[^>]*)\s+height="[^"]*"/, '$1')
    .replace(/fill="#[0-9a-fA-F]{3,6}"/g, 'fill="currentColor"')
    .replace(/fill="black"/gi, 'fill="currentColor"')
})
</script>

<template>
  <span class="svg-icon" v-html="svg" />
</template>

<style scoped>
.svg-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.svg-icon :deep(svg) {
  width: 1em;
  height: 1em;
  display: block;
}
</style>
