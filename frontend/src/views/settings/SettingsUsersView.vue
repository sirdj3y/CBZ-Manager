<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppLayout from '../../components/layout/AppLayout.vue'
import SvgIcon from '../../components/SvgIcon.vue'
import { usersApi } from '../../api/users'
import { profilesApi } from '../../api/profiles'
import { libraryApi } from '../../api/library'
import { useNotificationStore } from '../../stores/notifications'
import Hint from '../../components/ui/Hint.vue'
import AppDialog from '../../components/ui/AppDialog.vue'

const notif = useNotificationStore()
const route = useRoute()
const router = useRouter()

// Onglet piloté par la route (comme le toggle Séries/Albums de ContentToolbar.vue) — permet
// de lier/rafraîchir directement sur /settings/profiles.
const activeTab = computed(() => route.path === '/settings/profiles' ? 'profiles' : 'users')
function setTab(tab) {
  router.push(tab === 'profiles' ? '/settings/profiles' : '/settings/users')
}

const users = ref([])
const profiles = ref([])
const catalog = ref([]) // [{key, label}]
const ageRatings = ref([]) // ["Tout public", "Ados", "Adultes"]
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [u, p, c, a] = await Promise.all([
      usersApi.list(), profilesApi.list(), profilesApi.permissions(), libraryApi.getAgeRatings(),
    ])
    users.value = u.data
    profiles.value = p.data
    catalog.value = c.data
    ageRatings.value = a.data
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Impossible de charger les données')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  // Sélectionne le premier compte/profil par défaut plutôt que d'ouvrir sur un formulaire de
  // création vide — la plupart des visites servent à consulter/ajuster un élément existant.
  if (users.value.length) selectUser(users.value[0])
  if (profiles.value.length) startEditProfile(profiles.value[0])
})

// ── Recherche (liste de gauche) ───────────────────────────────────────────
const userSearch = ref('')
const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(u => u.username.toLowerCase().includes(q))
})

// ── Avatar — initiale + couleur dérivée du nom d'utilisateur. Pas de vraies photos pour un
// AUTRE compte que le sien : /api/auth/avatar ne sert que l'avatar de la session en cours,
// il n'existe pas de route pour récupérer l'avatar d'un tiers. ─────────────────────────────
const AVATAR_HUES = [12, 28, 190, 265, 320, 150, 45]
function avatarColor(username) {
  let hash = 0
  for (const ch of username || '') hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return `hsl(${AVATAR_HUES[hash % AVATAR_HUES.length]}, 58%, 52%)`
}

// ── Formulaire (création + édition dans le même panneau de détail) ────────────────────────
// null = création, sinon id de l'utilisateur sélectionné/en cours d'édition.
const editingUserId = ref(null)
const newUsername = ref('')
const newPassword = ref('')
const showPassword = ref(false)
const newAgeRatingLimit = ref('Tout public')
const saving = ref(false)
// { created_at, updated_at } du compte sélectionné, pour le pied du panneau de détail — null
// en création (rien à afficher, le compte n'existe pas encore).
const selectedMeta = ref(null)

// Rôle + permissions avancées — remplace l'ancien RolePermissionsPicker.vue (mise en page
// trop différente pour être réutilisée telle quelle : rôle en simple <select> sans badge
// inline, permissions en interrupteurs plutôt qu'en cases à cocher). Composant retiré.
const roleValue = ref('') // '' (aucun) | 'admin' | id de profil
const permCheckedKeys = ref(new Set())

function baseSetForRole(rv) {
  if (rv === 'admin') return null
  if (rv === '' || rv == null) return new Set()
  const p = profiles.value.find(pr => pr.id === rv)
  return new Set(p?.permissions || [])
}

const isAdminRole = computed(() => roleValue.value === 'admin')
const permBaseSet = computed(() => baseSetForRole(roleValue.value))
const permissionsModified = computed(() => {
  if (isAdminRole.value) return false
  const base = permBaseSet.value
  if (base.size !== permCheckedKeys.value.size) return true
  for (const k of base) if (!permCheckedKeys.value.has(k)) return true
  return false
})

function onRoleChange() {
  permCheckedKeys.value = new Set(baseSetForRole(roleValue.value) || [])
}

function resetPermissions() {
  permCheckedKeys.value = new Set(baseSetForRole(roleValue.value) || [])
}

function toggleUserPermission(key) {
  if (permCheckedKeys.value.has(key)) permCheckedKeys.value.delete(key)
  else permCheckedKeys.value.add(key)
  permCheckedKeys.value = new Set(permCheckedKeys.value)
}

