// Infos de build injectées par Vite (vite.config.js) : environnement, commit, date.
/* global __BUILD_INFO__ */
export const buildInfo = typeof __BUILD_INFO__ !== 'undefined' ? __BUILD_INFO__ : { channel: 'local', sha: '', date: '' }

// "26/09 à 14:32" (heure locale du navigateur) — '' si la date est absente ou invalide.
export function formatBuildDate(iso, { withYear = false } = {}) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  const day = d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', ...(withYear ? { year: 'numeric' } : {}) })
  const time = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  return `${day} à ${time}`
}
