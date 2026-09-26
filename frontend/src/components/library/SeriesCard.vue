<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import SvgIcon from '../SvgIcon.vue'
import { useAuthStore } from '../../stores/auth'
import SeriesActionsMenu from './SeriesActionsMenu.vue'

const props = defineProps({
  series: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  selectMode: { type: Boolean, default: false },
})
const emit = defineEmits(['edit', 'enrich', 'rename', 'convert', 'download', 'set-cover', 'toggle-hidden', 'delete', 'toggle-select'])

const authStore = useAuthStore()
const canMenu = computed(() => ['library.metadata_edit', 'library.rename', 'library.convert', 'library.download', 'library.delete']
  .some(p => authStore.hasPermission(p)))

const router = useRouter()
const imgRef = ref(null)
const imgSrc = ref(null)
const menuOpen = ref(false)
const cardHovered = ref(false)

onMounted(() => {
  const observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        imgSrc.value = props.series.cover_url
        observer.disconnect()
      }
    },
    { rootMargin: '120px' }
  )
  if (imgRef.value) observer.observe(imgRef.value)
})

// Mettre à jour l'image si la cover change (ex: après modification de la miniature)
watch(() => props.series.cover_url, (newUrl) => {
  if (newUrl) imgSrc.value = newUrl
})
</script>

<template>
  <div
    class="series-card"
    :class="{ 'series-card-hidden': series.hidden, 'menu-open': menuOpen, 'series-card-selected': selected }"
    :title="series.name"
    @mouseenter="cardHovered = true"
    @mouseleave="cardHovered = false"
  >
    <!-- Cover : overflow visible pour que le menu dépasse, image clippée par un inner wrapper -->
    <div ref="imgRef" class="series-cover" @click="router.push(`/series/${series.id}`)">
      <!-- Image clippée dans son propre wrapper -->
      <div class="series-cover-clip">
        <img
          v-if="imgSrc"
          :src="imgSrc"
          :alt="series.name"
          class="series-cover-img"
          loading="lazy"
          @error="imgSrc = null"
        />
        <div v-else class="series-cover-placeholder">📖</div>
        <!-- Fond sombre au hover — clippé avec l'image, masqué en mode sélection (rien à
             mettre en avant par-dessus, la case à cocher doit rester bien lisible) -->
        <div v-if="(cardHovered || menuOpen) && !selectMode" class="series-cover-dim"></div>
      </div>

      <!-- Sélection multiple — visible UNIQUEMENT si le mode "Sélectionner" est actif (barre
           du haut) : pas de sélection possible autrement, même au survol. -->
      <button
        v-if="selectMode"
        class="series-select"
        :class="{ 'series-select-active': selected }"
        :title="selected ? 'Désélectionner' : 'Sélectionner'"
        @click.stop="$emit('toggle-select', series)"
      ></button>

      <span v-if="!selectMode" class="series-badge">{{ series.tome_count }}</span>

      <!-- Boutons en bas de la cover, hors du clip, visibles si hover OU menu ouvert — masqués
           une fois la série sélectionnée ou en mode sélection, pour se concentrer sur la
           case à cocher. -->
      <div v-if="(cardHovered || menuOpen) && !selected && !selectMode" class="series-overlay" @click.stop>
        <button v-if="authStore.hasPermission('library.metadata_edit')" class="overlay-btn" title="Modifier les métadonnées" @click="$emit('edit', series)">
          <SvgIcon name="edit" style="font-size:20px" />
        </button>
        <div class="overlay-spacer"></div>
        <SeriesActionsMenu
          v-if="canMenu" v-model:open="menuOpen" :series="series"
          @edit="$emit('edit', $event)" @enrich="$emit('enrich', $event)" @rename="$emit('rename', $event)"
          @convert="$emit('convert', $event)" @download="$emit('download', $event)" @set-cover="$emit('set-cover', $event)"
          @toggle-hidden="$emit('toggle-hidden', $event)" @delete="$emit('delete', $event)"
        >
          <button class="overlay-btn" :class="{ 'overlay-btn-active': menuOpen }" title="Plus d'options">
            <SvgIcon name="more-vertical" style="font-size:20px" />
          </button>
        </SeriesActionsMenu>
      </div>
    </div>

    <!-- Info -->
    <div class="series-info" @click="router.push(`/series/${series.id}`)">
      <p class="series-name">{{ series.name }}</p>
      <p class="series-count">{{ series.tome_count }} album{{ series.tome_count !== 1 ? 's' : '' }}</p>
    </div>
  </div>
