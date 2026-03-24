<script setup>
const props = defineProps({
  modelValue: { type: Number, default: 0 },
  readonly: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function setRating(n) {
  if (!props.readonly) emit('update:modelValue', n === props.modelValue ? 0 : n)
}
</script>

<template>
  <div class="stars" :class="{ 'stars-readonly': readonly }">
    <button
      v-for="n in 5"
      :key="n"
      type="button"
      class="star-btn"
      :class="{ filled: n <= modelValue }"
      @click="setRating(n)"
      :disabled="readonly"
    >★</button>
  </div>
</template>

<style scoped>
.stars { display: flex; gap: 2px; }
.star-btn {
  background: none; border: none; cursor: pointer;
  font-size: 1.3rem; line-height: 1; padding: 0;
  color: var(--star-empty);
  transition: color 0.1s, transform 0.1s;
}
.star-btn.filled { color: var(--star-filled); }
.star-btn:not(:disabled):hover { color: #f59e0b; transform: scale(1.15); }
.stars-readonly .star-btn { cursor: default; }
</style>
