// Fichiers d'un glisser-déposer, dossiers compris (import, étape 1).
//
// dataTransfer.files ne contient pas le contenu d'un dossier déposé (au mieux une entrée vide
// à son nom) : il faut passer par les entrées de système de fichiers
// (DataTransferItem.webkitGetAsEntry, supporté par tous les navigateurs actuels) et parcourir
// chaque dossier. À appeler PENDANT l'événement drop : les items ne sont plus lisibles après.

// Un dossier livre ses entrées par paquets (100 dans Chrome) : relire jusqu'à un paquet vide.
async function readAllEntries(dirEntry) {
  const reader = dirEntry.createReader()
  const all = []
  for (;;) {
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) return all
    all.push(...batch)
  }
}

async function collect(entry, out) {
  if (entry.isFile) {
    out.push(await new Promise((resolve, reject) => entry.file(resolve, reject)))
  } else if (entry.isDirectory) {
    for (const child of await readAllEntries(entry)) await collect(child, out)
  }
}

/**
 * @returns {Promise<{ files: File[], folders: string[] }>} tous les fichiers (sous-dossiers
 *   compris) et les noms des dossiers déposés au premier niveau.
 */
export async function filesFromDataTransfer(dt) {
  const entries = [...(dt?.items || [])]
    .filter(item => item.kind === 'file')
    .map(item => item.webkitGetAsEntry?.())
    .filter(Boolean)
  // Pas d'entrées disponibles (navigateur ancien, dépôt simulé) : simples fichiers.
  if (!entries.length) return { files: [...(dt?.files || [])], folders: [] }

  const files = []
  const folders = []
  for (const entry of entries) {
    if (entry.isDirectory) folders.push(entry.name)
    await collect(entry, files)
  }
  return { files, folders }
}