</template>

<style scoped>
.series-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: visible;
  transition: box-shadow 0.18s, transform 0.18s;
  box-shadow: var(--shadow-sm);
  position: relative;
  z-index: 1;
}
.series-card:hover {
  box-shadow: 0 0 0 1.5px var(--primary), var(--shadow-lg);
  transform: translateY(-2px);
  /* Juste assez pour passer au-dessus des cards voisines (z-index:1) — jamais au-dessus
     de la barre du haut (z-index:40, sticky) sous peine de la traverser au survol. */
  z-index: 2;
}
.series-card.menu-open {
  z-index: 6;
}

.series-cover {
  aspect-ratio: 0.71;
  position: relative;
  cursor: pointer;
  overflow: visible; /* laisser le menu dépasser */
}

/* Wrapper qui clippe l'image — couvre toute la zone cover */
.series-cover-clip {
  position: absolute; inset: 0;
  overflow: hidden;
  border-radius: var(--radius) var(--radius) 0 0;
  background: var(--light);
}
.series-cover-img {
  width: 100%; height: 100%;
  object-fit: cover; display: block;
  transition: transform 0.3s ease;
}
.series-card:hover .series-cover-img { transform: scale(1.04); }

.series-cover-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  font-size: 2.5rem; color: var(--placeholder);
}

.series-cover-dim {
  position: absolute; inset: 0; z-index: 2;
  background: rgba(0,0,0,0.45);
  pointer-events: none;
}

.series-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  min-width: 24px; height: 24px; padding: 0 5px;
  background: rgba(255,255,255,0.92); color: #212121;
  font-size: 0.72rem; font-weight: 700;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
}

.series-select {
  position: absolute; top: 6px; left: 6px; z-index: 4;
  width: 19px; height: 19px; border-radius: 50%;
  /* Fond semi-opaque : un simple contour blanc se fondait dans les covers claires, surtout
     maintenant que la case reste affichée en permanence (mode "Sélectionner") et non plus
     seulement au survol. */
  background: rgba(0,0,0,0.4); border: 1.5px solid #fff;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
  cursor: pointer; padding: 0;
  display: flex; align-items: center; justify-content: center;
  transition: border-color 0.12s, background 0.12s, transform 0.1s;
}
.series-select:hover { transform: scale(1.15); }
.series-select-active { border-color: var(--vermilion); background: var(--vermilion); }
.series-select-active::after {
  content: '✓';
  color: #fff; font-size: 10px; font-weight: 700; line-height: 1;
}
.series-card-selected { box-shadow: 0 0 0 1.5px var(--primary); }

/* Overlay boutons — en bas de .series-cover, hors du clip */
.series-overlay {
  position: absolute;
  left: 0; right: 0;
  bottom: 8px;
  height: 36px;
  z-index: 10;
  display: flex; align-items: center;
  padding: 0 8px;
}
.overlay-spacer { flex: 1; }

.series-info {
  padding: 8px 10px 6px;
  border-top: 1px solid var(--border);
  cursor: pointer;
}
.series-name {
  font-size: 0.8125rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  max-height: 2.7em;
}
.series-count { font-size: 0.75rem; color: var(--muted); }

.series-card-hidden .series-cover-img,
.series-card-hidden .series-cover-placeholder { opacity: 0.4; filter: grayscale(40%); }
</style>
