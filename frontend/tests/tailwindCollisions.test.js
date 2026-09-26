// Tailwind scanne tout src/ (voir src/components/shadcn/shadcn.css) : un utilitaire est
// généré pour tout mot qui ressemble à une classe Tailwind, et s'applique à tout élément qui
// porte cette classe. Sans preflight, c'est inoffensif… sauf si l'app utilise déjà ce nom
// pour ses propres besoins. Ce test empêche les deux cas :
//  1. une classe définie par le CSS de l'app (style.css, blocs <style>) qui est aussi un
//     utilitaire Tailwind — les deux règles se mélangeraient ;
//  2. dans un fichier qui n'utilise pas les composants shadcn, une classe du template qui est
//     un utilitaire Tailwind — il changerait l'apparence d'une page jamais pensée pour.
// Les fichiers qui importent depuis @/components/shadcn utilisent les utilitaires exprès.
import { globSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { compile } from '@tailwindcss/node'
import { describe, expect, it } from 'vitest'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = join(root, 'src')

const files = globSync('**/*.{vue,js,css}', { cwd: src })
  .filter(f => !f.startsWith('components/shadcn/') && !f.startsWith('labs/'))
  .map(f => ({ name: f, text: readFileSync(join(src, f), 'utf8') }))

function cssOf(file) {
  if (file.name.endsWith('.css')) return file.text
  return [...file.text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n')
}
function templateClassesOf(file) {
  if (!file.name.endsWith('.vue')) return []
  const tpl = file.text.match(/<template>([\s\S]*)<\/template>/)?.[1] ?? ''
  const out = []
  for (const m of tpl.matchAll(/\sclass="([^"]*)"/g)) out.push(...m[1].split(/\s+/))
  // :class="['a', { b: x }]" et :class="x ? 'a' : 'b'" : chaînes et clés d'objet
  for (const m of tpl.matchAll(/:class="([^"]*)"/g)) {
    for (const s of m[1].matchAll(/'([^']+)'/g)) out.push(...s[1].split(/\s+/))
    for (const k of m[1].matchAll(/[{,]\s*'?([a-zA-Z][\w-]*)'?\s*:/g)) out.push(k[1])
  }
  return out.filter(c => /^[a-zA-Z][\w-]*$/.test(c))
}

async function tailwindUtilities(candidates) {
  const compiler = await compile('@import "tailwindcss/utilities.css" source(none);', { base: root, onDependency() {} })
  const css = compiler.build([...candidates])
  return new Set([...css.matchAll(/^\s*\.([a-zA-Z][\w-]*)\s*\{/gm)].map(m => m[1]))
}

describe('Tailwind ne touche pas aux pages existantes', () => {
  it('aucune classe définie par le CSS de l\'app n\'est un utilitaire Tailwind', async () => {
    const defined = new Map()
    for (const f of files) {
      const css = cssOf(f).replace(/url\([^)]*\)/g, '')
      for (const m of css.matchAll(/\.([a-zA-Z][\w-]*)/g)) if (!defined.has(m[1])) defined.set(m[1], f.name)
    }
    const hits = await tailwindUtilities(defined.keys())
    expect([...hits].map(c => `${c} (${defined.get(c)})`)).toEqual([])
  })

  it('aucune page sans composant shadcn n\'utilise une classe qui est un utilitaire Tailwind', async () => {
    const used = new Map()
    for (const f of files) {
      if (/@\/components\/shadcn/.test(f.text)) continue
      for (const c of templateClassesOf(f)) if (!used.has(c)) used.set(c, f.name)
    }
    const hits = await tailwindUtilities(used.keys())
    expect([...hits].map(c => `${c} (${used.get(c)})`)).toEqual([])
  })
})
