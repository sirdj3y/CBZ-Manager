import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',           name: 'home',         component: () => import('../views/HomeView.vue') },
    { path: '/series',     name: 'series',       component: () => import('../views/SeriesView.vue') },
    { path: '/series/:id', name: 'series-detail',component: () => import('../views/SeriesDetailView.vue') },
    { path: '/books',      name: 'books',        component: () => import('../views/BooksView.vue') },
    { path: '/tomes/:id',  name: 'tome-detail',  component: () => import('../views/TomeDetailView.vue') },
    { path: '/read/:id',   name: 'reader',       component: () => import('../views/ReaderView.vue') },
    { path: '/stats',      name: 'stats',        component: () => import('../views/StatsView.vue') },
    { path: '/settings',          redirect: '/settings/library' },
    { path: '/settings/general',  redirect: '/settings/library' },
    { path: '/settings/library',  name: 'settings-library',  component: () => import('../views/settings/SettingsLibraryView.vue') },
    { path: '/settings/data',     name: 'settings-data',     component: () => import('../views/settings/SettingsDataView.vue') },
    { path: '/settings/health',   redirect: '/settings/diagnostic' },
    { path: '/settings/diagnostic', name: 'settings-diagnostic', component: () => import('../views/settings/SettingsHealthView.vue') },
    { path: '/settings/about',    name: 'settings-about',    component: () => import('../views/settings/SettingsAboutView.vue') },
    { path: '/logs',       name: 'logs',         component: () => import('../views/LogsView.vue') },
    { path: '/import',     name: 'import',       component: () => import('../views/ImportView.vue') },
    { path: '/authors',    name: 'authors',      component: () => import('../views/AuthorsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
