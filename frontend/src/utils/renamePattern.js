// Shared rename-pattern engine — used by ImportView.vue (step 2, renommage à l'import)
// and RenameModal.vue (renommage d'albums existants). Kept in one place so a fix to the
// pattern logic (sanitization, token handling) doesn't need to be duplicated by hand.

export const RENAME_TOKENS = [
  '{Fichier}', '{Série}', '{Numéro}', '{Titre}', '{Année}', '{Dessinateur}', '{Scénariste}', '{Éditeur}',
]

export function formatTomeNumber(n) {
  if (!n) return ''
  const extracted = String(n).replace(/\D.*/, '').trim()
  if (!extracted) return String(n)
  const num = parseInt(extracted, 10)
  if (isNaN(num)) return String(n)
  if (/^\d+$/.test(extracted) && num < 10 && extracted.length === 1) return String(num).padStart(2, '0')
  return extracted
}

export function applyRenameRules(s, rules) {
  for (const rule of rules) {
    if (!rule.enabled || !rule.search) continue
    s = s.split(rule.search).join(rule.replace)
  }
  return s
}

// values: { stem, ext, series, number, title, year, penciller, writer, publisher }
// stem/ext come from the original filename; the rest are already resolved by the
// caller (metadata > parsed filename > fallback, in whatever priority order fits there).
export function applyRenamePattern(pattern, values, rules = []) {
  const {
    stem, ext,
    series = '', number = '', title = '', year = '',
    penciller = '', writer = '', publisher = '',
  } = values

  const formattedNumber = formatTomeNumber(number)
  let r = pattern
  r = r.replace(/{Fichier}/g, stem)
  r = r.replace(/{Filename}/g, stem)
  r = r.replace(/{Série}/g, series)
  r = r.replace(/{Series}/g, series)
  // Un "T" collé juste devant le token (convention "T{Numéro}" du modèle par défaut) n'a
  // de sens que si un numéro existe — sinon on le retire avec le token plutôt que de
  // laisser un "T" orphelin dans le nom final (ex: "Série - T - Titre").
  const numTokenReplacer = m => (formattedNumber ? m.slice(0, -'{Numéro}'.length) + formattedNumber : '')
  r = r.replace(/[Tt]?{Numéro}/g, numTokenReplacer)
  r = r.replace(/[Tt]?{Number}/g, m => (formattedNumber ? m.slice(0, -'{Number}'.length) + formattedNumber : ''))
  r = r.replace(/{Titre}/g, title)
  r = r.replace(/{Title}/g, title)
  r = r.replace(/{Année}/g, year)
  r = r.replace(/{Year}/g, year)
  r = r.replace(/{Dessinateur}/g, penciller)
  r = r.replace(/{Scénariste}/g, writer)
  r = r.replace(/{Writer}/g, writer)
  r = r.replace(/{Éditeur}/g, publisher)
  r = r.replace(/{Publisher}/g, publisher)
  r = r.replace(/[<>:"/\\|?*]/g, '_')
  // Nettoie les séparateurs orphelins dus aux tokens vides : " - - " → " - ", bords retirés
  r = r.replace(/(\s*-\s*){2,}/g, ' - ')
  r = r.replace(/^\s*-\s*/, '').replace(/\s*-\s*$/, '')
  r = r.replace(/\s{2,}/g, ' ').trim()
  r = r.replace(/_+/g, '_').replace(/^_+|_+$/g, '').trim()
  if (!r) r = stem
  r = applyRenameRules(r, rules)
  return r + ext
}
