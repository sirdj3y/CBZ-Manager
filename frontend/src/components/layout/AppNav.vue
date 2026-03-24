<script setup>
import { ref } from 'vue'
import { useLibraryStore } from '../../stores/library'
import { useNotificationStore } from '../../stores/notifications'
import SvgIcon from '../SvgIcon.vue'

const library = useLibraryStore()
const notif = useNotificationStore()

const scanning = ref(false)

async function handleScan() {
  if (scanning.value) return
  scanning.value = true
  try {
    await library.triggerScan()
    notif.info('Scan lancé…')
  } catch {
    notif.error('Erreur lors du scan')
  } finally {
    scanning.value = false
  }
}
</script>

<template>
  <header class="navbar">
    <router-link to="/" class="navbar-brand">
      <span class="navbar-logo">📚</span>
      CBZManager
    </router-link>

    <span v-if="library.scanProgress.status === 'running'" class="navbar-scan-info">
      Scan {{ library.scanProgress.processed }}/{{ library.scanProgress.total }}
    </span>

    <div class="navbar-actions">
      <button
        @click="handleScan"
        :disabled="scanning || library.scanProgress.status === 'running'"
        class="btn btn-primary btn-sm"
        title="Scanner la bibliothèque"
      >
        <SvgIcon name="refresh" :class="{ 'spin': scanning }" style="font-size:14px;margin-right:4px" />
        Scanner
      </button>
      <router-link to="/settings" class="btn btn-ghost btn-icon" title="Paramètres">
        <SvgIcon name="settings" style="font-size:18px" />
      </router-link>
    </div>
  </header>
</template>

<style scoped>
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 16px;
  height: 56px;
  padding: 0 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.navbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 1.05rem;
  color: var(--text);
  text-decoration: none;
  flex-shrink: 0;
}
.navbar-brand:hover {
  text-decoration: none;
  color: var(--primary);
}

.navbar-logo { font-size: 1.2rem; }

.navbar-scan-info {
  font-size: 0.8125rem;
  color: var(--muted);
  white-space: nowrap;
  margin-right: auto;
}

.navbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 0.8s linear infinite; }
</style>
