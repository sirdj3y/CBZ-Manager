// Pas de tiret long « — » dans les textes visibles de l'interface (préférence de
// l'utilisateur : il le lit comme une signature d'IA). Autorisés : les commentaires, et « — »
// seul comme valeur vide dans un tableau ou une fiche (ex. {{ x || '—' }}).
import { globSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

const src = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')

it('aucun tiret long dans les textes visibles', () => {
  const found = []
  for (const f of globSync('**/*.{vue,js}', { cwd: src })) {
    if (f.startsWith('components/shadcn/') || f.startsWith('labs/')) continue
    const text = readFileSync(join(src, f), 'utf8')
    const template = (text.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? '').replace(/<!--[\s\S]*?-->/g, '')
    const script = (f.endsWith('.js') ? text : text.split('</script>')[0])
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
    for (const chunk of [template, script]) {
      for (const line of chunk.split('\n')) {
        if (!line.includes('—')) continue
        if (/'—'|"—"|>\s*—\s*</.test(line)) continue
        found.push(`${f} : ${line.trim().slice(0, 100)}`)
      }
    }
  }
  expect(found).toEqual([])
})