// Titre court affiché en gras dans "Permissions avancées" — le catalogue backend
// (services/permissions.py) n'a qu'un seul libellé par clé ; celui-ci sert de description en
// dessous (déjà assez explicite), pas besoin de dupliquer la donnée côté backend pour ça.
const PERMISSION_TITLES = {
  'library.read': 'Consulter la bibliothèque',
  'library.import': 'Importer des fichiers',
  'library.scan': 'Scanner la bibliothèque',
  'library.metadata_edit': 'Modifier les métadonnées',
  'library.convert': 'Convertir des fichiers',
  'library.rename': 'Renommer des fichiers',
  'library.move': 'Déplacer des albums',
  'library.delete': 'Supprimer ou masquer',
  'library.download': 'Télécharger des fichiers',
  'library.missing_albums': 'Albums manquants',
  'library.settings': 'Réglages de bibliothèque',
}

function initRoleState(user) {
  roleValue.value = user?.is_admin ? 'admin' : (user?.profile_id ?? '')
  const base = baseSetForRole(roleValue.value)
  permCheckedKeys.value = new Set(user?.custom_permissions?.length ? user.custom_permissions : (base || []))
}

function selectUser(user) {
  editingUserId.value = user.id
  newUsername.value = user.username
  newPassword.value = ''
  showPassword.value = false
  // Un non-admin a toujours une vraie valeur stockée (voir saveUser/backend) — ce repli ne
  // s'applique donc en pratique qu'aux comptes admin (age_rating_limit toujours NULL en base
  // pour eux), qui n'ont aucune restriction réelle : affichés comme "Adultes" plutôt que
  // "Tout public", plus fidèle à leur accès effectif.
  newAgeRatingLimit.value = user.age_rating_limit || 'Adultes'
  selectedMeta.value = { created_at: user.created_at, updated_at: user.updated_at }
  initRoleState(user)
}

function startNewUser() {
  editingUserId.value = null
  newUsername.value = ''
  newPassword.value = ''
  showPassword.value = false
  // Pas de "Illimité" par défaut — sécurité par défaut, un oubli de paramétrage ne doit
  // jamais exposer plus que "Tout public" (voir backend/routers/users.py).
  newAgeRatingLimit.value = 'Tout public'
  selectedMeta.value = null
  initRoleState(null)
}

function cancelEdit() {
  const current = users.value.find(u => u.id === editingUserId.value)
  if (current) selectUser(current)
}

const pendingDeleteId = ref(null)
// { username, password } — affiché une seule fois juste après la création, jamais
// récupérable ensuite (le backend ne le renvoie qu'à cet instant, et seulement si aucun mot
// de passe n'a été saisi à la main — voir saveUser).
const tempPasswordInfo = ref(null)

function roleBadgeText(user) {
  if (user.is_admin) return 'Administrateur'
  return user.profile_id ? (profiles.value.find(p => p.id === user.profile_id)?.name || '—') : 'Aucun (aucun droit)'
}

async function saveUser() {
  const username = newUsername.value.trim()
  if (!username) {
    notif.error("Nom d'utilisateur requis")
    return
  }
  const payload = {
    username,
    is_admin: isAdminRole.value,
    profile_id: isAdminRole.value || roleValue.value === '' ? null : roleValue.value,
    custom_permissions: !isAdminRole.value && permissionsModified.value ? [...permCheckedKeys.value] : null,
    age_rating_limit: newAgeRatingLimit.value,
  }
  if (newPassword.value) payload.password = newPassword.value

  saving.value = true
  try {
    if (editingUserId.value) {
      const { data } = await usersApi.update(editingUserId.value, payload)
      notif.success('Compte mis à jour')
      await load()
      const updated = users.value.find(u => u.id === data.id)
      if (updated) selectUser(updated)
    } else {
      const { data } = await usersApi.create(payload)
      if (data.temp_password) {
        tempPasswordInfo.value = { username: data.username, password: data.temp_password }
      } else {
        notif.success('Utilisateur créé')
      }
      await load()
      const created = users.value.find(u => u.id === data.id)
      if (created) selectUser(created)
    }
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'enregistrement")
  } finally {
    saving.value = false
  }
}

function confirmDelete() {
  pendingDeleteId.value = editingUserId.value
}

async function doDelete() {
  const id = pendingDeleteId.value
  pendingDeleteId.value = null
  try {
    await usersApi.remove(id)
    notif.success('Utilisateur supprimé')
    await load()
    if (users.value.length) selectUser(users.value[0])
    else startNewUser()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  }
}

