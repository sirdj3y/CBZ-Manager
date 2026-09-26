<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useLibraryStore } from '../../stores/library'
import { useThemeStore } from '../../stores/theme'
import { useMissingAlbumsStore } from '../../stores/missingAlbums'
import { useSecurityAlertsStore } from '../../stores/securityAlerts'
import { useNewContentStore } from '../../stores/newContent'
import { useAuthStore } from '../../stores/auth'
import { useSmartListsStore } from '../../stores/smartLists'
import { useNotificationStore } from '../../stores/notifications'
import { smartListsApi } from '../../api/smartLists'
import client from '../../api/client'
import SvgIcon from '../SvgIcon.vue'
import UserAvatar from '../account/UserAvatar.vue'
import ChangePasswordModal from '../account/ChangePasswordModal.vue'
import SmartListEditModal from '../library/SmartListEditModal.vue'
import GlobalSearchModal from './GlobalSearchModal.vue'
import { buildInfo, formatBuildDate } from '../../utils/buildInfo'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/shadcn/popover'
import Hint from '../ui/Hint.vue'

const router = useRouter()
const route = useRoute()
const library = useLibraryStore()
const missingAlbumsStore = useMissingAlbumsStore()
const securityAlertsStore = useSecurityAlertsStore()
const newContentStore = useNewContentStore()
const authStore = useAuthStore()
const smartListsStore = useSmartListsStore()
const notif = useNotificationStore()

async function doLogout() {
  await authStore.logout()
  // Rechargement complet plutôt qu'une navigation SPA — voir LoginView.vue pour le
  // raisonnement (stores Pinia jamais réinitialisés entre deux sessions dans le même onglet).
  window.location.href = '/login'
}

const themeStore = useThemeStore()
// Persisté (comme le thème) — AppLayout est recréé à chaque navigation (voir plus bas),
// un simple ref(true) oubliait donc l'état replié à chaque changement de page.
const SIDEBAR_KEY = 'cmw-sidebar-open'
const sidebarOpen = ref(localStorage.getItem(SIDEBAR_KEY) !== '0')
// Tiroir mobile : distinct du collapse desktop (sidebarOpen), car sur petit écran
// le menu est soit masqué hors-écran, soit ouvert en plein (jamais en mode "icônes seules").
const mobileMenuOpen = ref(false)
const showLabels = computed(() => sidebarOpen.value || mobileMenuOpen.value)
const appVersion = __APP_VERSION__
// Préprod uniquement : date du build affichée discrètement sous la version, pour savoir si la
// dernière mise à jour poussée sur develop est bien arrivée (voir utils/buildInfo.js).
const preprodBuild = buildInfo.channel === 'preprod' && buildInfo.date
  ? { label: `préprod · ${formatBuildDate(buildInfo.date)}`, title: `Préprod construite le ${formatBuildDate(buildInfo.date, { withYear: true })} — commit ${buildInfo.sha}` }
  : null

// Recherche globale (Ctrl/Cmd+K, ou la "boîte" du topbar — voir plus bas) : point d'entrée
// unique, accessible depuis n'importe quelle page, pour chercher dans toute la bibliothèque
// (séries/albums/auteurs) d'un coup. Le raccourci clavier est intercepté au niveau window pour
// fonctionner même si le focus est ailleurs (champ de formulaire, etc.) — comportement
// standard (GitHub, Slack, Linear...).
const showGlobalSearch = ref(false)
const isMac = /Mac|iPod|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const searchShortcutLabel = isMac ? '⌘ K' : 'Ctrl K'
function onGlobalSearchShortcut(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    showGlobalSearch.value = true
  }
}
onMounted(() => window.addEventListener('keydown', onGlobalSearchShortcut))
onUnmounted(() => window.removeEventListener('keydown', onGlobalSearchShortcut))

// La "boîte de recherche" du topbar n'est plus un champ de filtre local (elle ne touche plus
// à library.search) : c'est un simple bouton qui ouvre la recherche globale — au clic, ou dès
// la première touche tapée si l'utilisateur se met à écrire sans cliquer d'abord (bouton
// focusable au clavier). Cette première touche est transmise au champ de la modale plutôt que
// perdue, pour ne pas donner l'impression qu'il a fallu la retaper.
const topbarSearchInitial = ref('')
function openGlobalSearchFromTopbar(initialChar = '') {
  topbarSearchInitial.value = initialChar
  showGlobalSearch.value = true
}
function onTopbarSearchKeydown(e) {
  // e.key.length === 1 : ne garde que les caractères imprimables (lettres, chiffres,
  // ponctuation, espace) — exclut "Enter", "Tab", "ArrowDown", etc.
  if (e.key.length !== 1 || e.ctrlKey || e.metaKey || e.altKey) return
  e.preventDefault()
  openGlobalSearchFromTopbar(e.key)
}

function toggleMenu() {
  if (window.innerWidth <= 768) {
    mobileMenuOpen.value = !mobileMenuOpen.value
  } else {
    sidebarOpen.value = !sidebarOpen.value
    localStorage.setItem(SIDEBAR_KEY, sidebarOpen.value ? '1' : '0')
  }
}

watch(() => route.path, () => { mobileMenuOpen.value = false })
watch(mobileMenuOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})
// AppLayout est recréé à chaque navigation (chaque vue l'inclut dans son propre template) —
// si le composant est démonté pendant que le tiroir est encore ouvert, le watcher ci-dessus
// peut ne jamais avoir la chance de remettre overflow à '', bloquant le scroll de la page
// suivante indéfiniment. Reset explicite et inconditionnel au démontage, par sécurité.
onUnmounted(() => { document.body.style.overflow = '' })

const isSettingsActive = computed(() => route.path.startsWith('/settings') || route.path === '/logs' || route.path === '/settings/diagnostic')
const settingsOpen = ref(route.path.startsWith('/settings') || route.path === '/logs' || route.path === '/settings/diagnostic')

