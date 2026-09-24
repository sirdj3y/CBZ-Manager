import { describe, expect, it } from 'vitest'
import { normalizeSearch, sortTitle, truncateForReadMore } from '../src/utils/text.js'

describe('text', () => {
  it('recherche insensible aux accents et à la casse', () => {
    expect(normalizeSearch('Château ÉTÉ')).toBe('chateau ete')
    expect(normalizeSearch(null)).toBe('')
  })

  it.each([
    ['Le Scrameustache', 'Scrameustache'],
    ["L'Incal", 'Incal'],
    ['Les Tuniques bleues', 'Tuniques bleues'],
    ['Lefranc', 'Lefranc'],
    ['Largo Winch', 'Largo Winch'],
  ])('sortTitle(%s) → %s', (input, expected) => {
    expect(sortTitle(input)).toBe(expected)
  })

  it('troncature sur un espace', () => {
    const text = 'mot '.repeat(100)
    const out = truncateForReadMore(text, 50)
    expect(out.endsWith('…')).toBe(true)
    expect(out.length).toBeLessThanOrEqual(51)
    expect(truncateForReadMore('court', 50)).toBe('court')
  })
})