// Modale "séries masquées" — même pattern que ConverterModal.vue (Set réactif + cases à
// cocher + tout cocher/décocher), pas AutocompleteInput (fait pour une seule valeur).
// Fetch dédié (comme MoveTomesModal.vue) plutôt que le store library.series, qui peut être
// filtré par le toggle "afficher les séries masquées" de la page courante.
const hiddenSeriesUser = ref(null)
const allSeries = ref([])
const checkedSeriesIds = ref(new Set())
const loadingHiddenSeries = ref(false)
const savingHiddenSeries = ref(false)

async function openHiddenSeriesModal(user) {
  hiddenSeriesUser.value = user
  loadingHiddenSeries.value = true
  try {
    const [seriesRes, hiddenRes] = await Promise.all([
      libraryApi.getSeries(true),
      usersApi.getHiddenSeries(user.id),
    ])
    allSeries.value = seriesRes.data
    checkedSeriesIds.value = new Set(hiddenRes.data.series_ids)
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Impossible de charger les séries')
    hiddenSeriesUser.value = null
  } finally {
    loadingHiddenSeries.value = false
  }
}

function toggleSeries(id) {
  if (checkedSeriesIds.value.has(id)) checkedSeriesIds.value.delete(id)
  else checkedSeriesIds.value.add(id)
  checkedSeriesIds.value = new Set(checkedSeriesIds.value)
}

function toggleAllSeries() {
  checkedSeriesIds.value = checkedSeriesIds.value.size === allSeries.value.length
    ? new Set()
    : new Set(allSeries.value.map(s => s.id))
}

async function saveHiddenSeries() {
  savingHiddenSeries.value = true
  try {
    await usersApi.setHiddenSeries(hiddenSeriesUser.value.id, [...checkedSeriesIds.value])
    notif.success('Séries masquées mises à jour')
    hiddenSeriesUser.value = null
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'enregistrement")
  } finally {
    savingHiddenSeries.value = false
  }
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(tempPasswordInfo.value.password)
    notif.success('Copié dans le presse-papier')
  } catch {
    notif.error('Impossible de copier — sélectionnez et copiez manuellement')
  }
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

// ── Onglet Profils ───────────────────────────────────────────────────────
// null = création, sinon id du profil en cours d'édition — un seul formulaire pour les deux.
const editingId = ref(null)
const formName = ref('')
const checkedPerms = ref(new Set())
const savingProfile = ref(false)

const pendingDeleteProfileId = ref(null)

function togglePermission(key) {
  if (checkedPerms.value.has(key)) checkedPerms.value.delete(key)
  else checkedPerms.value.add(key)
  checkedPerms.value = new Set(checkedPerms.value)
}

function toggleAllPermissions() {
  checkedPerms.value = checkedPerms.value.size === catalog.value.length
    ? new Set()
    : new Set(catalog.value.map(c => c.key))
}

function startCreateProfile() {
  editingId.value = null
  formName.value = ''
  checkedPerms.value = new Set()
}

function startEditProfile(profile) {
  editingId.value = profile.id
  formName.value = profile.name
  checkedPerms.value = new Set(profile.permissions)
}

async function saveProfile() {
  const name = formName.value.trim()
  if (!name) {
    notif.error('Nom de profil requis')
    return
  }
  const payload = { name, permissions: [...checkedPerms.value] }
  savingProfile.value = true
  try {
    if (editingId.value) {
      await profilesApi.update(editingId.value, payload)
      notif.success('Profil mis à jour')
    } else {
      await profilesApi.create(payload)
      notif.success('Profil créé')
    }
    startCreateProfile()
    await load()
  } catch (e) {
    notif.error(e.response?.data?.detail || "Erreur lors de l'enregistrement")
  } finally {
    savingProfile.value = false
  }
}

function confirmDeleteProfile(id) {
  pendingDeleteProfileId.value = id
}

async function doDeleteProfile() {
  const id = pendingDeleteProfileId.value
  pendingDeleteProfileId.value = null
  try {
    await profilesApi.remove(id)
    notif.success('Profil supprimé')
    if (editingId.value === id) startCreateProfile()
    await load()
  } catch (e) {
    notif.error(e.response?.data?.detail || 'Erreur lors de la suppression')
  }
}
</script>