const storageMismatch = ref(null)
async function checkStorage() {
  try {
    const { data } = await client.get('/api/health-check/storage')
    storageMismatch.value = data.mismatch
  } catch { /* pas bloquant */ }
}

onMounted(() => {
  // Recherche et filtres (auteur/dessinateur/éditeur/tag) sont un état global partagé par
  // toutes les pages — sans ce reset, une recherche tapée sur Séries ou un filtre posé en
  // cliquant un auteur depuis la page Auteurs (qui navigue vers /books?writer=...) restent
  // actifs en changeant de page, sans indicateur visible, et peuvent vider une liste à tort.
  // AppLayout est un composant enfant : son onMounted se déclenche avant celui de la page
  // qui l'utilise (ex. BooksView), donc ce reset n'efface jamais un filtre que la page en
  // cours de montage vient tout juste de positionner depuis l'URL.
  library.search = ''
  library.filters = {}
  missingAlbumsStore.refreshCount()
  if (authStore.hasPermission('library.settings')) securityAlertsStore.refresh()
  if (authStore.hasPermission('library.read')) newContentStore.refresh()
  checkStorage()
  // Compteurs du menu (Séries/Albums/Auteurs) — chargés une seule fois, réutilisés par
  // toutes les pages via le store partagé, pas un fetch à chaque navigation.
  if (!library.series.length) library.fetchSeries()
  if (!library.authors.authors.length) library.fetchAuthors()
  if (authStore.hasPermission('library.read') && !smartListsStore.loaded) smartListsStore.refresh()
})

const seriesCount = computed(() => library.series.length)
const albumsCount = computed(() => library.series.reduce((sum, s) => sum + (s.tome_count || 0), 0))
const authorsCount = computed(() => library.authors.authors.length)

// Menu "Scanner" global du topbar — regroupe les deux scans jusqu'ici dispersés (scan des
// fichiers de la bibliothèque, actualisation des métadonnées Bedetheque) dans un seul point
// d'entrée, accessible depuis n'importe quelle page (inspiré du menu "Scanner" de Plex).
const fileScanRunning = computed(() => library.scanProgress.status === 'running')
const metaScanRunning = computed(() => missingAlbumsStore.scanProgress.status === 'running' || missingAlbumsStore.scanProgress.status === 'pending')
const anyScanRunning = computed(() => fileScanRunning.value || metaScanRunning.value)

const showScanMenu = ref(false)

// Menus du topbar (Nouveautés, Scanner, Mon compte) et "⋮" des listes intelligentes :
// DropdownMenu de shadcn-vue (position, clic extérieur, clavier gérés par Reka UI).
const showAccountMenu = ref(false)

// Menu "Nouveautés" — même pattern, entre mode sombre et scanner. Ouvrir le menu marque
// tout comme vu (comportement standard d'une cloche de notifications) : le badge repasse à
// zéro immédiatement, pas besoin d'une action "tout marquer comme lu" séparée.
const showNotifMenu = ref(false)
watch(showNotifMenu, open => { if (open && newContentStore.count) newContentStore.markSeen() })
function openNotifItem(item) {
  showNotifMenu.value = false
  router.push(item.type === 'series' ? `/series/${item.id}` : `/tomes/${item.id}`)
}

// Listes intelligentes — section dépliable de la barre latérale (même pattern que
// Configuration) quand elle est dépliée, ou popover flottant ("flyout") en mode réduit
// (icônes seules, voir smartListsIconTriggerRef/flyoutOpen) où il n'y a pas la place
// d'afficher la liste en ligne. Seule surface de gestion (pas de page dédiée pour la liste
// des smart lists elles-mêmes — une fiche par liste existe via /collections/:id) : + pour
// créer, ⋮ par liste pour modifier/supprimer, glisser-déposer pour réordonner.
//
// Le flyout est téléporté dans <body> en position:fixed plutôt qu'un simple position:absolute
// dans .sidebar : .sidebar a overflow-x:hidden + overflow-y:auto (pour son propre scroll), qui
// le rognerait sinon. Les menus "⋮" sont des DropdownMenu (rendus hors de la sidebar par Reka UI).
const smartListsOpen = ref(false)
const confirmDeleteSmartList = ref(null)
const deletingSmartList = ref(false)
const duplicatingSmartList = ref(false)

// Id de la liste dont le menu "⋮" est ouvert (un seul à la fois).
const smartListMenuId = ref(null)
function setSmartListMenu(id, open) {
  if (open) smartListMenuId.value = id
  else if (smartListMenuId.value === id) smartListMenuId.value = null
}

const flyoutOpen = ref(false)
const smartListsIconTriggerRef = ref(null)

function onSmartListsToggleClick() {
  if (showLabels.value) {
    smartListsOpen.value = !smartListsOpen.value
    return
  }
  // Sidebar réduite (icônes seules) : pas de place pour déplier la liste en ligne, on
  // ouvre un popover flottant à côté de l'icône à la place (Popover, positionné par Reka UI).
  flyoutOpen.value = !flyoutOpen.value
}

