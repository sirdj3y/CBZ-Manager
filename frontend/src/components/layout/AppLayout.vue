<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLibraryStore } from '../../stores/library'
import { useThemeStore } from '../../stores/theme'
import SvgIcon from '../SvgIcon.vue'

const router = useRouter()
const route = useRoute()
const library = useLibraryStore()

const themeStore = useThemeStore()
const sidebarOpen = ref(true)
const appVersion = __APP_VERSION__

const isSettingsActive = computed(() => route.path.startsWith('/settings') || route.path === '/logs' || route.path === '/settings/diagnostic')
const settingsOpen = ref(route.path.startsWith('/settings') || route.path === '/logs' || route.path === '/settings/diagnostic')
</script>

<template>
  <div class="app-shell">
    <!-- ── Sidebar ── -->
    <aside :class="['sidebar', { 'sidebar-collapsed': !sidebarOpen }]">
      <!-- Brand -->
      <div :class="['sidebar-brand', { 'sidebar-brand-collapsed': !sidebarOpen }]" @click="router.push('/')" style="cursor:pointer">
        <img src="/favicon.png" :class="['brand-icon', { 'brand-icon-collapsed': !sidebarOpen }]" alt="CBZ Manager" />
        <div v-if="sidebarOpen" class="brand-text">
          <span class="brand-name">CBZ Manager</span>
          <span class="brand-version">v{{ appVersion }}</span>
        </div>
      </div>

      <!-- Nav items -->
      <nav class="sidebar-nav">
        <router-link to="/" :class="['nav-item', { 'nav-item-active': route.path === '/' }]">
          <SvgIcon name="home" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Accueil</span>
        </router-link>
        <router-link to="/series" :class="['nav-item', { 'nav-item-active': route.path.startsWith('/series') }]">
          <SvgIcon name="serie" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Séries</span>
        </router-link>
        <router-link to="/books" :class="['nav-item', { 'nav-item-active': route.path === '/books' }]">
          <SvgIcon name="comic" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Albums</span>
        </router-link>
        <router-link to="/authors" :class="['nav-item', { 'nav-item-active': route.path === '/authors' }]">
          <SvgIcon name="author" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Auteurs</span>
        </router-link>
        <router-link to="/stats" :class="['nav-item', { 'nav-item-active': route.path === '/stats' }]">
          <SvgIcon name="stats" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Statistiques</span>
        </router-link>
        <router-link to="/import" :class="['nav-item', { 'nav-item-active': route.path === '/import' }]">
          <SvgIcon name="upload" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Importer</span>
        </router-link>
      </nav>

      <!-- Separator -->
      <div class="sidebar-sep" />

      <!-- Config / Déconnexion -->
      <nav class="sidebar-nav sidebar-nav-bottom">
        <button class="nav-item nav-item-btn" @click="themeStore.toggle()" :title="themeStore.isDark ? 'Mode clair' : 'Mode sombre'">
          <SvgIcon :name="themeStore.isDark ? 'dark-mode-off' : 'dark-mode-on'" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">{{ themeStore.isDark ? 'Mode clair' : 'Mode sombre' }}</span>
        </button>
        <!-- Configuration toggle -->
        <button :class="['nav-item', 'nav-item-btn', { 'nav-item-active': isSettingsActive }]" @click="settingsOpen = !settingsOpen">
          <SvgIcon name="settings" class="nav-icon" />
          <span v-if="sidebarOpen" class="nav-label">Configuration</span>
          <SvgIcon v-if="sidebarOpen" :name="settingsOpen ? 'chevron-up' : 'chevron-down'" class="nav-chevron" />
        </button>
        <!-- Configuration sub-menu -->
        <template v-if="settingsOpen">
          <router-link to="/settings/library" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/library', 'nav-sub-item-collapsed': !sidebarOpen }]">
            <SvgIcon name="library" class="nav-icon nav-icon-sub" />
            <span v-if="sidebarOpen" class="nav-label">Bibliothèque</span>
          </router-link>
          <router-link to="/settings/data" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/data', 'nav-sub-item-collapsed': !sidebarOpen }]">
            <SvgIcon name="database" class="nav-icon nav-icon-sub" />
            <span v-if="sidebarOpen" class="nav-label">Sauvegarde &amp; BDD</span>
          </router-link>
          <router-link to="/settings/diagnostic" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/diagnostic', 'nav-sub-item-collapsed': !sidebarOpen }]">
            <SvgIcon name="health" class="nav-icon nav-icon-sub" />
            <span v-if="sidebarOpen" class="nav-label">Diagnostic</span>
          </router-link>
          <router-link to="/logs" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/logs', 'nav-sub-item-collapsed': !sidebarOpen }]">
            <SvgIcon name="history" class="nav-icon nav-icon-sub" />
            <span v-if="sidebarOpen" class="nav-label">Historique</span>
          </router-link>
          <router-link to="/settings/about" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/about', 'nav-sub-item-collapsed': !sidebarOpen }]">
            <SvgIcon name="info" class="nav-icon nav-icon-sub" />
            <span v-if="sidebarOpen" class="nav-label">À propos</span>
          </router-link>
        </template>
      </nav>
    </aside>

    <!-- ── Main area ── -->
    <div class="main-area">
      <!-- Top navbar -->
      <header class="topbar">
        <button class="btn btn-ghost btn-icon topbar-toggle" @click="sidebarOpen = !sidebarOpen" title="Menu">
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <rect y="2" width="18" height="2" rx="1" fill="currentColor"/>
            <rect y="8" width="18" height="2" rx="1" fill="currentColor"/>
            <rect y="14" width="18" height="2" rx="1" fill="currentColor"/>
          </svg>
        </button>
        <div class="topbar-search">
          <span class="search-icon">🔍</span>
          <input
            v-model="library.search"
            type="search"
            placeholder="Rechercher…"
            class="topbar-search-input"
          />
        </div>
        <!-- Scan status in topbar -->
        <span v-if="library.scanProgress.status === 'running'" class="topbar-scan">
          <SvgIcon name="refresh" class="spin" style="font-size:14px" />
          {{ library.scanProgress.processed }}/{{ library.scanProgress.total }}
        </span>
      </header>

      <!-- Scan progress bar -->
      <div v-if="library.scanProgress.status === 'running'" class="scan-bar">
        <div
          class="scan-bar-fill"
          :style="{ width: library.scanProgress.total ? `${(library.scanProgress.processed / library.scanProgress.total) * 100}%` : '5%' }"
        />
      </div>

      <!-- Page content -->
      <slot />
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}

