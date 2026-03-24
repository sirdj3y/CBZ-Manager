<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import SvgIcon from '../SvgIcon.vue'

const props = defineProps({
  series: { type: Object, required: true },
})
const emit = defineEmits(['edit', 'rename', 'convert', 'set-cover', 'toggle-hidden', 'delete'])

const router = useRouter()
const imgRef = ref(null)
const imgSrc = ref(null)
const menuOpen = ref(false)
const menuRef = ref(null)
const menuLeft = ref(false)
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
  document.addEventListener('mousedown', onClickOutside)
})
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))

function onClickOutside(e) {
  if (menuOpen.value && menuRef.value && !menuRef.value.contains(e.target)) {
    menuOpen.value = false
  }
}

function toggleMenu(e) {
  menuLeft.value = e.clientX > window.innerWidth * 0.66
  menuOpen.value = !menuOpen.value
}

// Mettre à jour l'image si la cover change (ex: après modification de la miniature)
watch(() => props.series.cover_url, (newUrl) => {
  if (newUrl) imgSrc.value = newUrl
})
</script>

<template>
  <div
    class="series-card"
    :class="{ 'series-card-hidden': series.hidden, 'menu-open': menuOpen }"
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
        <!-- Fond sombre au hover — clippé avec l'image -->
        <div v-if="cardHovered || menuOpen" class="series-cover-dim"></div>
      </div>
      <span class="series-badge">{{ series.tome_count }}</span>

      <!-- Boutons en bas de la cover, hors du clip, visibles si hover OU menu ouvert -->
      <div v-if="cardHovered || menuOpen" class="series-overlay" @click.stop>
        <button class="overlay-btn" title="Modifier les métadonnées" @click="$emit('edit', series)">
          <SvgIcon name="edit" style="font-size:15px" />
        </button>
        <div class="overlay-spacer"></div>
        <div class="more-wrap" ref="menuRef">
          <button class="overlay-btn" :class="{ 'overlay-btn-active': menuOpen }" title="Plus d'options" @click="toggleMenu">
            <SvgIcon name="more" style="font-size:15px" />
          </button>
          <div v-if="menuOpen" class="more-menu" :class="{ 'more-menu-left': menuLeft }">
            <button class="more-item" @click="$emit('edit', series); menuOpen = false">Éditer les métadonnées</button>
            <button class="more-item" @click="$emit('rename', series); menuOpen = false">Renommer les fichiers</button>
            <button class="more-item" @click="$emit('convert', series); menuOpen = false">Convertir les fichiers</button>
            <button class="more-item" @click="$emit('set-cover', series); menuOpen = false">Modifier la miniature</button>
            <div class="more-divider"></div>
            <button class="more-item" @click="$emit('toggle-hidden', series); menuOpen = false">
              {{ series.hidden ? 'Afficher la série' : 'Masquer la série' }}
            </button>
            <button class="more-item more-item-danger" @click="$emit('delete', series); menuOpen = false">
              Supprimer la série
            </button>
          </div>
        </div>
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
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
  z-index: 50;
}
.series-card.menu-open {
  z-index: 200;
}

.series-cover {
  aspect-ratio: 2/3;
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
  background: rgba(0,0,0,0.32);
  pointer-events: none;
}

.series-badge {
  position: absolute; top: 6px; right: 6px; z-index: 3;
  min-width: 24px; height: 24px; padding: 0 5px;
  background: rgba(255,255,255,0.92); color: var(--text);
  font-size: 0.72rem; font-weight: 700;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
}

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

.overlay-btn {
  width: 30px; height: 30px; border-radius: 50%;
  background: var(--overlay-btn-bg); border: none; cursor: pointer;
  color: var(--text);
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, transform 0.12s;
  flex-shrink: 0;
}
.overlay-btn:hover { background: var(--surface); transform: scale(1.1); }
.overlay-btn-active { background: var(--surface); }

/* More dropdown */
.more-wrap { position: relative; }
.more-menu {
  position: absolute;
  top: calc(100% + 4px); left: 0;
  background: var(--surface-raised);
}
.more-menu.more-menu-left {
  left: auto; right: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  min-width: 190px;
  padding: 4px 0;
  z-index: 300;
}
.more-item {
  display: block;
  width: 100%; padding: 8px 14px;
  background: none; border: none; cursor: pointer;
  font-size: 0.8125rem; font-family: var(--font); color: var(--text);
  text-align: left;
  transition: background 0.1s;
  white-space: nowrap;
}
.more-item:hover { background: var(--light); }
.more-divider { height: 1px; background: var(--border); margin: 4px 0; }
.more-item-danger { color: var(--danger); }
.more-item-danger:hover { background: var(--danger-bg-light); }

.series-info {
  padding: 8px 10px 6px;
  border-top: 1px solid var(--border);
  cursor: pointer;
}
.series-name {
  font-size: 0.8125rem; font-weight: 600; color: var(--text);
  line-height: 1.3; margin-bottom: 2px;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.series-count { font-size: 0.75rem; color: var(--muted); }

.series-card-hidden .series-cover-img,
.series-card-hidden .series-cover-placeholder { opacity: 0.4; filter: grayscale(40%); }
</style>