function openCreateSmartList() {
  smartListsStore.openCreate()
  flyoutOpen.value = false
}
function openEditSmartList(sl) {
  smartListsStore.openEdit(sl)
  flyoutOpen.value = false
}
async function onSmartListSaved(payload) {
  smartListsStore.closeEditor()
  await smartListsStore.refresh()
  // Après une création (pas une édition — on reste déjà sur la page en cours le cas
  // échéant), direction la fiche de la nouvelle liste plutôt que de la laisser invisible
  // tant qu'on n'a pas pensé à la chercher dans le menu.
  if (payload?.isCreate && payload.list) {
    router.push(`/collections/${payload.list.id}`)
  }
}
async function duplicateSmartList(sl) {
  duplicatingSmartList.value = true
  try {
    const { data } = await smartListsApi.duplicate(sl.id)
    notif.success('Liste dupliquée')
    await smartListsStore.refresh()
    router.push(`/collections/${data.id}`)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la duplication')
  } finally {
    duplicatingSmartList.value = false
  }
}
async function doDeleteSmartList() {
  if (!confirmDeleteSmartList.value) return
  deletingSmartList.value = true
  try {
    await smartListsApi.remove(confirmDeleteSmartList.value.id)
    notif.success('Liste supprimée')
    if (route.path === `/collections/${confirmDeleteSmartList.value.id}`) router.push('/')
    await smartListsStore.refresh()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  } finally {
    deletingSmartList.value = false
    confirmDeleteSmartList.value = null
  }
}

// Glisser-déposer pour réordonner — réordonne le tableau local en direct pendant le survol
// (comportement standard d'une liste réorganisable), persiste côté serveur au lâcher. Marche
// aussi bien depuis la liste en ligne que depuis le flyout replié (mêmes fonctions).
const draggedListId = ref(null)
function onDragStart(sl) { draggedListId.value = sl.id }
function onDragOver(sl) {
  if (draggedListId.value === null || draggedListId.value === sl.id) return
  const list = smartListsStore.lists
  const fromIdx = list.findIndex(x => x.id === draggedListId.value)
  const toIdx = list.findIndex(x => x.id === sl.id)
  if (fromIdx === -1 || toIdx === -1) return
  const [moved] = list.splice(fromIdx, 1)
  list.splice(toIdx, 0, moved)
}
async function onDrop() {
  if (draggedListId.value === null) return
  draggedListId.value = null
  await smartListsStore.reorder(smartListsStore.lists.map(l => l.id))
}
function onDragEnd() { draggedListId.value = null }

// Clic hors du flyout : il se ferme, sauf sur l'icône qui l'ouvre (son propre clic le
// referme, sinon il se rouvrirait aussitôt) et dans un menu "⋮" ouvert depuis lui (rendu
// dans <body>, donc "hors" du flyout pour Reka UI).
function keepFlyoutOpen(e) {
  const t = e.target
  if (smartListsIconTriggerRef.value?.contains(t) || t?.closest?.('[data-slot="dropdown-menu-content"]')) e.preventDefault()
}

function triggerFileScan() {
  if (!fileScanRunning.value) library.triggerScan()
}
function triggerMetadataScan() {
  if (!metaScanRunning.value) missingAlbumsStore.triggerScan()
}
function openAccountPage() {
  router.push('/account')
}
function openChangePassword() {
  authStore.changePasswordOpen = true
}
function logoutFromMenu() {
  doLogout()
}

function fmtRelative(iso) {
  const diffMs = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return "à l'instant"
  if (min < 60) return `il y a ${min} min`
  const h = Math.floor(min / 60)
  if (h < 24) return `il y a ${h} h`
  const d = Math.floor(h / 24)
  return `il y a ${d} j`
}
</script>

