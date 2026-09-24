// Normalise une chaine pour une recherche insensible aux accents et a la casse :
// "Chateau" / "chateau" / "CHATEAU" deviennent tous "chateau".
export function normalizeSearch(s) {
  return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

// Article de tête à ignorer pour le tri/regroupement alphabétique d'un nom de série
// ("Le Scrameustache" doit trier au S, pas au L) — jamais utilisé pour l'affichage,
// uniquement pour comparer/regrouper. Même liste d'articles que côté scraper Bedetheque
// (backend/services/scraper_bedetheque.py::_ARTICLE_RE), qui gère la conversion inverse
// ("Scrameustache (Le)" -> "Le Scrameustache") pour le rapprochement de séries.
const LEADING_ARTICLE_RE = /^(?:L'|(?:Le|La|Les|Un|Une)\s+)/i

export function sortTitle(s) {
  return (s || '').replace(LEADING_ARTICLE_RE, '')
}

// Troncature simple par nombre de caractères fixe, pour garder un lien "Lire la suite"
// toujours visible à la suite du texte (inline, sur la même ligne) — pas de mesure de
// largeur réelle, juste un seuil de caractères constant quel que soit l'écran.
export function truncateForReadMore(text, maxChars = 300) {
  if (!text || text.length <= maxChars) return text
  const cut = text.slice(0, maxChars)
  const lastSpace = cut.lastIndexOf(' ')
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut).trim() + '…'
}
