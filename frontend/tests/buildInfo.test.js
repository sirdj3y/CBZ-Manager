import { describe, expect, it } from 'vitest'
import { buildInfo, formatBuildDate } from '../src/utils/buildInfo.js'

describe('buildInfo', () => {
  it('valeurs par défaut hors build Docker', () => {
    expect(buildInfo.channel).toBeTypeOf('string')
  })

  it('formatBuildDate', () => {
    const iso = new Date(2026, 8, 26, 14, 32).toISOString()
    expect(formatBuildDate(iso)).toBe('26/09 à 14:32')
    expect(formatBuildDate(iso, { withYear: true })).toBe('26/09/2026 à 14:32')
    expect(formatBuildDate('')).toBe('')
    expect(formatBuildDate('n importe quoi')).toBe('')
  })
})