<template>
  <div class="app-shell">
    <!-- ── Fond du tiroir mobile ── -->
    <div v-if="mobileMenuOpen" class="sidebar-backdrop" @click="mobileMenuOpen = false" />

    <!-- ── Sidebar ── -->
    <aside :class="['sidebar', { 'sidebar-collapsed': !sidebarOpen, 'sidebar-mobile-open': mobileMenuOpen }]">
      <!-- Brand -->
      <div :class="['sidebar-brand', { 'sidebar-brand-collapsed': !showLabels }]" @click="router.push('/')" style="cursor:pointer">
        <img src="/favicon.png" :class="['brand-icon', { 'brand-icon-collapsed': !showLabels }]" alt="CBZ Manager" />
        <div v-if="showLabels" class="brand-text">
          <span class="brand-name">CBZ Manager</span>
          <span class="brand-version">v{{ appVersion }}</span>
          <span v-if="preprodBuild" class="brand-build" :title="preprodBuild.title">{{ preprodBuild.label }}</span>
        </div>
      </div>

      <!-- Nav items -->
      <nav class="sidebar-nav">
        <router-link v-if="authStore.hasPermission('library.read')" to="/" :class="['nav-item', { 'nav-item-active': route.path === '/' }]">
          <SvgIcon name="home" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Accueil</span>
        </router-link>
        <router-link v-if="authStore.hasPermission('library.read')" to="/series" :class="['nav-item', { 'nav-item-active': route.path.startsWith('/series') }]">
          <SvgIcon name="serie" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Séries</span>
          <span v-if="showLabels && seriesCount" class="nav-count">{{ seriesCount }}</span>
        </router-link>
        <router-link v-if="authStore.hasPermission('library.read')" to="/books" :class="['nav-item', { 'nav-item-active': route.path === '/books' }]">
          <SvgIcon name="comic" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Albums</span>
          <span v-if="showLabels && albumsCount" class="nav-count">{{ albumsCount }}</span>
        </router-link>
        <router-link v-if="authStore.hasPermission('library.read')" to="/authors" :class="['nav-item', { 'nav-item-active': route.path === '/authors' }]">
          <SvgIcon name="author" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Auteurs</span>
          <span v-if="showLabels && authorsCount" class="nav-count">{{ authorsCount }}</span>
        </router-link>
        <template v-if="authStore.hasPermission('library.read')">
          <!-- Sidebar réduite : l'icône sert d'ancre au flyout (Popover) ; sidebar dépliée : elle
               déplie la liste en ligne ci-dessous (voir onSmartListsToggleClick). -->
          <Popover v-model:open="flyoutOpen">
            <PopoverAnchor as-child>
              <div
                class="nav-item smart-lists-toggle"
                ref="smartListsIconTriggerRef"
                @click="onSmartListsToggleClick"
              >
                <SvgIcon name="sparkles" class="nav-icon" />
                <span v-if="showLabels" class="nav-label">Smart list</span>
                <SvgIcon v-if="showLabels" :name="smartListsOpen ? 'chevron-up' : 'chevron-down'" class="nav-chevron smart-lists-chevron" />
                <Hint v-if="showLabels" label="Nouvelle liste">
                  <button class="nav-header-btn" @click.stop="openCreateSmartList">+</button>
                </Hint>
              </div>
            </PopoverAnchor>
            <PopoverContent
              side="right" align="start" :side-offset="8"
              class="w-auto border-0 bg-transparent p-0 shadow-none"
              @interact-outside="keepFlyoutOpen"
            >
              <div class="smart-lists-flyout">
                <div class="smart-lists-flyout-header">
                  <span class="smart-lists-flyout-title">Smart list</span>
                  <Hint label="Nouvelle liste">
                    <button class="nav-header-btn" @click="openCreateSmartList">+</button>
                  </Hint>
                </div>
                <p v-if="smartListsStore.loaded && !smartListsStore.lists.length" class="nav-empty-hint">Aucune liste</p>
                <div
                  v-for="sl in smartListsStore.lists" :key="sl.id"
                  class="smart-list-row"
                  :class="{ 'smart-list-row-dragging': draggedListId === sl.id }"
                  draggable="true"
                  @dragstart="onDragStart(sl)"
                  @dragover.prevent="onDragOver(sl)"
                  @drop="onDrop"
                  @dragend="onDragEnd"
                >
                  <router-link
                    :to="`/collections/${sl.id}`"
                    :title="sl.name"
                    :class="['nav-item', 'nav-sub-item', 'smart-list-link', { 'nav-item-active': route.path === `/collections/${sl.id}` }]"
                    @click="flyoutOpen = false"
                  >
                    <span class="nav-label">{{ sl.name }}</span>
                  </router-link>
                  <div class="nav-inline-menu-wrap">
                    <DropdownMenu :open="smartListMenuId === sl.id" :modal="false" @update:open="setSmartListMenu(sl.id, $event)">
                      <Hint label="Options">
                        <DropdownMenuTrigger as-child>
                          <button class="nav-header-btn nav-header-btn-sub">
                            <SvgIcon name="more-vertical" style="font-size:13px" />
                          </button>
                        </DropdownMenuTrigger>
                      </Hint>
                      <DropdownMenuContent align="end" class="min-w-[180px]">
                        <DropdownMenuItem v-if="sl.can_edit" @select="openEditSmartList(sl)">Modifier</DropdownMenuItem>
                        <DropdownMenuItem :disabled="duplicatingSmartList" @select="duplicateSmartList(sl)">{{ duplicatingSmartList ? 'Duplication…' : 'Dupliquer' }}</DropdownMenuItem>
                        <template v-if="sl.can_edit">
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive" @select="confirmDeleteSmartList = sl">Supprimer</DropdownMenuItem>
                        </template>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </div>
            </PopoverContent>
          </Popover>
          <!-- Sidebar dépliée : liste en ligne, dépliable/repliable. En mode réduit (icônes
               seules), pas de rendu ici — voir le flyout téléporté plus bas. -->
          <template v-if="smartListsOpen && showLabels">
            <p v-if="smartListsStore.loaded && !smartListsStore.lists.length" class="nav-empty-hint">Aucune liste</p>
            <div
              v-for="sl in smartListsStore.lists" :key="sl.id"
              class="smart-list-row"
              :class="{ 'smart-list-row-dragging': draggedListId === sl.id }"
              draggable="true"
              @dragstart="onDragStart(sl)"
              @dragover.prevent="onDragOver(sl)"
              @drop="onDrop"
              @dragend="onDragEnd"
            >
              <router-link
                :to="`/collections/${sl.id}`"
                :title="sl.name"
                :class="['nav-item', 'nav-sub-item', 'smart-list-link', { 'nav-item-active': route.path === `/collections/${sl.id}` }]"
              >
                <span class="nav-label">{{ sl.name }}</span>
              </router-link>
              <div class="nav-inline-menu-wrap">
                <DropdownMenu :open="smartListMenuId === sl.id" :modal="false" @update:open="setSmartListMenu(sl.id, $event)">
                  <Hint label="Options">
                    <DropdownMenuTrigger as-child>
                      <button class="nav-header-btn nav-header-btn-sub">
                        <SvgIcon name="more-vertical" style="font-size:13px" />
                      </button>
                    </DropdownMenuTrigger>
                  </Hint>
                  <DropdownMenuContent align="end" class="min-w-[180px]">
                    <DropdownMenuItem v-if="sl.can_edit" @select="openEditSmartList(sl)">Modifier</DropdownMenuItem>
                    <DropdownMenuItem :disabled="duplicatingSmartList" @select="duplicateSmartList(sl)">{{ duplicatingSmartList ? 'Duplication…' : 'Dupliquer' }}</DropdownMenuItem>
                    <template v-if="sl.can_edit">
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" @select="confirmDeleteSmartList = sl">Supprimer</DropdownMenuItem>
                    </template>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </template>
        </template>
        <router-link v-if="authStore.hasPermission('library.missing_albums')" to="/missing-albums" :class="['nav-item', { 'nav-item-active': route.path === '/missing-albums' }]">
          <SvgIcon name="search" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Albums manquants</span>
          <span v-if="missingAlbumsStore.count && showLabels" class="nav-count">{{ missingAlbumsStore.count > 99 ? '99+' : missingAlbumsStore.count }}</span>
        </router-link>
        <div class="nav-divider" />
        <router-link v-if="authStore.hasPermission('library.read')" to="/stats" :class="['nav-item', { 'nav-item-active': route.path === '/stats' }]">
          <SvgIcon name="stats" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Statistiques</span>
        </router-link>
        <router-link v-if="authStore.hasPermission('library.import')" to="/import" :class="['nav-item', { 'nav-item-active': route.path === '/import' }]">
          <SvgIcon name="upload" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Importer</span>
        </router-link>
      </nav>

      <!-- Configuration : visible pour l'admin ou tout profil avec library.settings (voir
           router/index.js et services/permissions.py). Comptes reste réservé à l'admin
           strictement (déléguer la création de comptes = auto-élévation possible), les autres
           pages sont accessibles par permission. Le bouton doit rester masqué pour qui n'a ni
           l'un ni l'autre — sinon il "s'ouvre" au clic sur un sous-menu vide, visuellement
           indiscernable d'un menu cassé. -->
      <template v-if="authStore.hasPermission('library.settings') || authStore.isAdmin">
      <!-- Separator -->
      <div class="sidebar-sep" />

      <!-- Configuration -->
      <nav class="sidebar-nav sidebar-nav-bottom">
        <!-- Configuration toggle -->
        <button :class="['nav-item', 'nav-item-btn', { 'nav-item-active': isSettingsActive }]" @click="settingsOpen = !settingsOpen">
          <SvgIcon name="settings" class="nav-icon" />
          <span v-if="showLabels" class="nav-label">Configuration</span>
          <SvgIcon v-if="showLabels" :name="settingsOpen ? 'chevron-up' : 'chevron-down'" class="nav-chevron" />
        </button>
        <!-- Configuration sub-menu -->
        <template v-if="settingsOpen">
          <router-link v-if="authStore.hasPermission('library.settings')" to="/settings/library" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/library' || route.path === '/settings/data', 'nav-sub-item-collapsed': !showLabels }]">
            <SvgIcon name="library" class="nav-icon nav-icon-sub" />
            <span v-if="showLabels" class="nav-label">Bibliothèque</span>
          </router-link>
          <router-link v-if="authStore.isAdmin" to="/settings/users" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/users' || route.path === '/settings/profiles', 'nav-sub-item-collapsed': !showLabels }]">
            <SvgIcon name="author" class="nav-icon nav-icon-sub" />
            <span v-if="showLabels" class="nav-label">Comptes</span>
          </router-link>
          <router-link v-if="authStore.hasPermission('library.settings')" to="/settings/diagnostic" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/diagnostic', 'nav-sub-item-collapsed': !showLabels }]">
            <SvgIcon name="health" class="nav-icon nav-icon-sub" />
            <span v-if="showLabels" class="nav-label">Diagnostic</span>
          </router-link>
          <router-link v-if="authStore.hasPermission('library.settings')" to="/logs" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/logs', 'nav-sub-item-collapsed': !showLabels }]">
            <SvgIcon name="history" class="nav-icon nav-icon-sub" />
            <span v-if="showLabels" class="nav-label">Historique</span>
            <span v-if="securityAlertsStore.alerts.length && showLabels" class="nav-count nav-count-alert">{{ securityAlertsStore.alerts.length }}</span>
          </router-link>
          <router-link v-if="authStore.hasPermission('library.settings')" to="/settings/about" :class="['nav-item', 'nav-sub-item', { 'nav-item-active': route.path === '/settings/about', 'nav-sub-item-collapsed': !showLabels }]">
            <SvgIcon name="info" class="nav-icon nav-icon-sub" />
            <span v-if="showLabels" class="nav-label">À propos</span>
          </router-link>
        </template>
      </nav>
      </template>
    </aside>

    <!-- ── Main area ── -->
    <div class="main-area">
      <!-- Top navbar -->
      <header class="topbar">
        <Hint label="Menu">
          <button class="btn btn-ghost btn-icon topbar-toggle" @click="toggleMenu">
            <SvgIcon name="panel-left" style="font-size:18px" />
          </button>
        </Hint>
        <div class="topbar-search">
          <SvgIcon name="search" class="search-icon" />
          <!-- Simple bouton (pas un champ de filtre) : clic OU première touche tapée ouvrent
               la recherche globale (voir GlobalSearchModal.vue) — plus de filtrage local de
               la page courante ici. -->
          <button
            type="button"
            class="topbar-search-input topbar-search-btn"
            @click="openGlobalSearchFromTopbar()"
            @keydown="onTopbarSearchKeydown"
          >
            <span class="topbar-search-placeholder">Rechercher un album, une série, un auteur…</span>
            <span class="topbar-search-kbd">{{ searchShortcutLabel }}</span>
          </button>
        </div>
        <div class="topbar-actions">
          <!-- Scan status in topbar -->
          <span v-if="fileScanRunning" class="topbar-scan">
            {{ library.scanProgress.processed }}/{{ library.scanProgress.total }}
          </span>
          <span v-else-if="metaScanRunning" class="topbar-scan">
            {{ missingAlbumsStore.scanProgress.processed }}/{{ missingAlbumsStore.scanProgress.total }}
          </span>

          <!-- Mode sombre -->
          <Hint :label="themeStore.isDark ? 'Mode clair' : 'Mode sombre'">
            <button class="btn btn-ghost btn-icon topbar-theme-toggle" @click="themeStore.toggle()">
              <SvgIcon :name="themeStore.isDark ? 'dark-mode-off' : 'dark-mode-on'" style="font-size:18px" />
            </button>
          </Hint>

          <!-- Menu "Nouveautés" -->
          <DropdownMenu v-if="authStore.hasPermission('library.read')" v-model:open="showNotifMenu" :modal="false">
            <Hint label="Nouveautés">
              <DropdownMenuTrigger as-child>
                <button
                  class="btn btn-ghost btn-icon topbar-notif-trigger"
                  :class="{ 'topbar-scan-btn-active': showNotifMenu }"
                >
                  <SvgIcon name="bell" style="font-size:18px" />
                  <span v-if="newContentStore.count" class="topbar-notif-badge">{{ newContentStore.count > 99 ? '99+' : newContentStore.count }}</span>
                </button>
              </DropdownMenuTrigger>
            </Hint>
            <DropdownMenuContent align="end" class="max-h-[400px] w-[340px] max-w-[calc(100vw-16px)] overflow-y-auto">
              <div v-if="!newContentStore.items.length" class="notif-empty">Rien de nouveau pour l'instant.</div>
              <DropdownMenuItem v-for="item in newContentStore.items" :key="item.type + item.id" class="items-center gap-2.5 p-2" @select="openNotifItem(item)">
                <img v-if="item.cover_url" :src="item.cover_url" class="notif-cover" alt="" />
                <div v-else class="notif-cover notif-cover-placeholder">📖</div>
                <div class="notif-info">
                  <div class="notif-title">{{ item.title }}</div>
                  <div class="notif-meta">
                    <span class="notif-type">{{ item.type === 'series' ? 'Nouvelle série' : 'Nouvel album' }}</span>
                    <template v-if="item.type === 'tome'"> · {{ item.series_name }}</template>
                  </div>
                  <div class="notif-time">{{ fmtRelative(item.created_at) }}</div>
                </div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Menu "Scanner" -->
          <DropdownMenu v-if="authStore.hasPermission('library.scan') || authStore.hasPermission('library.missing_albums')" v-model:open="showScanMenu" :modal="false">
            <Hint label="Scanner">
              <DropdownMenuTrigger as-child>
                <button class="btn btn-ghost topbar-scan-trigger" :class="{ 'topbar-scan-btn-active': showScanMenu }">
                  <SvgIcon name="refresh" :class="{ spin: anyScanRunning }" style="font-size:18px" />
                </button>
              </DropdownMenuTrigger>
            </Hint>
            <DropdownMenuContent align="end" class="min-w-[260px]">
              <DropdownMenuItem v-if="authStore.hasPermission('library.scan')" :disabled="fileScanRunning" @select="triggerFileScan">
                Scanner les fichiers de la bibliothèque
              </DropdownMenuItem>
              <DropdownMenuItem v-if="authStore.hasPermission('library.missing_albums')" :disabled="metaScanRunning" @select="triggerMetadataScan">
                Actualiser toutes les métadonnées
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <span class="topbar-divider" />

          <!-- Menu "Mon compte" -->
          <DropdownMenu v-model:open="showAccountMenu" :modal="false">
            <Hint label="Mon compte">
              <DropdownMenuTrigger as-child>
                <button class="btn btn-ghost topbar-account-trigger" :class="{ 'topbar-scan-btn-active': showAccountMenu }">
                  <UserAvatar :size="32" />
                </button>
              </DropdownMenuTrigger>
            </Hint>
            <DropdownMenuContent align="end" class="min-w-[220px]">
              <DropdownMenuItem @select="openAccountPage">Mon compte</DropdownMenuItem>
              <DropdownMenuItem @select="openChangePassword">Changer le mot de passe</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem @select="logoutFromMenu">Se déconnecter</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <!-- Scan progress bar -->
      <div v-if="fileScanRunning" class="scan-bar">
        <div
          class="scan-bar-fill"
          :style="{ width: library.scanProgress.total ? `${(library.scanProgress.processed / library.scanProgress.total) * 100}%` : '5%' }"
        />
      </div>
      <div v-else-if="metaScanRunning" class="scan-bar">
        <div
          class="scan-bar-fill"
          :style="{ width: missingAlbumsStore.scanProgress.total ? `${(missingAlbumsStore.scanProgress.processed / missingAlbumsStore.scanProgress.total) * 100}%` : '5%' }"
        />
      </div>

      <!-- Bandeau permissions média -->
      <div v-if="storageMismatch" class="storage-warning">
        ⚠️ Certains fichiers de votre bibliothèque risquent d'être illisibles par l'application.
        Ajoutez <code>PUID={{ storageMismatch.media_uid }}</code> et <code>PGID={{ storageMismatch.media_gid }}</code>
        à votre configuration, puis redémarrez le conteneur.
      </div>

      <!-- Page content -->
      <slot />
    </div>

    <ChangePasswordModal v-if="authStore.changePasswordOpen" />
    <GlobalSearchModal
      v-if="showGlobalSearch"
      :initial-query="topbarSearchInitial"
      @close="showGlobalSearch = false; topbarSearchInitial = ''"
    />



    <SmartListEditModal
      v-if="smartListsStore.editorOpen"
      :smart-list="smartListsStore.editorTarget"
      @close="smartListsStore.closeEditor()"
      @saved="onSmartListSaved"
    />

    <div v-if="confirmDeleteSmartList" class="confirm-backdrop" @click.self="confirmDeleteSmartList = null">
      <div class="confirm-box">
        <p class="confirm-title">Supprimer la liste ?</p>
        <p class="confirm-desc"><strong>{{ confirmDeleteSmartList.name }}</strong> sera supprimée définitivement. Les albums eux-mêmes ne sont pas touchés.</p>
        <div class="confirm-btns">
          <button class="btn btn-ghost btn-sm" @click="confirmDeleteSmartList = null">Annuler</button>
          <button class="btn btn-danger btn-sm" :disabled="deletingSmartList" @click="doDeleteSmartList">{{ deletingSmartList ? 'Suppression…' : 'Supprimer' }}</button>
        </div>
      </div>
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
.brand-name {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 1.15rem; color: var(--text); white-space: nowrap; overflow: hidden;
}
.brand-version { font-family: var(--font-mono); font-size: 0.7rem; color: var(--muted); white-space: nowrap; overflow: hidden; }
.brand-build { font-family: var(--font-mono); font-size: 0.62rem; color: var(--muted); opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

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
/* Liseret signalant la page active, en plus du fond teinté — repère net même en mode
   replié (icônes seules, sans libellé ni fond très contrasté). */
.nav-item-active {
  background: var(--sidebar-active) !important; color: var(--vermilion);
  box-shadow: inset 3px 0 0 var(--vermilion);
}
.nav-item-active .nav-icon { color: var(--vermilion); }
.nav-item-btn { color: var(--muted); }

.nav-icon { width: 21px; height: 21px; font-size: 21px; flex-shrink: 0; color: currentColor; }
.nav-label { white-space: nowrap; overflow: hidden; flex: 1; }

.nav-chevron { width: 14px; height: 14px; font-size: 14px; flex-shrink: 0; color: var(--muted); margin-left: auto; }

.nav-divider { height: 1px; background: var(--border); margin: 6px 14px; }

/* Compteur (Séries/Albums/Auteurs/Albums manquants) — rendu discret (fond neutre à
   mi-chemin entre --light, presque invisible, et --border, trop marqué), jamais affiché
   menu replié (showLabels) pour ne pas surcharger les icônes seules. */
.nav-count {
  flex-shrink: 0;
  font-family: var(--font-mono); font-size: 0.62rem; font-weight: 600;
  color: var(--muted);
  background: color-mix(in srgb, var(--light), var(--border));
  border-radius: var(--radius-sm);
  padding: 0 5px;
  line-height: 1.5;
}
.nav-item-active .nav-count { color: var(--vermilion); background: var(--vermilion-light); }
/* Signal d'activité suspecte (Historique) — rouge plutôt que le gris neutre des autres
   compteurs, volontairement : ce n'est pas une simple quantité, c'est une alerte. */
.nav-count-alert, .nav-item-active .nav-count-alert { color: var(--danger); background: var(--danger-bg-light); }
.nav-sub-item { padding-left: 24px; font-size: 0.82rem; color: var(--muted); }
.nav-sub-item-collapsed { padding-left: 14px; justify-content: center; }
.nav-sub-item:hover { color: var(--text); }
.nav-sub-item.nav-item-active { color: var(--vermilion); }
.nav-icon-sub { width: 17px; height: 17px; font-size: 17px; }

/* ── Main area ── */
.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  /* Filet de sécurité : un contenu de page trop large sur mobile (ex. barre d'outils avec
     trop de contrôles) ne doit jamais faire défiler toute la page horizontalement — les
     lignes qui doivent défiler (alpha-bar, scroll-row…) gèrent déjà leur propre overflow-x
     interne, donc rien n'est perdu ici. "clip" plutôt que "hidden" : ce dernier forcerait
     overflow-y à "auto" (règle CSS : un axe "visible" à côté d'un axe non-visible devient
     "auto"), transformant .main-area en conteneur de scroll et cassant le sticky de
     .topbar/.sidebar (qui s'accrochent au viewport, pas à ce conteneur).
  */
  overflow-x: clip;
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
  padding: 6px 10px 6px 32px;
  font-family: var(--font);
  font-size: 0.875rem;
  color: var(--text);
  background: var(--light);
  border: 1px solid var(--border);
  border-radius: 20px;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
  appearance: none;
}
/* Devenu un <button> (simple déclencheur de la recherche globale, plus un champ de filtre —
   voir AppLayout.vue::openGlobalSearchFromTopbar) : mêmes dimensions/apparence que l'ancien
   champ (.topbar-search-input ci-dessus, réutilisé tel quel), juste la disposition interne en
   flex pour aligner le texte de substitution et le badge de raccourci côte à côte. */
