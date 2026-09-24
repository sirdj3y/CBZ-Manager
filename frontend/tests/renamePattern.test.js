import { describe, expect, it } from 'vitest'
import { applyRenamePattern, applyRenameRules, formatTomeNumber } from '../src/utils/renamePattern.js'

const PATTERN = '{Série} - T{Numéro} - {Titre}'

describe('formatTomeNumber', () => {
  it.each([
    ['1', '01'], ['9', '09'], ['10', '10'], ['01', '01'], ['123', '123'],
    ['7bis', '07bis'], ['13.5', '13.5'], ['HS1', 'HS1'], ['INT', 'INT'], ['', ''], [null, ''],
  ])('%s → %s', (input, expected) => {
    expect(formatTomeNumber(input)).toBe(expected)
  })
})

describe('applyRenamePattern', () => {
  const base = { stem: 'fichier original', ext: '.cbz' }

  it('modèle par défaut', () => {
    expect(applyRenamePattern(PATTERN, { ...base, series: 'Akira', number: '1', title: 'Akira' }))
      .toBe('Akira - T01 - Akira.cbz')
  })

  it('pas de "T" orphelin ni de tiret double sans numéro', () => {
    expect(applyRenamePattern(PATTERN, { ...base, series: 'Akira', title: 'Akira' })).toBe('Akira - Akira.cbz')
  })

  it('sans titre (manga)', () => {
    expect(applyRenamePattern(PATTERN, { ...base, series: 'Horimiya', number: '10' })).toBe('Horimiya - T10.cbz')
  })

  it('régression : un tome 13.5 ou 7bis ne prend pas le nom du tome 13 ou 7', () => {
    expect(applyRenamePattern(PATTERN, { ...base, series: 'S', number: '13.5', title: 'Titre' })).toBe('S - T13.5 - Titre.cbz')
    expect(applyRenamePattern(PATTERN, { ...base, series: 'S', number: '7bis', title: 'Titre' })).toBe('S - T07bis - Titre.cbz')
  })

  it('caractères interdits remplacés (underscores consécutifs fusionnés)', () => {
    expect(applyRenamePattern('{Titre}', { ...base, title: 'Quoi ? Où: "ici"/là' })).toBe('Quoi _ Où_ _ici_là.cbz')
  })

  it('retombe sur le nom d\'origine si tout est vide', () => {
    expect(applyRenamePattern(PATTERN, base)).toBe('fichier original.cbz')
  })

  it('règles de remplacement appliquées en dernier', () => {
    const rules = [{ enabled: true, search: 'Tome', replace: 'T' }, { enabled: false, search: 'Akira', replace: 'X' }]
    expect(applyRenamePattern('{Titre}', { ...base, title: 'Akira Tome' }, rules)).toBe('Akira T.cbz')
  })
})

describe('applyRenameRules', () => {
  it('remplace toutes les occurrences, ignore les règles vides', () => {
    expect(applyRenameRules('a-b-c', [{ enabled: true, search: '-', replace: ' ' }, { enabled: true, search: '', replace: 'x' }]))
      .toBe('a b c')
  })
})
