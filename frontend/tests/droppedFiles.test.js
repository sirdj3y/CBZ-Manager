import { describe, expect, it } from 'vitest'
import { filesFromDataTransfer } from '../src/utils/droppedFiles.js'

// Faux système de fichiers au format des entrées du navigateur (FileSystemEntry).
const file = name => ({ isFile: true, isDirectory: false, name, file: ok => ok({ name }) })
function dir(name, children, batch = 100) {
  return {
    isFile: false, isDirectory: true, name,
    createReader() {
      let i = 0
      return { readEntries: ok => { const b = children.slice(i, i + batch); i += batch; ok(b) } }
    },
  }
}
const dt = entries => ({ items: entries.map(e => ({ kind: 'file', webkitGetAsEntry: () => e })), files: [] })

describe('filesFromDataTransfer', () => {
  it('dossier déposé : ses fichiers, sous-dossiers compris, et son nom', async () => {
    const res = await filesFromDataTransfer(dt([
      dir('Blacksad', [file('T01.cbz'), file('T02.cbz'), dir('Extras', [file('HS.cbz')])]),
    ]))
    expect(res.files.map(f => f.name)).toEqual(['T01.cbz', 'T02.cbz', 'HS.cbz'])
    expect(res.folders).toEqual(['Blacksad'])
  })

  it('grand dossier livré par paquets : tout est lu', async () => {
    const many = Array.from({ length: 250 }, (_, i) => file(`T${i}.cbz`))
    const res = await filesFromDataTransfer(dt([dir('Gros', many, 100)]))
    expect(res.files).toHaveLength(250)
  })

  it('fichiers déposés directement', async () => {
    const res = await filesFromDataTransfer(dt([file('a.cbz'), file('b.cbr')]))
    expect(res.files.map(f => f.name)).toEqual(['a.cbz', 'b.cbr'])
    expect(res.folders).toEqual([])
  })

  it('sans entrées (navigateur ancien) : dataTransfer.files', async () => {
    const res = await filesFromDataTransfer({ items: [], files: [{ name: 'a.cbz' }] })
    expect(res.files.map(f => f.name)).toEqual(['a.cbz'])
  })
})