.topbar-search-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
  cursor: pointer;
}
.topbar-search-btn:hover { border-color: var(--primary-focus-border); }
.topbar-search-placeholder {
  flex: 1;
  min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--placeholder);
}
/* Arrondi/taille calés sur la maquette de comparaison (6px de rayon, padding plus compact,
   10.5px) plutôt que var(--radius-sm) (4px) et la taille de texte courante, un peu grande
   pour un badge de raccourci clavier. Simple indice visuel désormais (pas un bouton à part
   entière) : tout le bloc parent déclenche déjà la recherche globale. */
.topbar-search-kbd {
  flex-shrink: 0;
  padding: 2px 6px;
  font-family: var(--font-mono); font-size: 0.656rem; font-weight: 500;
  color: var(--muted); background: var(--surface);
  border: 1px solid var(--border); border-radius: 6px;
  white-space: nowrap;
}
.topbar-search-input:focus {
  outline: none;
  background: var(--surface);
  border-color: var(--primary-focus-border);
  box-shadow: 0 0 0 3px var(--primary-focus);
}
.topbar-search-input::placeholder { color: var(--placeholder); }

.topbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
/* Sépare le groupe "utilitaires" (mode sombre, nouveautés, scanner) de "Mon compte", plus
   personnel — un simple espace, pas une ligne, et seulement sur desktop : sur mobile la
   place manque déjà pour la barre de recherche (voir @media 768px). */
