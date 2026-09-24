<script setup>
import { ref } from 'vue'

const props = defineProps({
  modelValue: { type: Number, default: 0 },
  readonly: { type: Boolean, default: false },
  size: { type: String, default: '1.3rem' },
})
const emit = defineEmits(['update:modelValue'])

// Survolée : remplit aussi toutes les étoiles précédentes (comportement standard d'une
// notation par étoiles), pas seulement celle sous le curseur.
const hovered = ref(0)

function setRating(n) {
  if (!props.readonly) emit('update:modelValue', n === props.modelValue ? 0 : n)
}
function onEnter(n) {
  if (!props.readonly) hovered.value = n
}
</script>

<template>
  <div class="stars" :class="{ 'stars-readonly': readonly }" :style="{ fontSize: size }" @mouseleave="hovered = 0">
    <button
      v-for="n in 5"
      :key="n"
      type="button"
      class="star-btn"
      :class="{ filled: n <= (hovered || modelValue) }"
      @click="setRating(n)"
      @mouseenter="onEnter(n)"
      :disabled="readonly"
    >★</button>
  </div>
</template>

<style scoped>
/* Pas de gap — .bd-stars (page album) rend 5 glyphes ★ dans une seule chaîne de texte,
   sans espacement ajouté entre eux ; un gap ici créait un espacement visiblement plus
   large entre les étoiles "Ma note" qu'entre celles de Bedetheque.com. */
.stars { display: flex; gap: 0; }
.star-btn {
  background: none; border: none; cursor: pointer;
  /* Un <button> n'hérite pas la font-family du body par défaut (police système du
     formulaire) — sans ce reset, le glyphe ★ rend dans une police différente de
     .bd-stars (span, hérite normalement), donc visuellement pas de la même taille
     même à font-size identique. */
  font-family: inherit;
  font-size: inherit; line-height: 1; padding: 0;
  color: var(--star-empty);
  transition: color 0.1s, transform 0.1s;
}
.star-btn.filled { color: var(--star-filled); }
.star-btn:not(:disabled):hover { transform: scale(1.15); }
.stars-readonly .star-btn { cursor: default; }
</style>