<template>
  <AppLayout>
    <main class="settings-main">
      <div class="page-header-row">
        <div>
          <h1 class="settings-heading">Comptes</h1>
          <p class="settings-subheading">Gérez les utilisateurs et leurs permissions d'accès à votre bibliothèque.</p>
        </div>
        <button v-if="activeTab === 'users'" type="button" class="btn btn-primary" @click="startNewUser">
          <SvgIcon name="square-plus" class="btn-icon-svg" /> Nouvel utilisateur
        </button>
        <button v-else type="button" class="btn btn-primary" @click="startCreateProfile">
          <SvgIcon name="square-plus" class="btn-icon-svg" /> Nouveau profil
        </button>
      </div>

      <div class="tabs-row">
        <button @click="setTab('users')" :class="['tab-btn', { 'tab-btn-active': activeTab === 'users' }]">Utilisateurs</button>
        <button @click="setTab('profiles')" :class="['tab-btn', { 'tab-btn-active': activeTab === 'profiles' }]">Profils</button>
      </div>

      <!-- ── Onglet Utilisateurs ── -->
      <template v-if="activeTab === 'users'">
        <div v-if="loading" class="form-hint">Chargement…</div>
        <div v-else class="users-layout">
          <!-- Liste -->
          <section class="card users-list-card">
            <div class="card-body">
              <div class="settings-section-title">Utilisateurs ({{ users.length }})</div>
              <div class="user-search-wrap">
                <SvgIcon name="search" class="user-search-icon" />
                <input v-model="userSearch" type="text" class="form-control user-search-input" placeholder="Rechercher un utilisateur…" />
              </div>
              <div class="user-list">
                <button
                  v-for="u in filteredUsers" :key="u.id" type="button"
                  :class="['user-row', { 'user-row-active': editingUserId === u.id }]"
                  @click="selectUser(u)"
                >
                  <span class="user-row-avatar" :style="{ background: avatarColor(u.username) }">{{ u.username.charAt(0).toUpperCase() }}</span>
                  <span class="user-row-name">
                    {{ u.username }}
                    <SvgIcon v-if="u.must_change_password" name="info" class="user-row-warn" title="Doit changer son mot de passe à la prochaine connexion" />
                  </span>
                  <span :class="['badge', u.is_admin ? 'badge-admin' : 'badge-plain']">{{ roleBadgeText(u) }}</span>
                </button>
                <p v-if="!filteredUsers.length" class="form-hint">Aucun utilisateur trouvé.</p>
              </div>
            </div>
          </section>

          <!-- Détails -->
          <section class="card user-detail-card">
            <div class="card-body">
              <div class="user-detail-header">
                <div class="settings-section-title" style="margin-bottom:0">{{ editingUserId ? "Détails de l'utilisateur" : 'Nouvel utilisateur' }}</div>
                <div class="user-detail-header-actions">
                  <button v-if="editingUserId" type="button" class="btn btn-ghost btn-sm" title="Historique de ce compte" @click="router.push(`/logs?user=${encodeURIComponent(newUsername)}`)">
                    <SvgIcon name="history" class="btn-icon-svg" /> Historique
                  </button>
                  <button v-if="editingUserId" type="button" class="btn btn-danger-outline btn-sm" @click="confirmDelete">
                    <SvgIcon name="trash-2" class="btn-icon-svg" /> Supprimer
                  </button>
                </div>
              </div>

              <div class="detail-section">
                <div class="detail-section-title">
                  <SvgIcon name="author" />
                  <div class="detail-section-heading">
                    <div class="detail-section-name">Informations générales</div>
                    <p class="form-hint">Informations de connexion et rôle de l'utilisateur.</p>
                  </div>
                </div>
                <div class="detail-grid">
                  <div class="form-group">
                    <label class="form-label">Nom d'utilisateur <span class="required">*</span></label>
                    <input v-model="newUsername" type="text" class="form-control" @keyup.enter="saveUser" />
                  </div>
                  <div class="form-group">
                    <label class="form-label">Mot de passe</label>
                    <div class="password-input-wrap">
                      <input
                        v-model="newPassword" :type="showPassword ? 'text' : 'password'"
                        class="form-control" autocomplete="new-password"
                      />
                      <Hint :label="showPassword ? 'Masquer' : 'Afficher'">
                        <button type="button" class="password-toggle" @click="showPassword = !showPassword">
                          <SvgIcon :name="showPassword ? 'hide' : 'eye'" />
                        </button>
                      </Hint>
                    </div>
                    <p class="form-hint">{{ editingUserId ? 'Laissez vide pour conserver le mot de passe actuel.' : 'Laissez vide pour générer un mot de passe temporaire.' }}</p>
                  </div>
                  <div class="form-group">
                    <label class="form-label">Rôle <span class="required">*</span></label>
                    <select v-model="roleValue" class="form-control" @change="onRoleChange">
                      <option value="">Aucun (aucun droit)</option>
                      <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
                      <option value="admin">Administrateur</option>
                    </select>
                    <p class="form-hint">Définit les permissions de base de l'utilisateur.</p>
                  </div>
                  <div class="form-group">
                    <label class="form-label">Public <span class="required">*</span></label>
                    <select v-model="newAgeRatingLimit" class="form-control" :disabled="isAdminRole">
                      <option v-for="a in ageRatings" :key="a" :value="a">{{ a === 'Adultes' ? 'Adultes (illimité)' : a }}</option>
                    </select>
                    <p class="form-hint">Filtre le contenu accessible selon sa classification.</p>
                  </div>
                </div>
              </div>

              <div v-if="!isAdminRole" class="detail-section">
                <div class="detail-section-title">
                  <SvgIcon name="key" />
                  <div class="detail-section-heading">
                    <div class="detail-section-name">Permissions avancées</div>
                    <p class="form-hint">Affinez les autorisations de cet utilisateur.</p>
                  </div>
                  <button v-if="permissionsModified" type="button" class="btn btn-ghost btn-sm perm-reset-btn" @click="resetPermissions">
                    <SvgIcon name="refresh" class="btn-icon-svg" /> Réinitialiser
                  </button>
                </div>
                <div class="permission-toggle-list">
                  <label v-for="p in catalog" :key="p.key" class="permission-toggle-row">
                    <div class="permission-toggle-title">{{ PERMISSION_TITLES[p.key] || p.label }}</div>
                    <span class="switch">
                      <input type="checkbox" :checked="permCheckedKeys.has(p.key)" @change="toggleUserPermission(p.key)" />
                      <span class="switch-track"><span class="switch-thumb"></span></span>
                    </span>
                  </label>
                </div>
              </div>

              <div v-if="editingUserId && !isAdminRole" class="detail-section">
                <button type="button" class="btn btn-ghost btn-sm" @click="openHiddenSeriesModal({ id: editingUserId, username: newUsername })">
                  <SvgIcon name="hide" class="btn-icon-svg" /> Séries masquées…
                </button>
              </div>

              <div class="detail-footer">
                <p v-if="selectedMeta" class="form-hint detail-footer-meta">
                  Créé le {{ formatDate(selectedMeta.created_at) }}<template v-if="selectedMeta.updated_at"> · Dernière modification le {{ formatDate(selectedMeta.updated_at) }}</template>
                </p>
                <div v-else class="detail-footer-meta" />
                <div class="detail-footer-actions">
                  <button v-if="editingUserId" type="button" class="btn btn-ghost btn-sm" @click="cancelEdit">Annuler</button>
                  <button type="button" class="btn btn-primary btn-sm" :disabled="saving" @click="saveUser">
                    {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </template>

      <!-- ── Onglet Profils ── -->
      <template v-else>
        <div v-if="loading" class="form-hint">Chargement…</div>
        <div v-else class="users-layout">
          <!-- Liste -->
          <section class="card users-list-card">
            <div class="card-body">
              <div class="settings-section-title">Profils ({{ profiles.length }})</div>
              <div class="user-list">
                <button
                  v-for="p in profiles" :key="p.id" type="button"
                  :class="['user-row', { 'user-row-active': editingId === p.id }]"
                  @click="startEditProfile(p)"
                >
                  <span class="user-row-avatar" :style="{ background: avatarColor(p.name) }">{{ p.name.charAt(0).toUpperCase() }}</span>
                  <span class="user-row-name">{{ p.name }}</span>
                  <span class="badge badge-plain">{{ p.permissions.length }} permission{{ p.permissions.length !== 1 ? 's' : '' }}</span>
                </button>
                <p v-if="!profiles.length" class="form-hint">Aucun profil pour l'instant.</p>
              </div>
            </div>
          </section>

          <!-- Détails -->
          <section class="card user-detail-card">
            <div class="card-body">
              <div class="user-detail-header">
                <div class="settings-section-title" style="margin-bottom:0">{{ editingId ? 'Détails du profil' : 'Nouveau profil' }}</div>
                <div class="user-detail-header-actions">
                  <button v-if="editingId" type="button" class="btn btn-danger-outline btn-sm" @click="confirmDeleteProfile(editingId)">
                    <SvgIcon name="trash-2" class="btn-icon-svg" /> Supprimer
                  </button>
                </div>
              </div>

              <div class="detail-section">
                <div class="detail-section-title">
                  <SvgIcon name="author" />
                  <div class="detail-section-heading">
                    <div class="detail-section-name">Informations générales</div>
                    <p class="form-hint">Nom du profil, affiché dans la liste des rôles disponibles pour un compte.</p>
                  </div>
                </div>
                <div class="form-group">
                  <label class="form-label">Nom <span class="required">*</span></label>
                  <input v-model="formName" type="text" class="form-control" placeholder="ex : Lecteur" @keyup.enter="saveProfile" />
                </div>
              </div>

              <div class="detail-section">
                <div class="detail-section-title">
                  <SvgIcon name="key" />
                  <div class="detail-section-heading">
                    <div class="detail-section-name">Permissions</div>
                    <p class="form-hint">Droits accordés à tout utilisateur ayant ce profil.</p>
                  </div>
                  <button type="button" class="btn btn-ghost btn-sm perm-reset-btn" @click="toggleAllPermissions">
                    {{ checkedPerms.size === catalog.length ? 'Tout décocher' : 'Tout cocher' }}
                  </button>
                </div>
                <div class="permission-toggle-list">
                  <label v-for="p in catalog" :key="p.key" class="permission-toggle-row">
                    <div class="permission-toggle-title">{{ PERMISSION_TITLES[p.key] || p.label }}</div>
                    <span class="switch">
                      <input type="checkbox" :checked="checkedPerms.has(p.key)" @change="togglePermission(p.key)" />
                      <span class="switch-track"><span class="switch-thumb"></span></span>
                    </span>
                  </label>
                </div>
              </div>

              <div class="detail-footer">
                <div class="detail-footer-meta" />
                <div class="detail-footer-actions">
                  <button v-if="editingId" type="button" class="btn btn-ghost btn-sm" @click="startCreateProfile">Annuler</button>
                  <button type="button" class="btn btn-primary btn-sm" :disabled="savingProfile" @click="saveProfile">
                    {{ savingProfile ? 'Enregistrement…' : 'Enregistrer' }}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </template>
    </main>

    <!-- Confirmation de suppression utilisateur -->
    <AppDialog v-if="pendingDeleteId" :title="`Supprimer définitivement le compte « ${newUsername} » ?`" @close="pendingDeleteId = null">
      <div class="modal-box modal-box-sm">
      <div class="modal-body">
        <p>Supprimer définitivement le compte « <strong>{{ newUsername }}</strong> » ?</p>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-spacer" />
        <button class="btn btn-ghost btn-sm" @click="pendingDeleteId = null">Annuler</button>
        <button class="btn btn-danger btn-sm" @click="doDelete">Supprimer</button>
      </div>
      </div>
    </AppDialog>

    <!-- Confirmation de suppression profil -->
    <AppDialog v-if="pendingDeleteProfileId" title="Supprimer ce profil ?" @close="pendingDeleteProfileId = null">
      <div class="modal-box modal-box-sm">
      <div class="modal-body">
        <p>Supprimer ce profil ? Les utilisateurs qui l'ont perdront leurs permissions (aucun profil = aucun droit).</p>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-spacer" />
        <button class="btn btn-ghost btn-sm" @click="pendingDeleteProfileId = null">Annuler</button>
        <button class="btn btn-danger btn-sm" @click="doDeleteProfile">Supprimer</button>
      </div>
      </div>
    </AppDialog>

    <!-- Mot de passe temporaire — affiché une seule fois -->
    <AppDialog v-if="tempPasswordInfo" :title="`Compte « ${tempPasswordInfo.username} » créé`" :dismissible="false" @close="tempPasswordInfo = null">
      <div class="modal-box">
      <div class="modal-header">
        <div class="modal-header-info">
          <p class="modal-title">Compte « {{ tempPasswordInfo.username }} » créé</p>
        </div>
      </div>
      <div class="modal-body">
        <p class="form-hint">
          Ce mot de passe ne sera plus jamais affiché — notez-le ou copiez-le maintenant, puis transmettez-le à l'utilisateur.
        </p>
        <div class="temp-password-box">
          <code>{{ tempPasswordInfo.password }}</code>
          <button class="btn btn-ghost btn-sm" @click="copyPassword">Copier</button>
        </div>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-spacer" />
        <button class="btn btn-primary btn-sm" @click="tempPasswordInfo = null">J'ai noté le mot de passe</button>
      </div>
      </div>
    </AppDialog>

    <!-- Séries masquées pour un utilisateur -->
    <AppDialog v-if="hiddenSeriesUser" :title="`Séries masquées pour « ${hiddenSeriesUser.username} »`" @close="hiddenSeriesUser = null">
      <div class="modal-box">
      <div class="modal-header">
        <div class="modal-header-info">
          <p class="modal-title">Séries masquées pour « {{ hiddenSeriesUser.username }} »</p>
        </div>
        <button @click="hiddenSeriesUser = null" class="btn btn-ghost btn-icon btn-sm">✕</button>
      </div>
      <div class="modal-body">
        <div v-if="loadingHiddenSeries" class="form-hint">Chargement…</div>
        <template v-else>
          <div class="permissions-header">
            <p class="form-hint" style="margin:0">Cochées = invisibles pour cet utilisateur, partout dans l'app.</p>
            <button type="button" class="btn btn-ghost btn-sm" @click="toggleAllSeries">
              {{ checkedSeriesIds.size === allSeries.length ? 'Tout décocher' : 'Tout cocher' }}
            </button>
          </div>
          <div class="series-list">
            <label v-for="s in allSeries" :key="s.id" :class="['series-row', { 'series-row-checked': checkedSeriesIds.has(s.id) }]">
              <input type="checkbox" :checked="checkedSeriesIds.has(s.id)" @change="toggleSeries(s.id)" class="toggle-checkbox" />
              <span>{{ s.name }}</span>
            </label>
          </div>
        </template>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-spacer" />
        <button class="btn btn-ghost btn-sm" @click="hiddenSeriesUser = null">Annuler</button>
        <button class="btn btn-primary btn-sm" :disabled="savingHiddenSeries || loadingHiddenSeries" @click="saveHiddenSeries">
          {{ savingHiddenSeries ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </div>
      </div>
    </AppDialog>
  </AppLayout>
</template>

<style scoped>
.settings-main {
  flex: 1; padding: 24px 20px;
  max-width: 1200px; margin: 0 auto; width: 100%;
}
.page-header-row {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  margin-bottom: 20px;
}
.settings-heading {
  font-family: var(--font-display); font-weight: 400; text-transform: uppercase;
  font-size: 1.4rem;
  color: var(--text);
}
.settings-subheading { font-size: 0.85rem; color: var(--muted); margin-top: 4px; }
.settings-section-title {
  font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted); margin-bottom: 14px;
}
.form-group { margin-bottom: 14px; }
.form-hint { margin-top: 5px; font-size: 0.8rem; color: var(--muted); }
.required { color: var(--vermilion); }

/* Onglets soulignés — se distinguent nettement des boutons pill du reste de la page
   (Créer/Modifier/Supprimer), contrairement à l'ancien .view-toggle en style bouton
   segmenté qui se confondait avec eux. */
.tabs-row {
  display: flex; gap: 22px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 20px;
}
.tab-btn {
  padding: 0 0 10px;
  background: none; border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-family: var(--font);
  font-size: 0.85rem; font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  transition: color 0.12s, border-color 0.12s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn-active { color: var(--vermilion); border-bottom-color: var(--vermilion); }

/* ── Onglet Utilisateurs — disposition liste + détail ─────────────────────────────────── */
.users-layout {
  display: grid; grid-template-columns: 320px 1fr; gap: 20px; align-items: start;
}
@media (max-width: 860px) {
  .users-layout { grid-template-columns: 1fr; }
  .detail-grid { grid-template-columns: 1fr !important; }
}

.user-search-wrap { position: relative; margin-bottom: 14px; }
.user-search-icon {
  position: absolute; left: 11px; top: 50%; transform: translateY(-50%);
  color: var(--muted); pointer-events: none; font-size: 0.9rem;
}
.user-search-input { padding-left: 32px; }

.user-list { display: flex; flex-direction: column; gap: 4px; }
.user-row {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 8px; border: none; border-radius: var(--radius-sm);
  background: none; cursor: pointer; text-align: left;
  transition: background 0.1s;
}
.user-row:hover { background: var(--light); }
.user-row-active { background: var(--vermilion-light); }
.user-row-avatar {
  flex-shrink: 0; width: 38px; height: 38px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 700; font-size: 0.95rem;
}
.user-row-name {
  flex: 1; min-width: 0; font-weight: 600; color: var(--text); font-size: 0.875rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.user-row-warn { color: var(--warning); margin-left: 4px; font-size: 0.8rem; cursor: help; }

.user-detail-card { min-width: 0; }
.user-detail-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 18px;
}
.user-detail-header-actions { display: flex; align-items: center; gap: 8px; }
.btn-danger-outline {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--surface); color: var(--danger); border: 1px solid var(--danger);
  border-radius: var(--radius-sm); padding: 6px 12px;
  font-family: var(--font); font-size: 0.8125rem; font-weight: 600; cursor: pointer;
  transition: background 0.12s;
}
.btn-danger-outline:hover { background: var(--danger-bg-light); }

.detail-section { padding: 18px 0; border-top: 1px solid var(--border); }
.detail-section:first-of-type { padding-top: 0; border-top: none; }
.detail-section-title { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 16px; }
.detail-section-heading { flex: 1; min-width: 0; }
.detail-section-name { font-size: 0.95rem; font-weight: 700; color: var(--text); }
.perm-reset-btn { flex-shrink: 0; }

.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 18px; }

.password-input-wrap { position: relative; }
.password-input-wrap .form-control { padding-right: 36px; }
.password-toggle {
  position: absolute; top: 50%; right: 4px; transform: translateY(-50%);
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: var(--radius-sm);
  background: none; border: none; color: var(--muted); cursor: pointer;
  transition: background 0.12s;
}
.password-toggle:hover { background: var(--light); }

.permission-toggle-list { display: flex; flex-direction: column; }
.permission-toggle-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 12px 0; border-bottom: 1px solid var(--border);
}
.permission-toggle-row:last-child { border-bottom: none; padding-bottom: 0; }
.permission-toggle-title { font-size: 0.875rem; color: var(--text); }

