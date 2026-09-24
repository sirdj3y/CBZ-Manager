import { describe, expect, it } from 'vitest'
import { sortTomesByNumber } from '../src/utils/tomeSort.js'

describe('sortTomesByNumber', () => {
  it('tri numérique, hors-séries et sans numéro à la fin', () => {
    const tomes = ['10', 'HS1', '2', null, '1', '13.5', '13'].map(number => ({ number }))
    expect(sortTomesByNumber(tomes).map(t => t.number)).toEqual(['1', '2', '10', '13', '13.5', 'HS1', null])
  })

  it('ne modifie pas le tableau d\'origine', () => {
    const tomes = [{ number: '2' }, { number: '1' }]
    sortTomesByNumber(tomes)
    expect(tomes[0].number).toBe('2')
  })

  it('entrée absente', () => {
    expect(sortTomesByNumber(undefined)).toEqual([])
  })
})
