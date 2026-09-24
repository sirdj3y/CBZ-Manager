// Partagé entre SmartListEditModal (édition) et CollectionDetailView (résumé affiché sur la
// fiche d'une liste) — évite de dupliquer deux fois la même logique de lecture des règles.

export const SOURCE_LABELS = { file: 'Fichier', metadata: 'Métadonnées', series: 'Série' }
export const OPERATOR_LABELS = {
  contains: 'contient', not_contains: 'ne contient pas',
  is: 'est', is_not: "n'est pas",
  is_empty: 'est vide', is_not_empty: "n'est pas vide",
  gt: 'supérieur à', lt: 'inférieur à', between: 'entre',
}

// groupes (format API : OU entre groupes, ET dans un groupe) -> liste plate, chaque condition
// (sauf la première) portant le connecteur qui la relie à la précédente.
export function groupsToFlat(groups) {
  const flat = []
  ;(groups || []).forEach(g => {
    ;(g.conditions || []).forEach((c, ci) => {
      flat.push({ ...c, connector: flat.length === 0 ? null : (ci === 0 ? 'OR' : 'AND') })
    })
  })
  return flat
}

// liste plate -> groupes (format API) — transformation inverse de groupsToFlat.
export function flatToGroups(flat) {
  const groups = []
  for (const c of flat) {
    const { connector, ...cond } = c
    if (connector === 'OR' || groups.length === 0) {
      groups.push({ conditions: [cond] })
    } else {
      groups[groups.length - 1].conditions.push(cond)
    }
  }
  return groups
}

function displayValue(value, meta) {
  if (meta?.type === 'boolean') return value === 'true' ? 'Oui' : 'Non'
  return value
}

function conditionLabel(cond, fieldsCatalog) {
  const meta = fieldsCatalog?.find(f => f.source === cond.source && f.field === cond.field)
  const fieldLabel = meta?.label || cond.field
  const opLabel = OPERATOR_LABELS[cond.operator] || cond.operator
  const needsValue = cond.operator !== 'is_empty' && cond.operator !== 'is_not_empty'
  let text = `${fieldLabel} ${opLabel}`
  if (needsValue) {
    text += ` « ${displayValue(cond.value, meta)} »`
    if (cond.operator === 'between') text += ` et « ${displayValue(cond.value2, meta)} »`
  }
  return text
}

// Résumé texte succinct des règles, ex: "Classification est « Manga » ET Genre contient
// « Aventure » OU Étiquette est « Favori »" — fieldsCatalog optionnel (labels de champs
// dégradés vers le nom brut du champ si absent, plutôt que planter).
export function describeRules(rules, fieldsCatalog) {
  const flat = groupsToFlat(rules?.groups)
  if (!flat.length) return ''
  return flat
    .map((c, i) => (i === 0 ? '' : (c.connector === 'OR' ? 'OU ' : 'ET ')) + conditionLabel(c, fieldsCatalog))
    .join(' ')
}
