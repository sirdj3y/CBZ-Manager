// Complétion globale de l'import depuis une page série Bedetheque.com : association des albums
// de la page aux lignes du tableau par numéro, puis recopie des champs.

// Clé de comparaison d'un numéro d'album : le tableau formate « 01 » (formatTomeNumber) quand
// Bedetheque écrit « 1 », et la casse varie (« HS1 » / « hs1 »).
export function numberKey(n) {
  const s = String(n ?? '').trim().toLowerCase()
  return s.replace(/^0+(?=\d)/, '')
}

export function indexAlbumsByNumber(albums) {
  const byNumber = {}
  for (const a of albums) {
    const key = numberKey(a.number)
    if (key && !(key in byNumber)) byNumber[key] = a
  }
  return byNumber
}

// Mêmes champs que la sélection d'un résultat album par album (ImportView.applyScraperResult),
// moins le numéro (déjà celui de la ligne) et la série (celle de l'import).
export function applyBulkAlbum(row, album) {
  if (album.title)     row.Title     = album.title
  if (album.writer)    row.Writer    = album.writer
  if (album.penciller) row.Penciller = album.penciller
  if (album.publisher) row.Publisher = album.publisher
  if (album.year)      row.Year      = String(album.year)
  if (album.url)       row.Web       = album.url
}
