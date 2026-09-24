import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login',      name: 'login',        component: () => import('../views/LoginView.vue') },
    { path: '/',           name: 'home',         component: () => import('../views/HomeView.vue'), meta: { permission: 'library.read' } },
    { path: '/series',     name: 'series',       component: () => import('../views/SeriesView.vue'), meta: { permission: 'library.read' } },
    { path: '/series/:id', name: 'series-detail',component: () => import('../views/SeriesDetailView.vue'), meta: { permission: 'library.read' } },
    { path: '/books',      name: 'books',        component: () => import('../views/BooksView.vue'), meta: { permission: 'library.read' } },
    { path: '/tomes/:id',  name: 'tome-detail',  component: () => import('../views/TomeDetailView.vue'), meta: { permission: 'library.read' } },
    { path: '/read/:id',   name: 'reader',       component: () => import('../views/ReaderView.vue'), meta: { permission: 'library.read' } },
    { path: '/stats',      name: 'stats',        component: () => import('../views/StatsView.vue'), meta: { permission: 'library.read' } },
    { path: '/missing-albums', name: 'missing-albums', component: () => import('../views/MissingAlbumsView.vue'), meta: { permission: 'library.missing_albums' } },
    { path: '/collections/:id', name: 'collection-detail',  component: () => import('../views/CollectionDetailView.vue'), meta: { permission: 'library.read' } },
    { path: '/account',    name: 'account',      component: () => import('../views/AccountView.vue') },
    { path: '/settings',          redirect: '/settings/library' },
    { path: '/settings/general',  redirect: '/settings/library' },
    { path: '/settings/security', redirect: '/account' },
    { path: '/settings/library',  name: 'settings-library',  component: () => import('../views/settings/SettingsLibraryView.vue'), meta: { permission: 'library.settings' } },
    // Sauvegarde & BDD (suppression/restauration de la base) reste réservée à l'admin, même
    // composant que /settings/library (onglets internes) — voir services/permissions.py.
    { path: '/settings/data',     name: 'settings-data',     component: () => import('../views/settings/SettingsLibraryView.vue'), meta: { adminOnly: true } },
    { path: '/settings/health',   redirect: '/settings/diagnostic' },
    { path: '/settings/diagnostic', name: 'settings-diagnostic', component: () => import('../views/settings/SettingsHealthView.vue'), meta: { permission: 'library.settings' } },
    { path: '/settings/about',    name: 'settings-about',    component: () => import('../views/settings/SettingsAboutView.vue'), meta: { permission: 'library.settings' } },
    // Comptes reste réservé à l'admin : déléguer la création de comptes permettrait à un
    // non-admin de se créer un accès plus permissif que le sien (voir services/permissions.py).
    { path: '/settings/users',    name: 'settings-users',    component: () => import('../views/settings/SettingsUsersView.vue'), meta: { adminOnly: true } },
    { path: '/settings/profiles', name: 'settings-profiles', component: () => import('../views/settings/SettingsUsersView.vue'), meta: { adminOnly: true } },
    { path: '/logs',       name: 'logs',         component: () => import('../views/LogsView.vue'), meta: { permission: 'library.settings' } },
    { path: '/import',     name: 'import',       component: () => import('../views/ImportView.vue'), meta: { permission: 'library.import' } },
    { path: '/authors',    name: 'authors',      component: () => import('../views/AuthorsView.vue'), meta: { permission: 'library.read' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// Vérifie la session une seule fois par chargement d'app (auth.checked la met en cache),
// puis protège toutes les routes sauf /login.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) {
    await auth.checkAuth()
  }
  if (to.path === '/login') {
    return auth.authenticated ? '/' : true
  }
  if (!auth.authenticated) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // Mot de passe temporaire/par défaut jamais changé (compte créé par un admin, ou admin
  // fraîchement bootstrapé encore sur admin/admin) : piégé sur /account jusqu'au changement,
  // sinon ce champ (déjà renvoyé par le serveur depuis le début) restait purement informatif
  // — seulement affiché en ⚠ dans le tableau Utilisateurs, jamais réellement appliqué.
  if (auth.mustChangePassword && to.path !== '/account') {
    return '/account'
  }
  // Le serveur refuse déjà ces routes (403 sans le droit, ou 403 admin-only) — ce garde évite
  // juste d'afficher une page cassée avant que les appels API échouent. Repli sur /account
  // plutôt que '/' : '/' exige lui-même library.read, un utilisateur sans aucune permission
  // (pas de profil assigné) boucle indéfiniment sur ce garde sinon. /account (identifiant,
  // mot de passe, photo — self-service) n'exige rien, toujours atteignable.
  if ((to.meta.adminOnly && !auth.isAdmin) || (to.meta.permission && !auth.hasPermission(to.meta.permission))) {
    return to.path === '/account' ? true : '/account'
  }
  return true
})

export default router