/* Interrupteur — technique classique (checkbox invisible + piste/curseur stylés). */
.switch { position: relative; display: inline-block; width: 32px; height: 18px; flex-shrink: 0; }
.switch input {
  position: absolute; inset: 0; margin: 0; opacity: 0; cursor: pointer; z-index: 1;
}
.switch-track {
  position: absolute; inset: 0; background: var(--border); border-radius: 999px;
  transition: background 0.15s;
}
.switch-thumb {
  position: absolute; top: 2px; left: 2px; width: 14px; height: 14px;
  background: #fff; border-radius: 50%; box-shadow: 0 1px 2px rgba(0,0,0,.3);
  transition: transform 0.15s;
}
.switch input:checked ~ .switch-track { background: var(--vermilion); }
.switch input:checked ~ .switch-track .switch-thumb { transform: translateX(14px); }
.switch input:focus-visible ~ .switch-track { outline: 2px solid var(--primary-focus-border); outline-offset: 2px; }

.detail-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding-top: 18px; margin-top: 4px; border-top: 1px solid var(--border);
}
.detail-footer-meta { font-size: 0.78rem; color: var(--muted); margin: 0; }
.detail-footer-actions { display: flex; gap: 10px; flex-shrink: 0; }

.badge { display: inline-block; padding: 1px 7px; border-radius: 20px; font-size: 0.72rem; font-weight: 600; flex-shrink: 0; }
.badge-admin { background: var(--vermilion-light); color: var(--vermilion); }
.badge-plain { background: var(--light); color: var(--muted); }