.topbar-divider { width: 14px; flex-shrink: 0; }

.topbar-scan {
  font-size: 0.8rem;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 5px;
}

/* Menu "Scanner" — même pattern que les menus "..." de SeriesDetailView.vue (non
   mutualisé : celui-ci vit dans le topbar global, hors de tout scroll-row). */
.topbar-scan-trigger { display: flex; align-items: center; padding: 6px; }
.topbar-scan-btn-active { border-color: var(--vermilion); color: var(--vermilion); background: var(--vermilion-light); }

/* Listes intelligentes — section dépliable, voir script pour la raison du Teleport.
   L'en-tête est un seul .nav-item (icône, libellé, chevron, +, badge) plutôt qu'une rangée
   composite : ça lui donne automatiquement le même padding-right que Séries/Albums/Auteurs,
   donc un badge aligné avec les leurs sans calcul manuel. */
.smart-lists-toggle { gap: 6px; }
/* .nav-chevron (règle générale) pousse le chevron tout à droite via margin-left:auto — ici
   .nav-label (flex:1) absorbe déjà l'espace disponible, donc un léger espace fixe suffit à
   séparer chevron et "+" au lieu d'un grand vide. */
.smart-lists-chevron { margin-left: 6px; }
.nav-header-btn {
  flex-shrink: 0; padding: 6px; margin: 0 2px;
  background: none; border: none; color: var(--muted); cursor: pointer;
  border-radius: var(--radius-sm); font-size: 0.9rem; line-height: 1;
  display: flex; align-items: center; justify-content: center;
}
.nav-header-btn:hover { background: var(--sidebar-hover); color: var(--text); }
.nav-inline-menu-wrap { flex-shrink: 0; margin-right: 4px; }
.smart-list-row { display: flex; align-items: center; }
.smart-list-link { flex: 1; min-width: 0; }
/* Pas de badge de comptage sur chaque smart list (contrairement à Séries/Albums/Auteurs) :
   un badge et le bouton "..." qui partagent le même espace se sont révélés peu fiables au
   clic (l'un pouvait rester au-dessus de l'autre selon le survol) — un bouton "..." seul,
   toujours à sa place, est plus sûr que de retenter l'alignement. Le nombre reste consultable
   en un clic sur la fiche de la liste. */
