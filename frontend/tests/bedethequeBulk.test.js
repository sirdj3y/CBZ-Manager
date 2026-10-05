import { describe, it, expect } from 'vitest'
import { applyBulkAlbum, indexAlbumsByNumber, numberKey } from '../src/utils/bedethequeBulk'

describe('complétion globale Bedetheque', () => {
  it('associe « 01 » du tableau à « 1 » de Bedetheque', () => {
    const byNumber = indexAlbumsByNumber([{ number: '1', title: 'Journal Infime' }, { number: 'HS1', title: 'HS' }])
    expect(byNumber[numberKey('01')].title).toBe('Journal Infime')
    expect(byNumber[numberKey('hs1')].title).toBe('HS')
    expect(numberKey('10')).toBe('10')
    expect(numberKey('0')).toBe('0')
    expect(numberKey('')).toBe('')
  })

  it('garde le premier album pour un numéro en double', () => {
    const byNumber = indexAlbumsByNumber([{ number: '1', title: 'Tome 1' }, { number: '1', title: 'Le petit monde 1' }])
    expect(byNumber['1'].title).toBe('Tome 1')
  })

  it("recopie l'année et le lien de la fiche album", () => {
    const row = { Title: '', Year: '', Web: '' }
    applyBulkAlbum(row, { title: 'Journal Infime', year: '2004', url: 'https://www.bedetheque.com/BD-Lou-Tome-1-Journal-Infime-37024.html', writer: 'Julien Neel' })
    expect(row).toMatchObject({ Title: 'Journal Infime', Year: '2004', Writer: 'Julien Neel', Web: 'https://www.bedetheque.com/BD-Lou-Tome-1-Journal-Infime-37024.html' })
  })

  it("ne vide pas un champ que l'album n'a pas", () => {
    const row = { Year: '1999', Publisher: 'Dupuis' }
    applyBulkAlbum(row, { title: 'X' })
    expect(row).toMatchObject({ Year: '1999', Publisher: 'Dupuis' })
  })
})
