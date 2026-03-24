<script setup>
import SeriesCard from './SeriesCard.vue'
defineProps({ series: Array })
</script>

<template>
  <div class="series-grid">
    <SeriesCard v-for="s in series" :key="s.id" :series="s" />
  </div>
</template>

<style scoped>
.series-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  padding: 20px;
}

@media (min-width: 480px) {
  .series-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (min-width: 768px) {
  .series-grid { grid-template-columns: repeat(4, 1fr); }
}
@media (min-width: 1024px) {
  .series-grid { grid-template-columns: repeat(5, 1fr); }
}
@media (min-width: 1280px) {
  .series-grid { grid-template-columns: repeat(6, 1fr); }
}
@media (min-width: 1600px) {
  .series-grid { grid-template-columns: repeat(8, 1fr); }
}
</style>