.nav-header-btn-sub { opacity: 0; }
.smart-list-row:hover .nav-header-btn-sub { opacity: 1; }
.nav-empty-hint { padding: 6px 24px; font-size: 0.78rem; color: var(--muted); font-style: italic; }

/* Repère visuel d'arborescence (ligne + point) — signale clairement que ces listes sont des
   enfants de "Smart list", pas des entrées de premier niveau comme Séries/Albums/Auteurs
   juste au-dessus. Chaque ligne dessine son propre segment vertical sur toute sa hauteur
   (::before), sauf la dernière (arrêtée à mi-hauteur, sur son point) — mis bout à bout, ces
   segments forment une ligne continue qui s'arrête proprement au dernier élément. */
.smart-list-row { position: relative; }
.smart-list-row::before {
  content: '';
  position: absolute;
  left: 20px; top: 0;
  width: 1px; height: 100%;
  background: var(--border);
}
.smart-list-row:last-child::before { height: 50%; }
.smart-list-row::after {
  content: '';
  position: absolute;
  left: 18px; top: 50%;
  width: 4px; height: 4px;
  margin-top: -2px;
  border-radius: 50%;
  background: var(--border);
}
/* Glisser-déposer : la ligne en cours de déplacement s'estompe, un peu de feedback visuel
   sans effet de transition qui gênerait le suivi du curseur pendant le drag. */