/* ── Sidebar ── */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.2s ease;
  z-index: 50;
}
.sidebar-collapsed {
  width: 52px;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
  min-height: var(--navbar-h);
  flex-shrink: 0;
}
.brand-icon { width: 48px; height: 48px; flex-shrink: 0; object-fit: contain; }
.brand-icon-collapsed { width: 28px; height: 28px; }
.sidebar-brand-collapsed { justify-content: center; padding: 12px 0; }
.brand-text { display: flex; flex-direction: column; gap: 1px; overflow: hidden; }
.brand-name { font-weight: 700; font-size: 1rem; color: var(--text); white-space: nowrap; overflow: hidden; }
.brand-version { font-size: 0.7rem; color: var(--muted); white-space: nowrap; overflow: hidden; }

.sidebar-nav {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
  gap: 2px;
}
.sidebar-nav-bottom {
  margin-top: auto;
  padding-bottom: 12px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.sidebar-sep { flex: 1; }

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text);
  border-radius: 0;
  cursor: pointer;
  text-decoration: none;
  transition: background-color 0.12s;
  white-space: nowrap;
  overflow: hidden;
  border: none;
  background: none;
  font-family: var(--font);
  width: 100%;
  text-align: left;
}
.nav-item:hover { background: var(--sidebar-hover); text-decoration: none; }
.nav-item-active { background: var(--sidebar-active) !important; color: var(--primary); }
.nav-item-active .nav-icon { color: var(--primary); }
.nav-item-btn { color: var(--muted); }

.nav-icon { width: 22px; height: 22px; font-size: 22px; flex-shrink: 0; color: currentColor; }
.nav-label { white-space: nowrap; overflow: hidden; flex: 1; }
.nav-chevron { width: 14px; height: 14px; font-size: 14px; flex-shrink: 0; color: var(--muted); margin-left: auto; }
.nav-sub-item { padding-left: 24px; font-size: 0.82rem; color: var(--muted); }
.nav-sub-item-collapsed { padding-left: 14px; justify-content: center; }
.nav-sub-item:hover { color: var(--text); }
.nav-sub-item.nav-item-active { color: var(--primary); }
.nav-icon-sub { width: 18px; height: 18px; font-size: 18px; }

/* ── Main area ── */
.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ── Topbar ── */
.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--navbar-h);
  padding: 0 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.topbar-toggle { color: var(--muted); flex-shrink: 0; }
.topbar-toggle:hover { color: var(--text); }

.topbar-search {
  flex: 1;
  max-width: 480px;
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 10px;
  font-size: 0.875rem;
  color: var(--muted);
  pointer-events: none;
}
.topbar-search-input {
  width: 100%;
  padding: 6px 12px 6px 32px;
  font-family: var(--font);
  font-size: 0.875rem;
  color: var(--text);
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
  appearance: none;
}
.topbar-search-input:focus {
  outline: none;
  background: var(--surface);
  border-color: var(--primary-focus-border);
  box-shadow: 0 0 0 3px var(--primary-focus);
}
.topbar-search-input::placeholder { color: var(--placeholder); }

.topbar-scan {
  margin-left: auto;
  font-size: 0.8rem;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 5px;
}

/* Scan progress bar */
.scan-bar {
  height: 3px;
  background: var(--border);
  flex-shrink: 0;
}
.scan-bar-fill {
  height: 100%;
  background: var(--primary);
  transition: width 0.4s ease;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 0.9s linear infinite; }
</style>