.permissions-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.toggle-checkbox { accent-color: var(--primary); flex-shrink: 0; }

/* Modales — même squelette que RenameModal.vue (chaque modale duplique son propre CSS
   dans cette codebase, pas de classes globales partagées). */
.modal-box {
  background: var(--surface-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 100%; max-width: 440px;
  display: flex; flex-direction: column;
}
.modal-box.modal-box-sm { max-width: 360px; }
.modal-header { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.modal-header-info { flex: 1; min-width: 0; }
.modal-title { font-size: 0.9rem; font-weight: 600; color: var(--text); }
.modal-body { padding: 16px; display: flex; flex-direction: column; gap: 10px; font-size: 0.85rem; color: var(--text); }
.modal-footer {
  display: flex; align-items: center; gap: 8px; padding: 12px 16px;
  border-top: 1px solid var(--border); background: var(--light);
  border-radius: 0 0 var(--radius) var(--radius);
}
.modal-footer-spacer { flex: 1; }

.temp-password-box {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 12px; background: var(--light); border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.temp-password-box code { font-size: 0.95rem; font-weight: 600; letter-spacing: 0.02em; }

.series-list {
  display: flex; flex-direction: column; gap: 2px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  padding: 4px; max-height: 320px; overflow-y: auto;
}
.series-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 8px; border-radius: var(--radius-sm);
  font-size: 0.8125rem; color: var(--text); cursor: pointer;
  transition: background 0.1s;
}
.series-row:hover { background: var(--light); }
.series-row-checked { background: var(--primary-light); }
</style>