.smart-list-row-dragging { opacity: 0.4; }


/* Flyout "Smart list" en mode sidebar réduite — même chrome que les autres popovers de
   l'app, mais plus large (contenu = une liste de noms, pas juste des actions courtes). */
.smart-lists-flyout {
  width: 240px;
  max-height: 70vh;
  overflow-y: auto;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  padding: 8px 0;
}
.smart-lists-flyout-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 14px 8px;
  font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--muted);
}

.confirm-backdrop {
  position: fixed; inset: 0; z-index: 500;
  background: var(--overlay-bg);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.confirm-box {
  background: var(--surface-raised); border-radius: var(--radius); box-shadow: var(--shadow-lg);
  padding: 24px; max-width: 400px; width: 100%;
}
.confirm-title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.confirm-desc { font-size: 0.875rem; color: var(--muted); margin-bottom: 20px; }
.confirm-btns { display: flex; justify-content: flex-end; gap: 8px; }

.topbar-theme-toggle { color: var(--muted); flex-shrink: 0; }
.topbar-theme-toggle:hover { color: var(--text); }

/* Menu "Nouveautés" — même squelette que le menu Scanner ci-dessus. */
.topbar-notif-trigger { position: relative; }
.topbar-notif-badge {
  position: absolute; top: 2px; right: 2px;
  min-width: 15px; height: 15px; padding: 0 3px;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.62rem; font-weight: 700; line-height: 1;
  color: #fff; background: var(--vermilion);
  border-radius: 999px; border: 2px solid var(--surface);
}
.notif-empty { padding: 16px; text-align: center; font-size: 0.8rem; color: var(--muted); }
.notif-cover { width: 32px; height: 44px; object-fit: cover; border-radius: 3px; flex-shrink: 0; background: var(--light); }
.notif-cover-placeholder { display: flex; align-items: center; justify-content: center; font-size: 1rem; }
.notif-info { min-width: 0; flex: 1; }
.notif-title { font-size: 0.82rem; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.notif-meta { font-size: 0.74rem; color: var(--vermilion); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.notif-time { font-size: 0.72rem; color: var(--muted); margin-top: 1px; }

/* Menu "Mon compte" — même squelette que le menu Scanner ci-dessus. */
.topbar-account-trigger { display: flex; align-items: center; padding: 3px; border-radius: 50%; }

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

.storage-warning {
  padding: 8px 20px;
  background: var(--warning-bg, #fffbeb);
  color: var(--orange-bar, #b45309);
  border-bottom: 1px solid var(--border);
  font-size: 0.82rem;
  line-height: 1.5;
}
.storage-warning code {
  background: rgba(0,0,0,0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 0.9s linear infinite; }

/* ── Tiroir mobile ── */
.sidebar-backdrop {
  display: none;
}

@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    width: 260px !important;
    transform: translateX(-100%);
    transition: transform 0.22s ease;
    box-shadow: var(--shadow-lg, 0 10px 30px rgba(0, 0, 0, 0.25));
    z-index: 100;
  }
  .sidebar-mobile-open {
    transform: translateX(0);
  }
  .sidebar-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 90;
  }
  .topbar-search {
    max-width: none;
  }
  .topbar-search-kbd {
    display: none;
  }
  .topbar-divider {
    width: 0;
  }
}

</style>
