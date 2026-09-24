<script setup>
import { ref, computed, watch } from 'vue'
import { useAuthStore } from '../../stores/auth'

const props = defineProps({
  size: { type: Number, default: 28 },
})

const auth = useAuthStore()
// L'échec de chargement (avatar supprimé ailleurs, cache-buster pas encore à jour, etc.)
// bascule sur les initiales plutôt que de laisser une icône cassée — reset à chaque
// changement de version/compte pour retenter le prochain avatar.
const imgError = ref(false)
watch(() => [auth.avatarVersion, auth.username], () => { imgError.value = false })

const hasPhoto = computed(() => auth.avatarVersion > 0 && !imgError.value)
const avatarUrl = computed(() => `/api/auth/avatar?v=${auth.avatarVersion}`)
const initial = computed(() => (auth.username || '?').charAt(0).toUpperCase())
</script>

<template>
  <div
    class="user-avatar"
    :style="{ width: props.size + 'px', height: props.size + 'px', fontSize: (props.size * 0.42) + 'px' }"
  >
    <img v-if="hasPhoto" :src="avatarUrl" alt="" class="user-avatar-img" @error="imgError = true" />
    <span v-else class="user-avatar-initial">{{ initial }}</span>
  </div>
</template>

<style scoped>
.user-avatar {
  flex-shrink: 0;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary);
  color: #fff;
  font-weight: 700;
  font-family: var(--font);
}
.user-avatar-img { width: 100%; height: 100%; object-fit: cover; }
</style>
