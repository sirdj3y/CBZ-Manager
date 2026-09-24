import { describe, expect, it } from 'vitest'
import { describeRules, flatToGroups, groupsToFlat } from '../src/utils/smartListRules.js'

const groups = [
  { conditions: [
    { source: 'series', field: 'classification', operator: 'is', value: 'Manga' },
    { source: 'metadata', field: 'Genre', operator: 'contains', value: 'Aventure' },
  ] },
  { conditions: [{ source: 'metadata', field: 'Tags', operator: 'is_empty', value: '' }] },
]

describe('groupsToFlat / flatToGroups', () => {
  it('ET dans un groupe, OU entre groupes', () => {
    expect(groupsToFlat(groups).map(c => c.connector)).toEqual([null, 'AND', 'OR'])
  })

  it('aller-retour sans perte', () => {
    expect(flatToGroups(groupsToFlat(groups))).toEqual(groups)
  })

  it('entrées vides', () => {
    expect(groupsToFlat(undefined)).toEqual([])
    expect(flatToGroups([])).toEqual([])
  })
})

describe('describeRules', () => {
  const catalog = [
    { source: 'series', field: 'classification', label: 'Classification' },
    { source: 'metadata', field: 'Genre', label: 'Genre' },
    { source: 'metadata', field: 'BlackAndWhite', label: 'Noir et blanc', type: 'boolean' },
  ]

  it('résumé lisible avec connecteurs', () => {
    expect(describeRules({ groups }, catalog)).toBe(
      'Classification est « Manga » ET Genre contient « Aventure » OU Tags est vide',
    )
  })

  it('booléens et intervalle', () => {
    const rules = { groups: [{ conditions: [
      { source: 'metadata', field: 'BlackAndWhite', operator: 'is', value: 'true' },
      { source: 'metadata', field: 'Year', operator: 'between', value: '1990', value2: '2000' },
    ] }] }
    expect(describeRules(rules, catalog)).toBe('Noir et blanc est « Oui » ET Year entre « 1990 » et « 2000 »')
  })

  it('sans catalogue ni règles', () => {
    expect(describeRules({ groups }, undefined)).toContain('classification est « Manga »')
    expect(describeRules(null)).toBe('')
  })
})
