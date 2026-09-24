// Tri numérique des tomes — partagé entre les pages/menus qui listent des tomes d'une série
// (SeriesDetailView, SeriesView, HomeView) pour les popups Convertir/Renommer. Sans ça, un tri
// texte brut sur Tome.number (ordre par défaut renvoyé par l'API) donne "01, 10, 11, 12, 02…".

export function parseTomeNumber(n) {
  if (!n) return { hs: true, val: Infinity, raw: '' }
  const s = String(n).trim()
  const isHS = /^hs/i.test(s)
  const num = parseFloat(s.replace(/[^0-9.]/gi, ''))
  return { hs: isHS, val: isNaN(num) ? Infinity : num, raw: s }
}

export function sortTomesByNumber(tomes) {
  if (!tomes) return []
  return [...tomes].sort((a, b) => {
    const pa = parseTomeNumber(a.number)
    const pb = parseTomeNumber(b.number)
    if (pa.hs !== pb.hs) return pa.hs ? 1 : -1
    if (pa.val !== pb.val) return pa.val - pb.val
    return pa.raw.localeCompare(pb.raw, 'fr', { numeric: true })
  })
}
